from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ewebcity-seo-optimizer/scripts"))
from reporting import compare_reports, render_html, write_reports


def fixture(status="fail"):
    return {
        "schema_version": "1.0", "tool_version": "2.0.0", "target": "https://example.com/",
        "collected_at": "2026-11-12T10:00:00Z", "mode": "offline_source_html",
        "coverage": {"pages_analysed": 1, "complete": False},
        "pages": [{"url": "https://example.com/", "http_status": None, "title": "Example", "canonical": None}],
        "findings": [{"rule_id": "TITLE_PRESENT", "url": "https://example.com/", "status": status,
                      "severity": "medium", "confidence": "high", "evidence": {"title": ""},
                      "recommendation": "Write a descriptive title.",
                      "reference_url": "https://developers.google.com/search/docs/appearance/title-link",
                      "reference_checked_at": "2026-11-12"}],
        "checks_not_performed": ["Google indexing state", "Rendered DOM", "Field Core Web Vitals"],
    }


class ComparisonTests(unittest.TestCase):
    def test_explicit_pass_resolves_and_preserves_inputs(self):
        before, after = fixture(), fixture("pass")
        originals = deepcopy((before, after))
        result = compare_reports(before, after)
        self.assertEqual(result["counts"], {"new": 0, "persistent": 0, "resolved": 1, "not_rechecked": 0})
        self.assertEqual((before, after), originals)

    def test_missing_finding_is_not_a_resolution(self):
        after = fixture()
        after["findings"] = []
        after["pages"] = []
        result = compare_reports(fixture(), after)
        self.assertEqual(result["counts"]["resolved"], 0)
        self.assertEqual(result["counts"]["not_rechecked"], 1)

    def test_explicit_unavailable_check_is_not_resolution(self):
        result = compare_reports(fixture(), fixture("not_checked"))
        self.assertEqual(result["counts"]["not_rechecked"], 1)

    def test_incomparable_mode_origin_or_version_is_not_resolution(self):
        for key, value in [("mode", "live_source_html"), ("target", "https://other.example/"),
                           ("tool_version", "3.0.0"), ("schema_version", "2.0")]:
            with self.subTest(key=key):
                after = fixture("pass")
                after[key] = value
                result = compare_reports(fixture(), after)
                self.assertFalse(result["comparable"])
                self.assertEqual(result["counts"]["resolved"], 0)
                self.assertEqual(result["counts"]["not_rechecked"], 1)

    def test_duplicate_cannot_resolve_if_related_page_was_not_rechecked(self):
        before, after = fixture(), fixture("pass")
        before["findings"][0]["rule_id"] = after["findings"][0]["rule_id"] = "duplicate_title"
        before["findings"][0]["evidence"]["related_urls"] = ["https://example.com/other"]
        result = compare_reports(before, after)
        self.assertEqual(result["counts"]["not_rechecked"], 1)
        after["pages"].append({"url": "https://example.com/other", "title": "Another"})
        self.assertEqual(compare_reports(before, after)["counts"]["resolved"], 1)

    def test_changed_canonical_does_not_require_crawling_external_old_target(self):
        before, after = fixture("warning"), fixture("pass")
        before["findings"][0]["rule_id"] = after["findings"][0]["rule_id"] = "canonical_origin"
        before["findings"][0]["evidence"]["related_urls"] = ["https://other.example/"]
        self.assertEqual(compare_reports(before, after)["counts"]["resolved"], 1)

    def test_persistent_and_new_outcomes(self):
        before, after = fixture(), fixture("warning")
        another = deepcopy(after["findings"][0])
        another["rule_id"] = "JSON_LD_VALID"
        after["findings"].append(another)
        result = compare_reports(before, after)
        self.assertEqual(result["counts"]["persistent"], 1)
        self.assertEqual(result["counts"]["new"], 1)

    def test_duplicate_keys_and_bad_status_are_rejected(self):
        report = fixture()
        report["findings"].append(deepcopy(report["findings"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate finding"):
            compare_reports(fixture(), report)
        with self.assertRaisesRegex(ValueError, "Invalid finding status"):
            compare_reports(fixture(), fixture("maybe"))


class ReportTests(unittest.TestCase):
    def test_page_content_is_escaped_and_unsafe_links_are_inert(self):
        report = fixture()
        attack = '</title><script>alert("x")</script><img src=x onerror=alert(1)>'
        report["pages"][0]["title"] = attack
        finding = report["findings"][0]
        finding.update(title=attack, recommendation=attack, reference_url="javascript:alert(1)")
        finding["evidence"]["html"] = attack
        html = render_html(report)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("Not measured (snapshot)", html)

    def test_three_outputs_include_comparison_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before"
            after = root / "after"
            write_reports(fixture(), before)
            baseline_bytes = (before / "audit.json").read_bytes()
            write_reports(fixture("pass"), after, before / "audit.json")
            self.assertEqual({p.name for p in after.iterdir()}, {"audit.json", "report.html", "fixes.md"})
            result = json.loads((after / "audit.json").read_text())
            self.assertEqual(result["comparison"]["counts"]["resolved"], 1)
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                write_reports(fixture("pass"), before)
            self.assertEqual((before / "audit.json").read_bytes(), baseline_bytes)

    def test_bad_baseline_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "bad.json"
            baseline.write_text("{bad json")
            with self.assertRaisesRegex(ValueError, "not valid"):
                write_reports(fixture(), root / "after", baseline)
            self.assertFalse((root / "after").exists())

    def test_symlink_output_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                write_reports(fixture(), link / "audit")
            self.assertEqual(list(real.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
