from copy import deepcopy
import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ewebcity-seo-optimizer/scripts"))
from reporting import compare_reports, render_html, write_reports


class DashboardDocument(HTMLParser):
    """Inspect emitted HTML semantics without relying on a layout snapshot."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.text = []
        self.scripts = []
        self.styles = []
        self._raw = None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.elements.append((tag, attrs))
        if tag in ("script", "style"):
            self._raw = []

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._raw is not None:
            (self.scripts if tag == "script" else self.styles).append("".join(self._raw))
            self._raw = None

    def handle_data(self, data):
        if self._raw is not None:
            self._raw.append(data)
        else:
            self.text.append(data)

    def by_attribute(self, attribute):
        return [attrs for _, attrs in self.elements if attribute in attrs]

    def by_class(self, tag, class_name):
        return [attrs for kind, attrs in self.elements if kind == tag and class_name in attrs.get("class", "").split()]


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
    def test_embedded_css_has_no_unmatched_rule_braces(self):
        from reporting import _STYLE
        depth, quote, escaped = 0, None, False
        for char in _STYLE:
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                self.assertGreaterEqual(depth, 0, "Unexpected closing brace can discard the next CSS rule")
        self.assertIsNone(quote)
        self.assertEqual(depth, 0)

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

    def test_csp_hashes_match_the_only_executable_code_and_styles(self):
        report = fixture()
        attack = '</script><script src="https://attacker.example/x.js">bad()</script><img src=x onerror=bad()>'
        report["findings"][0].update(title=attack, severity='medium" onclick="bad()', reference_url="data:text/html,attack")
        report["findings"][0]["evidence"]["captured_html"] = attack
        report["pages"][0]["title"] = attack
        parsed = DashboardDocument(render_html(report))
        self.assertEqual(len(parsed.scripts), 1)
        self.assertEqual(len(parsed.styles), 1)
        csp = next(attrs["content"] for tag, attrs in parsed.elements if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy")
        for content in (*parsed.scripts, *parsed.styles):
            digest = base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("ascii")
            self.assertIn("'sha256-" + digest + "'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertIn("connect-src 'none'", csp)
        self.assertFalse(any(tag == "img" for tag, _ in parsed.elements))
        self.assertFalse(any(key.startswith("on") for _, attrs in parsed.elements for key in attrs))
        self.assertFalse(any(tag == "script" and "src" in attrs for tag, attrs in parsed.elements))
        self.assertFalse(any(attrs.get("href", "").startswith(("javascript:", "data:")) for _, attrs in parsed.elements))
        # Report text cannot alter the executable program or its hash.
        self.assertEqual(parsed.scripts, DashboardDocument(render_html(fixture())).scripts)

    def test_kpis_and_distributions_use_observations_not_supplied_summary(self):
        report = fixture()
        report["summary"] = {"statuses": {"pass": 9999, "fail": 9999}}
        report["coverage"]["pages_analysed"] = 9999
        report["pages"].append({"url": "https://example.com/second", "title": "Second", "http_status": 200})
        report["findings"] = []
        for index, (rule, status) in enumerate(zip(
            ("title_present", "description_present", "noindex_directive", "jsonld_syntax", "image_alt_attribute"),
            ("fail", "warning", "pass", "not_checked", "not_applicable"),
        )):
            finding = deepcopy(fixture()["findings"][0])
            finding.update(rule_id=rule, status=status, url=report["pages"][index % 2]["url"])
            report["findings"].append(finding)
        parsed = DashboardDocument(render_html(report))
        kpis = {attrs["data-kpi"]: int(attrs["data-count"]) for attrs in parsed.by_attribute("data-kpi")}
        self.assertEqual(kpis, {"issues": 2, "pages": 2, "passed": 1, "unchecked": 1})
        statuses = {attrs["data-status-summary"]: int(attrs["data-count"]) for attrs in parsed.by_attribute("data-status-summary")}
        self.assertEqual(statuses, {status: 1 for status in ("fail", "warning", "pass", "not_checked", "not_applicable")})
        categories = parsed.by_attribute("data-category-summary")
        self.assertEqual(sum(int(attrs["data-total"]) for attrs in categories), 5)
        self.assertEqual(sum(int(attrs["data-issues"]) for attrs in categories), 2)
        self.assertEqual(len(parsed.by_class("article", "finding")), 5)
        self.assertEqual(len(parsed.by_class("tr", "page-row")), 2)

    def test_without_javascript_every_finding_and_its_evidence_is_available(self):
        report = fixture()
        report["findings"][0]["evidence"]["observation"] = "Evidence must remain readable without JavaScript."
        passed = deepcopy(report["findings"][0])
        passed.update(rule_id="DESCRIPTION_PRESENT", status="pass")
        report["findings"].append(passed)
        parsed = DashboardDocument(render_html(report))
        self.assertEqual(len(parsed.by_class("article", "finding")), 2)
        self.assertTrue(all("hidden" not in attrs for attrs in parsed.by_class("article", "finding")))
        self.assertTrue(all("open" in attrs for attrs in parsed.by_class("details", "finding-details")))
        self.assertIn("Evidence must remain readable without JavaScript.", "".join(parsed.text))
        root = next(attrs for tag, attrs in parsed.elements if tag == "html")
        self.assertNotIn("enhanced", root.get("class", ""))
        controls = {attrs["id"]: attrs for tag, attrs in parsed.elements if tag in ("input", "select") and "id" in attrs}
        labels = {attrs["for"] for tag, attrs in parsed.elements if tag == "label" and "for" in attrs}
        for control in ("finding-search", "status-filter", "severity-filter", "category-filter", "page-filter", "page-search"):
            self.assertIn(control, controls)
            self.assertIn(control, labels)

    def test_empty_report_has_zero_counts_and_no_spurious_success_claim(self):
        report = fixture()
        report["findings"] = []
        report["pages"] = []
        parsed = DashboardDocument(render_html(report))
        self.assertTrue(all(attrs["data-count"] == "0" for attrs in parsed.by_attribute("data-kpi")))
        self.assertIn("No checks were recorded", "".join(parsed.text))
        self.assertIn("No HTML pages were analysed", "".join(parsed.text))
        self.assertIn("No baseline supplied", "".join(parsed.text))

    def test_comparison_cards_count_recorded_outcomes_and_escape_explanations(self):
        before, after = fixture(), fixture("pass")
        comparison = compare_reports(before, after)
        comparison["counts"] = {key: 999 for key in ("resolved", "persistent", "new", "not_rechecked")}
        comparison["resolved"][0]["reason"] = '<img src=x onerror="bad()"> Explicit pass'
        after["comparison"] = comparison
        parsed = DashboardDocument(render_html(after))
        counts = {attrs["data-comparison"]: int(attrs["data-count"]) for attrs in parsed.by_attribute("data-comparison")}
        self.assertEqual(counts, {"resolved": 1, "persistent": 0, "new": 0, "not_rechecked": 0})
        self.assertFalse(any(tag == "img" for tag, _ in parsed.elements))
        self.assertIn("Explicit pass", "".join(parsed.text))

    def test_imported_measurements_keep_lab_field_scope_units_and_period(self):
        report = fixture()
        report["measurements"] = {
            "items": [
                {"source": "Lighthouse", "kind": "lab", "scope": "url", "url": "https://example.com/",
                 "collected_at": "2026-11-12T10:00:00Z", "device": "mobile", "aggregation": "navigation sample",
                 "input_file": "lab.json", "source_version": "13.0", "metrics": [{"id": "lcp", "label": "LCP", "value": 1250, "unit": "ms", "rating": "good"}]},
                {"source": "Chrome UX Report", "kind": "field", "scope": "origin", "url": "https://example.com/",
                 "device": "not recorded", "aggregation": "p75", "collection_period": {"start": "2026-10-15", "end": "2026-11-11"},
                 "input_file": '<img src=x onerror="bad()">', "input_sha256": "abc123",
                 "metrics": [{"id": "cls", "label": "CLS", "value": 0.06, "unit": "score", "rating": "good"}]},
            ],
            "issues": ['Ignored unsupported metric: <script>bad()</script>'],
        }
        parsed = DashboardDocument(render_html(report))
        text = "".join(parsed.text)
        self.assertEqual(len(parsed.by_class("article", "measurement")), 2)
        for expected in ("lab measurement", "field measurement", "URL-specific", "Origin-wide", "navigation sample", "p75", "2026-10-15 to 2026-11-11", "Device: not recorded", "1,250", "ms", "0.06", "abc123"):
            self.assertIn(expected, text)
        self.assertFalse(any(tag == "img" for tag, _ in parsed.elements))
        self.assertEqual(len(parsed.scripts), 1)
        self.assertIn("Imported performance evidence is listed separately", text)

    def test_demo_banner_requires_literal_boolean(self):
        for value in (False, "true", 1, None):
            with self.subTest(value=value):
                report = fixture()
                report["demonstration"] = value
                self.assertEqual(DashboardDocument(render_html(report)).by_class("div", "demo-banner"), [])
        report["demonstration"] = True
        parsed = DashboardDocument(render_html(report))
        self.assertEqual(len(parsed.by_class("div", "demo-banner")), 1)
        self.assertIn("Sample HTML and synthetic performance exports; not a live website assessment.", "".join(parsed.text))

    def test_field_collection_window_is_distinct_from_export_analysis_time(self):
        report = fixture()
        report["measurements"] = {"items": [
            {"source": "PageSpeed Insights / CrUX", "kind": "field", "scope": "url", "url": report["target"],
             "collected_at": "2026-11-12T12:00:00Z", "collection_period": None, "aggregation": "p75", "device": "not recorded", "metrics": [],
             "note": 'Analysis time is not the collection window. <img src=x onerror="bad()">'},
            {"source": "CrUX API", "kind": "field", "scope": "origin", "url": report["target"],
             "collected_at": None, "collection_period": {"start": "2026-10-15", "end": "2026-11-11"},
             "aggregation": "p75", "device": "PHONE", "metrics": [], "note": "Origin data is aggregate evidence."},
        ]}
        parsed = DashboardDocument(render_html(report))
        text = "".join(parsed.text)
        self.assertIn("Collection window not recorded", text)
        self.assertIn("Export analysis timestamp: 12 Nov 2026 · 12:00 UTC", text)
        self.assertIn("Collection window: 2026-10-15 to 2026-11-11", text)
        self.assertEqual(len(parsed.by_class("p", "measurement-timestamp")), 1)
        self.assertEqual(len(parsed.by_class("p", "measurement-note")), 2)
        self.assertIn("Analysis time is not the collection window.", text)
        self.assertFalse(any(tag == "img" for tag, _ in parsed.elements))
        self.assertEqual(len(parsed.scripts), 1)

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
