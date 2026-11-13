"""Regressions for crawler-scoped directives and source evidence accuracy."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "ewebcity-seo-optimizer" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import analyse_html, audit_live, audit_offline, main
from html_evidence import decode_html, link_header_evidence
from reporting import compare_reports
from test_audit import TARGET, document, find, paths, response
from test_safe_http import fixture_server


class DirectiveEvidenceTests(unittest.TestCase):
    def test_parameter_none_does_not_create_a_noindex_directive(self):
        page, findings = analyse_html(TARGET, document(head='<meta name="robots" content="max-image-preview:none, max-snippet:0">'
                                                       '<link rel="canonical" href="/">'))
        self.assertEqual(page["noindex_observations"], [])
        self.assertEqual(find(findings, "noindex_directive")["status"], "pass")
        self.assertEqual(find(findings, "canonical_noindex_conflict")["status"], "pass")

    def test_repeated_header_fields_do_not_leak_a_crawler_prefix(self):
        page, _findings = analyse_html(TARGET, document(),
            headers={"X-Robots-Tag": "googlebot: noindex, nofollow"},
            header_values={"x-robots-tag": ["Googlebot: NoIndex", "nofollow"]})
        policy = page["robots_policy"]["by_agent"]
        self.assertTrue(policy["googlebot"]["noindex"])
        self.assertFalse(policy["bingbot"]["noindex"])
        self.assertTrue(policy["bingbot"]["nofollow"])
        self.assertTrue(page["robots_policy"]["raw_header_fields_preserved"])

    def test_other_crawler_noindex_is_not_a_google_canonical_conflict(self):
        page, findings = analyse_html(TARGET, document(head='<link rel="canonical" href="/">'),
                                      headers={"X-Robots-Tag": "otherbot: noindex, nofollow"})
        self.assertEqual(page["noindex_observations"][0]["agent"], "otherbot")
        self.assertFalse(page["robots_policy"]["by_agent"]["googlebot"]["noindex"])
        self.assertEqual(find(findings, "canonical_noindex_conflict")["status"], "pass")

    def test_unknown_first_directive_cannot_globalise_a_scoped_header(self):
        page, findings = analyse_html(TARGET, document(head='<link rel="canonical" href="/">'),
                                      headers={"X-Robots-Tag": "otherbot: unknown-directive, noindex"})
        self.assertEqual(page["noindex_observations"][0]["agent"], "otherbot")
        self.assertFalse(page["robots_policy"]["by_agent"]["googlebot"]["noindex"])
        self.assertFalse(page["robots_policy"]["by_agent"]["bingbot"]["noindex"])
        self.assertEqual(find(findings, "canonical_noindex_conflict")["status"], "pass")

    def test_scoped_whitespace_flags_are_not_reported_as_clean_absence(self):
        page, findings = analyse_html(TARGET, document(head='<link rel="canonical" href="/">'),
                                      headers={"X-Robots-Tag": "googlebot: noindex nofollow"})
        self.assertTrue(page["robots_policy"]["by_agent"]["googlebot"]["noindex"])
        self.assertEqual(find(findings, "noindex_directive")["status"], "warning")

    def test_directive_limit_keeps_unobserved_noindex_unknown(self):
        page, findings = analyse_html(TARGET, document(head='<link rel="canonical" href="/">'),
            headers={"X-Robots-Tag": "googlebot: index," + "index," * 256 + "noindex"})
        self.assertTrue(page["robots_policy"]["parsing_limited"])
        self.assertTrue(page["extraction_limited"])
        self.assertEqual(find(findings, "noindex_directive")["status"], "not_checked")
        self.assertEqual(find(findings, "canonical_noindex_conflict")["status"], "not_checked")

    def test_scope_specific_conflicts_and_news_rules_remain_explicit(self):
        page, findings = analyse_html(TARGET, document(head='<meta name="robots" content="index,follow">'
            '<meta name="googlebot-news" content="none"><meta name="googlebot" content="nofollow">'))
        self.assertFalse(page["robots_policy"]["by_agent"]["googlebot"]["noindex"])
        self.assertTrue(page["robots_policy"]["by_agent"]["googlebot-news"]["noindex"])
        self.assertEqual(find(findings, "robots_directive_conflicts")["status"], "warning")

    def test_invalid_parameter_values_are_reviewed_without_inventing_noindex(self):
        page, findings = analyse_html(TARGET, document(head='<meta name="robots" content="max-snippet:noindex, max-image-preview:huge">'))
        self.assertEqual(page["noindex_observations"], [])
        self.assertEqual(find(findings, "robots_directives_review")["status"], "warning")

    def test_real_repeated_http_headers_reach_the_scoped_parser(self):
        class RepeatedHeaders(dict):
            def items(self):
                return [("Content-Type", "text/html"), ("X-Robots-Tag", "googlebot: noindex"),
                        ("X-Robots-Tag", "nofollow")]
        with fixture_server({"/": (200, RepeatedHeaders(), document())}) as (url, _requests):
            report = audit_live(url, allow_localhost=True, delay=0)
        policy = report["pages"][0]["robots_policy"]["by_agent"]
        self.assertTrue(policy["googlebot"]["noindex"])
        self.assertFalse(policy["bingbot"]["noindex"])
        self.assertTrue(policy["bingbot"]["nofollow"])


class SourceAndCanonicalTests(unittest.TestCase):
    def test_title_and_textarea_markup_cannot_invent_metadata_or_links(self):
        page, _findings = analyse_html(TARGET, document('<textarea><meta name="robots" content="noindex">'
            '<link rel="canonical" href="https://other.example/"><a href="/fake">Fake</a></textarea>',
            title='A &amp; B <b>literal</b>'))
        self.assertEqual(page["title"], "A & B <b>literal</b>")
        self.assertEqual(page["noindex_observations"], [])
        self.assertEqual(page["canonical"], [])
        self.assertEqual(page["links"], [])

    def test_later_duplicate_attributes_do_not_override_html_first_value(self):
        page, _findings = analyse_html(TARGET, document(head='<meta name="robots" content="index" content="noindex">'))
        self.assertEqual(page["noindex_observations"], [])

    def test_header_canonical_resolves_against_response_url_not_html_base(self):
        page, findings = analyse_html(TARGET, document(head='<base href="https://other.example/base/">'),
                                      headers={"Link": '</canonical>; rel="canonical"'})
        self.assertEqual(page["canonical"], ["https://example.org/canonical"])
        self.assertEqual(find(findings, "canonical_present")["status"], "pass")
        self.assertEqual(page["canonical_sources"][0]["source"], "http:link")

    def test_matching_canonical_channels_are_not_conflicting(self):
        _page, findings = analyse_html(TARGET, document(head='<link rel="canonical" href="/">'),
                                       headers={"Link": '<https://example.org/>; rel="canonical"'})
        self.assertEqual(find(findings, "canonical_signal_consistency")["status"], "pass")
        self.assertEqual(find(findings, "canonical_single")["status"], "pass")

    def test_conflicting_channels_fragments_and_body_placement_have_evidence(self):
        _page, findings = analyse_html(TARGET, document('<link rel="canonical" href="/other#topic">'),
                                       headers={"Link": '<https://example.org/>; rel="canonical"'})
        for rule in ("canonical_signal_consistency", "canonical_fragment", "canonical_source_head"):
            self.assertEqual(find(findings, rule)["status"], "warning", rule)

    def test_link_header_commas_and_quoted_parameters_do_not_split_targets(self):
        result = link_header_evidence({"Link": '<https://example.org/?a=1,2>; rel="canonical"; title="a,b;c", '
                                     '<https://example.org/fr>; rel="alternate"; hreflang="fr"'})
        self.assertEqual(len(result["links"]), 2)
        self.assertEqual(result["links"][0]["href"], "https://example.org/?a=1,2")
        self.assertEqual(result["links"][1]["hreflang"], "fr")

    def test_malformed_link_parameter_quotes_and_tokens_remain_unknown(self):
        for value in ('<https://example.org/>; rel=canonical garbage',
                      '<https://example.org/>; rel="canonical" "alternate"'):
            with self.subTest(value=value):
                result = link_header_evidence({"Link": value})
                self.assertTrue(result["invalid"])
                _page, findings = analyse_html(TARGET, document(), headers={"Link": value})
                self.assertEqual(find(findings, "canonical_present")["status"], "not_checked")

    def test_link_annotation_limit_does_not_hide_an_uninspected_canonical(self):
        value = ",".join(f'</asset/{i}>; rel="preload"' for i in range(200)) + ',</missing>; rel="canonical"'
        page, findings = analyse_html(TARGET, document(), headers={"Link": value})
        self.assertTrue(page["header_link_errors"])
        self.assertEqual(find(findings, "canonical_present")["status"], "not_checked")

    def test_unassessed_link_context_cannot_resolve_a_failed_canonical_target(self):
        routes = {"/": (200, {"Content-Type": "text/html", "Link": '</missing>; rel="canonical"'}, document()),
                  "/missing": response("Not found", status=404, content_type="text/plain")}
        with fixture_server(routes) as (url, _requests):
            before = audit_live(url, allow_localhost=True, delay=0)
            routes["/"] = (200, {"Content-Type": "text/html", "Link": '</missing>; rel="canonical"; anchor="/another-context"'}, document())
            after = audit_live(url, allow_localhost=True, delay=0)
        self.assertEqual(find(before["findings"], "canonical_target_response", url + "/")["status"], "warning")
        self.assertEqual(find(after["findings"], "canonical_target_response", url + "/")["status"], "not_checked")
        result = compare_reports(before, after)
        self.assertIn(("canonical_target_response", url + "/"), {(item["rule_id"], item["url"]) for item in result["not_rechecked"]})


class DecodingEvidenceTests(unittest.TestCase):
    def test_bom_wins_over_conflicting_http_charset(self):
        text, info = decode_html(document(title="বাংলা").encode("utf-8-sig"), {"Content-Type": "text/html; charset=windows-1252"})
        self.assertIn("বাংলা", text)
        self.assertEqual(info["source"], "bom")
        self.assertFalse(info["had_errors"])

    def test_meta_latin1_label_uses_html_windows1252_mapping(self):
        body = document(title="Café “care”", head='<meta charset="iso-8859-1">').encode("cp1252")
        text, info = decode_html(body, {})
        self.assertIn("Café “care”", text)
        self.assertEqual(info["source"], "meta")
        self.assertEqual(info["encoding"], "windows-1252")

    def test_comment_and_textarea_fake_meta_do_not_control_decoding(self):
        body = ('<!-- <meta charset="windows-1252"> --><textarea><meta charset="windows-1252"></textarea>'
                '<meta charset="utf-8"><title>বাংলা</title>').encode()
        text, info = decode_html(body, {})
        self.assertIn("বাংলা", text)
        self.assertEqual(info["encoding"], "utf-8")

    def test_non_web_python_codecs_are_rejected_and_disclosed(self):
        for charset in ("idna", "utf-7", "unicode_escape", "hex"):
            with self.subTest(charset=charset):
                text, info = decode_html(document().encode(), {"Content-Type": f"text/html; charset={charset}"})
                self.assertIn("Fixture page", text)
                self.assertTrue(info["unsupported_declarations"])
                self.assertEqual(info["encoding"], "utf-8")

    def test_nul_in_charset_label_is_reported_without_crashing(self):
        text, info = decode_html(b'<meta charset="utf-\x00-8"><title>Example</title>', {})
        self.assertIn("Example", text)
        self.assertTrue(info["unsupported_declarations"])

    def test_utf16_meta_aliases_cannot_hide_ascii_noindex(self):
        for label in ("utf16", "utf-16", "utf_16", "utf_16_le", "utf-16-be"):
            with self.subTest(label=label):
                body = f'<meta charset="{label}"><meta name="robots" content="noindex"><title>Example</title>'.encode()
                body += b" " * (len(body) % 2)
                text, info = decode_html(body, {})
                page, findings = analyse_html(TARGET, text, decoding=info)
                self.assertEqual(info["encoding"], "utf-8")
                self.assertEqual(page["title"], "Example")
                self.assertEqual(find(findings, "noindex_directive")["status"], "warning")

    def test_utf16_header_without_bom_and_meta_http_equiv_are_read(self):
        text, info = decode_html(document(title="Care").encode("utf-16-le"), {"Content-Type": "text/html; charset=utf-16"})
        self.assertIn("Care", text)
        self.assertFalse(info["had_errors"])
        text, info = decode_html(document(title="Café", head='<meta http-equiv="Content-Type" content="text/html; charset=windows-1252">').encode("cp1252"), {})
        self.assertIn("Café", text)
        self.assertEqual(info["source"], "meta")

    def test_decode_errors_do_not_resolve_previous_duplicate_findings(self):
        routes = {"/": response(document('<a href="/two">Two</a>', title="Same")),
                  "/two": response(document(title="Same"))}
        with fixture_server(routes) as (url, _requests):
            before = audit_live(url, allow_localhost=True, delay=0)
            routes["/two"] = response(document(title="BROKEN").encode().replace(b"BROKEN", b"\xff"))
            after = audit_live(url, allow_localhost=True, delay=0)
        self.assertEqual(find(after["findings"], "duplicate_title", url + "/")["status"], "not_checked")
        result = compare_reports(before, after)
        self.assertIn(("duplicate_title", url + "/"), {(item["rule_id"], item["url"]) for item in result["not_rechecked"]})


class HreflangEvidenceTests(unittest.TestCase):
    def audit(self, url, **options):
        return audit_live(url, allow_localhost=True, delay=0, **options)

    def test_invalid_relative_and_reserved_region_values_are_reviewed(self):
        _page, findings = analyse_html(TARGET, document(head='<link rel="alternate" hreflang="en-UK" href="/uk">'
            '<link rel="alternate" hreflang="es-419" href="https://example.org/es">'))
        result = find(findings, "hreflang_syntax")
        self.assertEqual(result["status"], "warning")
        self.assertIn("href_not_fully_qualified", result["evidence"]["declarations"][0]["issues"])
        self.assertFalse(result["evidence"]["registry_codes_validated"])

    def test_fetched_language_variants_with_return_links_pass(self):
        def variant(_path, base):
            return response(document(head=f'<link rel="alternate" hreflang="en" href="{base}/">'
                f'<link rel="alternate" hreflang="fr" href="{base}/fr">'))
        with fixture_server({"/": variant, "/fr": variant}) as (url, requests):
            report = self.audit(url)
        self.assertIn("/fr", paths(requests))
        self.assertEqual(find(report["findings"], "hreflang_return_links", url + "/")["status"], "pass")

    def test_external_or_uncrawled_variants_are_unknown_not_broken(self):
        with fixture_server({"/": response(document(head='<link rel="alternate" hreflang="fr" href="https://other.example/fr">'))}) as (url, requests):
            report = self.audit(url)
        self.assertEqual(paths(requests), ["/robots.txt", "/sitemap.xml", "/"])
        self.assertEqual(find(report["findings"], "hreflang_return_links", url + "/")["status"], "not_checked")

    def test_invalidating_a_language_tag_does_not_resolve_a_failed_destination(self):
        routes = {"/": lambda _path, base: response(document(head=f'<link rel="alternate" hreflang="fr" href="{base}/fr">')),
                  "/fr": response("Not found", status=404, content_type="text/plain")}
        with fixture_server(routes) as (url, _requests):
            before = self.audit(url)
            routes["/"] = lambda _path, base: response(document(head=f'<link rel="alternate" hreflang="fr-" href="{base}/fr">'))
            after = self.audit(url)
        self.assertEqual(find(before["findings"], "hreflang_target_response", url + "/")["status"], "warning")
        self.assertEqual(find(after["findings"], "hreflang_target_response", url + "/")["status"], "not_checked")
        result = compare_reports(before, after)
        self.assertIn(("hreflang_target_response", url + "/"), {(item["rule_id"], item["url"]) for item in result["not_rechecked"]})

    def test_truncated_return_annotations_cannot_resolve_previous_missing_return(self):
        routes = {
            "/": lambda _path, base: response(document(head=f'<link rel="alternate" hreflang="en" href="{base}/">'
                                                      f'<link rel="alternate" hreflang="fr" href="{base}/fr">')),
            "/fr": lambda _path, base: response(document(head=f'<link rel="alternate" hreflang="fr" href="{base}/fr">')),
        }
        with fixture_server(routes) as (url, _requests):
            before = self.audit(url)
            self.assertEqual(find(before["findings"], "hreflang_return_links", url + "/")["status"], "warning")
            routes["/fr"] = lambda _path, base: response(document(head=f'<link rel="alternate" hreflang="fr" href="{base}/fr">' * 200
                + f'<link rel="alternate" hreflang="en" href="{base}/">'))
            after = self.audit(url)
        self.assertEqual(find(after["findings"], "hreflang_return_links", url + "/")["status"], "not_checked")
        result = compare_reports(before, after)
        self.assertIn(("hreflang_return_links", url + "/"), {(item["rule_id"], item["url"]) for item in result["not_rechecked"]})


class MeasurementGateTests(unittest.TestCase):
    def test_invalid_performance_export_fails_before_crawling_or_html_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = root / "bad.json"
            bad.write_text("{invalid", encoding="utf-8")
            with patch("audit.audit_live") as live, patch("audit.audit_offline") as offline, redirect_stderr(io.StringIO()):
                result = main(["--url", TARGET, "--html", str(root / "does-not-exist.html"),
                               "--output", str(root / "out"), "--performance-json", str(bad)])
            self.assertEqual(result, 1)
            live.assert_not_called()
            offline.assert_not_called()
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
