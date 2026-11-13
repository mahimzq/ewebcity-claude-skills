"""Supplied metrics must retain scope, provenance and measurement meaning."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ewebcity-seo-optimizer/scripts"))
from measurements import load_performance_evidence

TARGET = "https://example.com/service"


def lighthouse():
    return {
        "requestedUrl": TARGET, "finalUrl": TARGET, "fetchTime": "2026-11-12T12:00:00Z",
        "lighthouseVersion": "13.0.0", "configSettings": {"formFactor": "mobile", "throttlingMethod": "simulate"},
        "audits": {
            "largest-contentful-paint": {"numericValue": 2600, "numericUnit": "millisecond"},
            "cumulative-layout-shift": {"numericValue": 0.08, "numericUnit": "unitless"},
            "total-blocking-time": {"numericValue": 150, "numericUnit": "millisecond"},
        },
    }


def psi():
    return {
        "analysisUTCTimestamp": "2026-11-12T12:00:00Z", "lighthouseResult": lighthouse(),
        "loadingExperience": {"id": TARGET, "metrics": {
            "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2500},
            "INTERACTION_TO_NEXT_PAINT": {"percentile": 201},
            "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 10, "distributions": [{"max": 10}, {"max": 25}, {"min": 25}]},
        }},
        "originLoadingExperience": {"id": "https://example.com", "metrics": {
            "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 4100},
        }},
    }


def crux():
    return {"record": {
        "key": {"origin": "https://example.com", "formFactor": "PHONE"},
        "metrics": {
            "largest_contentful_paint": {"percentiles": {"p75": 2400}},
            "interaction_to_next_paint": {"percentiles": {"p75": 190}},
            "cumulative_layout_shift": {"percentiles": {"p75": "0.10"}},
        },
        "collectionPeriod": {"firstDate": {"year": 2026, "month": 10, "day": 15}, "lastDate": {"year": 2026, "month": 11, "day": 11}},
    }}


class MeasurementTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_performance_evidence([path], TARGET)

    def test_lab_is_separate_unrated_and_does_not_fabricate_inp(self):
        result = self.load(lighthouse())
        item = result["items"][0]
        self.assertEqual((item["kind"], item["scope"], item["device"]), ("lab", "url", "mobile"))
        self.assertEqual(item["url"], TARGET)
        self.assertEqual(len(item["input_sha256"]), 64)
        self.assertEqual(item["input_file"], "export.json")
        self.assertEqual({m["id"] for m in item["metrics"]}, {"lcp", "cls", "tbt"})
        self.assertEqual({m["rating"] for m in item["metrics"]}, {"unrated"})

    def test_psi_field_and_origin_scope_are_never_combined_with_lab(self):
        result = self.load(psi())
        self.assertEqual([(i["kind"], i["scope"]) for i in result["items"]], [("lab", "url"), ("field", "url"), ("field", "origin")])
        field = result["items"][1]
        self.assertEqual(field["device"], "not recorded")
        self.assertIsNone(field["collection_period"])
        values = {m["id"]: m for m in field["metrics"]}
        self.assertEqual(values["lcp"]["rating"], "good")
        self.assertEqual(values["inp"]["rating"], "needs_improvement")
        self.assertEqual(values["cls"]["value"], 0.1)
        self.assertEqual(values["cls"]["raw_value"], 10)
        self.assertEqual(result["items"][2]["metrics"][0]["rating"], "poor")

    def test_psi_origin_fallback_is_explicit(self):
        data = psi()
        data["loadingExperience"].update(id="https://example.com", origin_fallback=True)
        self.assertEqual(self.load(data)["items"][1]["scope"], "origin")

    def test_psi_cls_ambiguous_scale_is_omitted(self):
        data = psi()
        del data["loadingExperience"]["metrics"]["CUMULATIVE_LAYOUT_SHIFT_SCORE"]["distributions"]
        result = self.load(data)
        self.assertNotIn("cls", {m["id"] for m in result["items"][1]["metrics"]})
        self.assertTrue(any("scale" in issue for issue in result["issues"]))

    def test_psi_unitless_histogram_is_not_divided_twice(self):
        data = psi()
        data["loadingExperience"]["metrics"]["CUMULATIVE_LAYOUT_SHIFT_SCORE"] = {
            "percentile": 0.2, "distributions": [{"max": 0.1}, {"max": 0.25}],
        }
        metrics = self.load(data)["items"][1]["metrics"]
        self.assertEqual(next(m["value"] for m in metrics if m["id"] == "cls"), 0.2)

    def test_crux_preserves_window_and_does_not_invent_fetch_date(self):
        item = self.load(crux())["items"][0]
        self.assertEqual(item["collection_period"], {"start": "2026-10-15", "end": "2026-11-11"})
        self.assertIsNone(item["collected_at"])
        self.assertEqual(item["aggregation"], "p75")
        self.assertEqual(item["device"], "PHONE")
        self.assertEqual(next(m["value"] for m in item["metrics"] if m["id"] == "cls"), 0.1)

    def test_crux_missing_device_is_all_form_factors(self):
        data = crux()
        del data["record"]["key"]["formFactor"]
        self.assertEqual(self.load(data)["items"][0]["device"], "all form factors")

    def test_foreign_origin_and_credentials_are_rejected(self):
        for url in ["https://other.example/service", "https://user:secret@example.com/service", "javascript:alert(1)"]:
            with self.subTest(url=url):
                data = lighthouse()
                data["finalUrl"] = url
                with self.assertRaises(ValueError):
                    self.load(data)

    def test_origin_evidence_cannot_masquerade_as_page_path(self):
        data = crux()
        data["record"]["key"]["origin"] = TARGET
        with self.assertRaisesRegex(ValueError, "origin evidence"):
            self.load(data)

    def test_invalid_runtime_does_not_import_apparent_lab_success(self):
        data = psi()
        data["lighthouseResult"]["runtimeError"] = {"code": "NO_FCP"}
        result = self.load(data)
        self.assertTrue(all(item["kind"] == "field" for item in result["items"]))
        self.assertTrue(any("runtime error" in issue for issue in result["issues"]))

    def test_errored_unsupported_unit_and_invalid_numeric_audits_are_omitted(self):
        data = lighthouse()
        data["audits"]["largest-contentful-paint"]["scoreDisplayMode"] = "error"
        data["audits"]["cumulative-layout-shift"]["numericUnit"] = "millisecond"
        data["audits"]["total-blocking-time"]["numericValue"] = True
        self.assertFalse(self.load(data)["items"])
        for value in [-1, None, "2500", 10**400]:
            with self.subTest(value=str(value)[:30]):
                data = lighthouse()
                data["audits"]["largest-contentful-paint"]["numericValue"] = value
                self.assertNotIn("lcp", {m["id"] for m in self.load(data)["items"][0]["metrics"]})

    def test_empty_field_data_does_not_become_zero_or_pass(self):
        result = self.load({"loadingExperience": {"id": TARGET, "metrics": {}}})
        self.assertFalse(result["items"])
        self.assertTrue(result["issues"])

    def test_malformed_enum_types_never_crash_or_become_known_devices(self):
        for value in [[], ["mobile"], {}, {"device": "PHONE"}, True]:
            with self.subTest(value=value):
                data = lighthouse()
                data["configSettings"].update(formFactor=value, emulatedFormFactor=value, throttlingMethod=value)
                data["audits"]["largest-contentful-paint"]["scoreDisplayMode"] = value
                data["audits"]["cumulative-layout-shift"]["numericUnit"] = value
                item = self.load(data)["items"][0]
                self.assertEqual(item["device"], "not recorded")
                self.assertEqual(item["throttling_method"], "not recorded")
                self.assertNotIn("cls", {m["id"] for m in item["metrics"]})
                data = psi()
                data["loadingExperience"]["metrics"]["LARGEST_CONTENTFUL_PAINT_MS"]["formFactor"] = value
                self.assertEqual(self.load(data)["items"][1]["device"], "not recorded")
                data = crux()
                data["record"]["key"]["formFactor"] = value
                self.assertEqual(self.load(data)["items"][0]["device"], "not recorded")

    def test_origin_fallback_requires_a_boolean(self):
        data = psi()
        data["loadingExperience"]["origin_fallback"] = "true"
        with self.assertRaisesRegex(ValueError, "boolean"):
            self.load(data)

    def test_bad_timestamps_and_date_ranges_are_reported_as_missing(self):
        data = lighthouse()
        data["fetchTime"] = "2026-11-12T12:00:00"
        result = self.load(data)
        self.assertIsNone(result["items"][0]["collected_at"])
        self.assertTrue(result["issues"])
        data = crux()
        data["record"]["collectionPeriod"]["firstDate"]["year"] = 2027
        self.assertIsNone(self.load(data)["items"][0]["collection_period"])

    def test_unsupported_error_and_wrong_structures_fail_closed(self):
        for data in [{}, [], {"error": {"code": 429}}, {"record": []}, {"lighthouseResult": None}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.load(data)

    def test_duplicate_and_nonfinite_json_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            for raw in ['{"audits":{},"audits":{}}', '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}']:
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "valid, finite"):
                    load_performance_evidence([path], TARGET)

    def test_file_and_total_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.json"
            path.write_text(json.dumps(lighthouse()))
            with patch("measurements.MAX_FILE_BYTES", 8), self.assertRaisesRegex(ValueError, "input limit"):
                load_performance_evidence([path], TARGET)
            with patch("measurements.MAX_TOTAL_BYTES", 8), self.assertRaisesRegex(ValueError, "input limit"):
                load_performance_evidence([path], TARGET)
            with self.assertRaisesRegex(ValueError, "At most"):
                load_performance_evidence([path] * 9, TARGET)
            with self.assertRaisesRegex(ValueError, "regular JSON file"):
                load_performance_evidence([Path(tmp)], TARGET)

    def test_duplicate_export_is_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.json"
            path.write_text(json.dumps(lighthouse()))
            result = load_performance_evidence([path, path], TARGET)
            self.assertEqual(len(result["items"]), 1)
            self.assertTrue(any("duplicate input" in issue for issue in result["issues"]))

    def test_import_never_resolves_hosts_or_makes_network_requests(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("Network is forbidden")), patch("http.client.HTTPConnection.connect", side_effect=AssertionError("Network is forbidden")):
            result = self.load(psi())
            self.assertEqual(len(result["items"]), 3)
        self.assertEqual(load_performance_evidence([], TARGET)["items"], [])

    def test_declared_demonstration_inputs_keep_their_qualification(self):
        data = lighthouse()
        data["_demonstration"] = "Synthetic test data, not a provider run"
        item = self.load(data)["items"][0]
        self.assertTrue(item["demonstration"])
        self.assertIn("SYNTHETIC DEMONSTRATION", item["note"])
        self.assertNotIn("demonstration", self.load(lighthouse())["items"][0])


if __name__ == "__main__":
    unittest.main()
