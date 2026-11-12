"""Behavioural source-audit tests using saved HTML and local fixture servers."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "ewebcity-seo-optimizer" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import analyse_html, audit_live, audit_offline
from safe_http import FetchError
from test_safe_http import fixture_server

STAMP = "2026-11-12T12:00:00Z"
TARGET = "https://example.org/"


def document(body="", title="Fixture page", head=""):
    return (f'<!doctype html><html lang="en"><head><title>{title}</title>'
            '<meta name="description" content="A useful, real page summary">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">{head}</head>'
            f'<body><h1>A useful heading</h1>{body}</body></html>')


def response(body, status=200, content_type="text/html"):
    return status, {"Content-Type": content_type}, body


def find(items, rule, url=None):
    return next(item for item in items if item["rule_id"] == rule and (url is None or item["url"] == url))


def paths(requests):
    return [request["path"] for request in requests]


class SourceHTMLTests(unittest.TestCase):
    def analyse(self, html, **options):
        return analyse_html(TARGET, html, collected_at=STAMP, **options)

    def test_entities_and_case_insensitive_attributes_are_preserved(self):
        page, findings = self.analyse('<HTML LANG="en-GB"><HEAD><TITLE>Research &amp; care &#169;</TITLE>'
                                     '<META NAME="DESCRIPTION" CONTENT="A &amp; B">'
                                     '<LINK REL="alternate CANONICAL" HREF="/care?x=1&amp;y=2"></HEAD>'
                                     '<BODY><H1>Care &amp; support</H1></BODY></HTML>')
        self.assertEqual(page["title"], "Research & care ©")
        self.assertEqual(page["meta_description"], "A & B")
        self.assertEqual(page["canonical"], ["https://example.org/care?x=1&y=2"])
        self.assertEqual(page["headings"], [{"level": 1, "text": "Care & support"}])
        self.assertEqual(find(findings, "title_present")["status"], "pass")

    def test_comments_scripts_and_styles_do_not_invent_document_tags(self):
        html = document('<!-- <title>Fake</title><a href="/comment">x</a> -->'
                        '<script>const x = \'<a href="/script">fake</a><meta name="robots" content="noindex">\';</script>'
                        '<style>.x::after { content: "<a href=/css>"; }</style><a href="/real">Real</a>')
        page, _findings = self.analyse(html)
        self.assertEqual(page["titles"], ["Fixture page"])
        self.assertEqual(page["links"], [TARGET + "real"])
        self.assertEqual(page["noindex_observations"], [])

    def test_inert_nested_template_tags_cannot_override_document_evidence(self):
        html = document('<template><title>Fake title</title><link rel="canonical" href="https://other.example/">'
                        '<a href="/template">Hidden</a><template><meta name="robots" content="noindex">'
                        '<h1>Hidden heading</h1></template></template><a href="/real">Real</a>')
        page, _findings = self.analyse(html)
        self.assertEqual(page["titles"], ["Fixture page"])
        self.assertEqual(page["canonical"], [])
        self.assertEqual(page["links"], [TARGET + "real"])
        self.assertEqual(page["noindex_observations"], [])
        self.assertEqual(page["headings"], [{"level": 1, "text": "A useful heading"}])

    def test_base_url_applies_to_relative_empty_and_fragment_links(self):
        html = document('<a href="part?x=1&amp;y=2">Part</a><a href="">Base</a><a href="#topic">Section</a>'
                        '<a href="mailto:info@example.org">Mail</a><a href="javascript:alert(1)">JS</a>',
                        head='<base href="https://example.org/docs/"><link rel="canonical" href="part">')
        page, _findings = self.analyse(html)
        self.assertEqual(page["links"], [TARGET + "docs/", TARGET + "docs/part?x=1&y=2"])
        self.assertEqual(page["canonical"], [TARGET + "docs/part"])

    def test_conflicting_and_invalid_canonicals_are_explicit(self):
        page, findings = self.analyse(document(head='<link rel="canonical" href="/one">'
                                              '<link rel="canonical" href="https://other.example/two">'
                                              '<link rel="canonical" href="javascript:alert(1)">'))
        self.assertEqual(find(findings, "canonical_single")["status"], "fail")
        self.assertEqual(find(findings, "canonical_valid_url")["status"], "fail")
        self.assertEqual(find(findings, "canonical_origin")["status"], "warning")
        self.assertEqual(len(page["canonical"]), 2)

    def test_header_and_agent_specific_meta_directives_keep_their_sources(self):
        page, findings = self.analyse(document(head='<meta name="robots" content="index,follow">'
                                              '<meta name="googlebot" content="NOINDEX">'),
                                      http_status=200, headers={"X-Robots-Tag": "bingbot: none"})
        self.assertEqual({item["source"] for item in page["noindex_observations"]},
                         {"meta:googlebot", "http:x-robots-tag"})
        self.assertEqual(find(findings, "noindex_directive")["status"], "warning")
        self.assertNotIn("indexed", page)

    def test_jsonld_syntax_is_distinct_from_eligibility(self):
        html = document('<script type="application/ld+json">{"@graph":[{"@type":"Organization"}]}</script>'
                        '<script type="application/ld+json">{"@type":"Product",bad}</script>'
                        '<script type="application/ld+json">{"value":NaN}</script>')
        page, findings = self.analyse(html)
        self.assertEqual(page["json_ld"]["types"], ["Organization"])
        self.assertEqual(len(page["json_ld"]["syntax_errors"]), 2)
        self.assertFalse(page["json_ld"]["eligibility_checked"])
        self.assertEqual(find(findings, "jsonld_syntax")["status"], "fail")

    def test_decorative_alt_and_multiple_main_headings_are_not_automatic_failures(self):
        page, findings = self.analyse(document('<h1>Another section</h1><img src="/decoration.svg" alt="">', title="A" * 100))
        self.assertEqual(page["images"]["empty_alt"], 1)
        self.assertEqual(find(findings, "image_alt_attribute")["status"], "pass")
        self.assertEqual(find(findings, "main_heading_present")["status"], "pass")
        self.assertEqual(find(findings, "title_present")["status"], "pass")

    def test_missing_alt_and_http_resources_are_observed_without_fetching(self):
        page, findings = self.analyse(document('<img src="http://assets.example/picture.png"><script src="http://assets.example/a.js"></script>'))
        self.assertEqual(page["images"]["missing_alt"], 1)
        self.assertEqual(find(findings, "image_alt_attribute")["status"], "warning")
        self.assertEqual(find(findings, "mixed_content_references")["status"], "warning")

    def test_results_are_stable_with_fixed_observation_time(self):
        first = self.analyse(document('<a href="/x">X</a>'))
        second = self.analyse(document('<a href="/x">X</a>'))
        self.assertEqual(first, second)
        for item in first[1]:
            self.assertEqual(item["evidence"]["collected_at"], STAMP)
            self.assertTrue(item["reference_url"].startswith("https://"))
            self.assertIn("recommendation", item)

    def test_link_extraction_limit_is_disclosed(self):
        page, findings = self.analyse(document("".join(f'<a href="/p/{i}">Page</a>' for i in range(2005))))
        self.assertTrue(page["extraction_limited"])
        self.assertTrue(page["links_extraction_limited"])
        self.assertFalse(page["images_extraction_limited"])
        self.assertEqual(page["discovered_link_count"], 2005)
        self.assertEqual(len(page["links"]), 2000)
        self.assertEqual(find(findings, "link_url_syntax")["status"], "not_checked")

    def test_observed_link_syntax_problem_survives_incomplete_extraction(self):
        page, findings = self.analyse(document('<a href="//[">Invalid</a>' + '<a href="/">Self</a>' * 2000))
        self.assertTrue(page["links_extraction_limited"])
        self.assertEqual(find(findings, "link_url_syntax")["status"], "warning")

    def test_image_extraction_limit_does_not_make_complete_link_syntax_unknown(self):
        page, findings = self.analyse(document('<img src="/decoration.svg" alt="">' * 2001 + '<a href="/">Self</a>'))
        self.assertTrue(page["images_extraction_limited"])
        self.assertFalse(page["links_extraction_limited"])
        self.assertEqual(find(findings, "link_url_syntax")["status"], "pass")


class OfflineTests(unittest.TestCase):
    def test_snapshot_never_fabricates_http_or_network_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "snapshot.html"
            source.write_text(document('<a href="/unvisited">Unvisited</a>'), encoding="utf-8")
            with patch("safe_http.socket.getaddrinfo", side_effect=AssertionError("Offline mode attempted DNS")):
                report = audit_offline(source, TARGET)
        self.assertEqual(report["coverage"]["requests"], 0)
        self.assertEqual(report["coverage"]["pages_analysed"], 1)
        self.assertIsNone(report["pages"][0]["http_status"])
        self.assertEqual(find(report["findings"], "http_status")["status"], "not_checked")
        self.assertEqual(find(report["findings"], "redirect_chain")["status"], "not_checked")
        self.assertEqual(find(report["findings"], "internal_link_target_response")["status"], "not_checked")
        canonical = find(report["findings"], "canonical_signal_consistency")["evidence"]
        self.assertFalse(canonical["headers_inspected"])
        self.assertIn("HTTP headers were not inspected", canonical["observation"])
        self.assertIn("Core Web Vitals", " ".join(report["checks_not_performed"]))
        self.assertIn("only", report["coverage"]["completeness_scope"])

    def test_oversized_snapshot_is_rejected_without_partial_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "large.html"
            source.write_bytes(b"<html>" + b"x" * 50)
            with self.assertRaises(FetchError) as caught:
                audit_offline(source, TARGET, max_bytes=20)
        self.assertEqual(caught.exception.code, "response_too_large")


class LiveAuditTests(unittest.TestCase):
    def audit(self, target, **options):
        return audit_live(target, allow_localhost=True, delay=0, timeout=1, max_seconds=5, **options)

    def test_missing_robots_is_not_a_critical_error(self):
        with fixture_server({"/": response(document())}) as (url, requests):
            report = self.audit(url)
        self.assertEqual(paths(requests), ["/robots.txt", "/sitemap.xml", "/"])
        self.assertEqual(report["coverage"]["pages_analysed"], 1)
        self.assertEqual(find(report["findings"], "robots_available")["status"], "not_applicable")

    def test_robots_server_error_and_html_fallback_stop_before_pages(self):
        for robots in [response("Unavailable", status=503, content_type="text/plain"), response(document())]:
            with self.subTest(status=robots[0]), fixture_server({"/robots.txt": robots, "/": response(document())}) as (url, requests):
                report = self.audit(url)
                self.assertEqual(paths(requests), ["/robots.txt"])
                self.assertEqual(report["pages"], [])
                self.assertFalse(report["coverage"]["complete"])
                self.assertEqual(find(report["findings"], "robots_available")["status"], "not_checked")

    def test_disallowed_target_is_never_fetched(self):
        with fixture_server({"/robots.txt": response("User-agent: *\nDisallow: /", content_type="text/plain"),
                             "/": response(document())}) as (url, requests):
            report = self.audit(url)
        self.assertEqual(paths(requests), ["/robots.txt"])
        self.assertIn("target_robots_disallowed", report["coverage"]["stop_reasons"])
        self.assertEqual(report["pages"], [])

    def test_explicitly_rechecked_crawl_permission_can_resolve_a_previous_block(self):
        from reporting import compare_reports

        routes = {"/robots.txt": response("User-agent: *\nDisallow: /", content_type="text/plain"),
                  "/": response(document())}
        with fixture_server(routes) as (url, requests):
            before = self.audit(url)
            self.assertEqual(find(before["findings"], "target_crawl_permission", url + "/")["status"], "warning")
            self.assertNotIn("/", paths(requests))
            routes["/robots.txt"] = response("User-agent: *\nAllow: /", content_type="text/plain")
            after = self.audit(url)
            self.assertEqual(find(after["findings"], "target_crawl_permission", url + "/")["status"], "pass")
            self.assertIn("/", paths(requests))
        comparison = compare_reports(before, after)
        resolved = {(item["rule_id"], item["url"]) for item in comparison["resolved"]}
        self.assertIn(("target_crawl_permission", url + "/"), resolved)

    def test_blocked_links_queries_and_external_origins_are_not_fetched(self):
        routes = {
            "/robots.txt": response("User-agent: *\nDisallow: /private\nDisallow: /*?sort=*", content_type="text/plain"),
            "/": response(document('<a href="/private">Private</a><a href="/public">Public</a>'
                                    '<a href="/view?sort=price">Sort</a><a href="http://169.254.169.254/">External</a>')),
            "/public": response(document(title="Public")),
        }
        with fixture_server(routes) as (url, requests):
            report = self.audit(url)
        self.assertEqual(paths(requests), ["/robots.txt", "/sitemap.xml", "/", "/public"])
        self.assertEqual(report["coverage"]["pages_analysed"], 2)
        blocked = [item for item in report["coverage"]["skipped"] if item["reason"] == "robots_disallowed"]
        self.assertEqual(len(blocked), 2)
        self.assertFalse(report["coverage"]["complete"])

    def test_page_limit_keeps_unvisited_destinations_not_checked(self):
        with fixture_server({"/": response(document('<a href="/two">Two</a><a href="/three">Three</a>'))}) as (url, requests):
            report = self.audit(url, max_pages=1)
        self.assertEqual(report["coverage"]["pages_analysed"], 1)
        self.assertIn("page_limit", report["coverage"]["stop_reasons"])
        self.assertFalse(report["coverage"]["complete"])
        target_check = find(report["findings"], "internal_link_target_response", url + "/")
        self.assertEqual(target_check["status"], "not_checked")
        self.assertEqual(set(target_check["evidence"]["unverified_urls"]), {url + "/two", url + "/three"})
        self.assertNotIn("/two", paths(requests))

    def test_omitted_broken_link_cannot_resolve_a_previous_observed_failure(self):
        from reporting import compare_reports

        routes = {"/": response(document('<a href="/broken">Broken</a>')),
                  "/broken": response("Not found", status=404, content_type="text/plain")}
        with fixture_server(routes) as (url, requests):
            before = self.audit(url)
            previous = find(before["findings"], "internal_link_target_response", url + "/")
            self.assertEqual(previous["status"], "warning")
            self.assertEqual(previous["evidence"]["related_urls"], [url + "/broken"])
            # The retained sample can look healthy or contain no HTTP links at
            # all. Neither permits resolving an unchanged, omitted broken link.
            for retained_href in ("/", "mailto:info@example.org"):
                with self.subTest(retained_href=retained_href):
                    routes["/"] = response(document(f'<a href="{retained_href}">Retained</a>' * 2000
                                                    + '<a href="/broken">Broken</a>'))
                    requests.clear()
                    after = self.audit(url)
                    current = find(after["findings"], "internal_link_target_response", url + "/")
                    self.assertEqual(current["status"], "not_checked")
                    self.assertTrue(current["evidence"]["links_extraction_limited"])
                    self.assertEqual(find(after["findings"], "link_url_syntax", url + "/")["status"], "not_checked")
                    self.assertNotIn("/broken", paths(requests))
                    comparison = compare_reports(before, after)
                    key = lambda item: (item["rule_id"], item["url"])
                    expected = ("internal_link_target_response", url + "/")
                    self.assertIn(expected, {key(item) for item in comparison["not_rechecked"]})
                    self.assertNotIn(expected, {key(item) for item in comparison["resolved"]})

    def test_observed_broken_link_stays_warning_when_other_links_are_omitted(self):
        routes = {"/": response(document('<a href="/broken">Broken</a>' + '<a href="/">Self</a>' * 2000)),
                  "/broken": response("Not found", status=404, content_type="text/plain")}
        with fixture_server(routes) as (url, _requests):
            report = self.audit(url)
        current = find(report["findings"], "internal_link_target_response", url + "/")
        self.assertEqual(current["status"], "warning")
        self.assertTrue(current["evidence"]["links_extraction_limited"])
        self.assertEqual(current["evidence"]["related_urls"], [url + "/broken"])

    def test_depth_and_request_limits_preserve_partial_coverage(self):
        routes = {"/": response(document('<a href="/two">Two</a>')), "/two": response(document())}
        with fixture_server(routes) as (url, requests):
            report = self.audit(url, max_depth=0)
            self.assertEqual(report["coverage"]["pages_analysed"], 1)
            self.assertIn("depth_limit", report["coverage"]["stop_reasons"])
            self.assertNotIn("/two", paths(requests))
        with fixture_server(routes) as (url, requests):
            report = self.audit(url, max_requests=3)
            self.assertEqual(len(requests), 3)
            self.assertEqual(report["coverage"]["requests"], 3)
            self.assertIn("request_budget", report["coverage"]["stop_reasons"])

    def test_rate_limit_stops_without_requesting_later_queued_pages(self):
        routes = {"/": response(document('<a href="/a-rate">Rate</a><a href="/z-after">Later</a>')),
                  "/a-rate": response("Rate limit", status=429), "/z-after": response(document())}
        with fixture_server(routes) as (url, requests):
            report = self.audit(url)
        self.assertEqual(paths(requests), ["/robots.txt", "/sitemap.xml", "/", "/a-rate"])
        self.assertIn("rate_limited", report["coverage"]["stop_reasons"])
        self.assertEqual(report["coverage"]["pages_analysed"], 1)
        self.assertEqual(find(report["findings"], "resource_retrieval", url + "/a-rate")["status"], "not_checked")
        self.assertFalse(any(item["url"] == url + "/a-rate" and item["rule_id"] == "title_present" for item in report["findings"]))

    def test_access_denied_pages_are_unavailable_not_bad_html(self):
        for status in (401, 403, 407):
            with self.subTest(status=status), fixture_server({"/": response("Access denied", status=status)}) as (url, _requests):
                report = self.audit(url)
                self.assertEqual(report["pages"], [])
                self.assertIn("access_denied", report["coverage"]["stop_reasons"])
                self.assertFalse(any(item["rule_id"] == "title_present" for item in report["findings"]))

    def test_canonical_404_has_observed_target_evidence(self):
        with fixture_server({"/": response(document(head='<link rel="canonical" href="/missing">')),
                             "/missing": response(document(title="Not found"), status=404)}) as (url, _requests):
            report = self.audit(url)
        target_check = find(report["findings"], "canonical_target_response", url + "/")
        self.assertEqual(target_check["status"], "warning")
        self.assertEqual(target_check["evidence"]["destination_observations"][0]["http_status"], 404)
        self.assertEqual(target_check["evidence"]["related_urls"], [url + "/missing"])

    def test_canonical_noindex_and_link_redirect_are_checked_after_crawl(self):
        routes = {"/": response(document('<a href="/old">Old</a>', head='<link rel="canonical" href="/target">')),
                  "/old": (301, {"Location": "/target"}, ""),
                  "/target": response(document(head='<meta name="robots" content="noindex">', title="Target"))}
        with fixture_server(routes) as (url, _requests):
            report = self.audit(url)
        self.assertEqual(find(report["findings"], "internal_link_target_response", url + "/")["status"], "warning")
        self.assertEqual(find(report["findings"], "canonical_target_response", url + "/")["status"], "pass")
        self.assertEqual(find(report["findings"], "canonical_target_noindex", url + "/")["status"], "warning")

    def test_duplicates_describe_only_the_observed_sample(self):
        routes = {"/": response(document('<a href="/other">Other</a>')), "/other": response(document())}
        with fixture_server(routes) as (url, _requests):
            report = self.audit(url)
        duplicate = find(report["findings"], "duplicate_title", url + "/")
        self.assertEqual(duplicate["status"], "warning")
        self.assertEqual(duplicate["evidence"]["related_urls"], [url + "/other"])
        self.assertEqual(set(duplicate["evidence"]["comparison_scope_urls"]), {url + "/", url + "/other"})

    def test_sitemap_discovers_pages_and_checks_noindex_consistency(self):
        def sitemap(_path, root):
            return response(f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{root}/listed</loc></url></urlset>', content_type="application/xml")

        routes = {"/": response(document()), "/sitemap.xml": sitemap,
                  "/listed": response(document(head='<meta name="robots" content="noindex">', title="Listed"))}
        with fixture_server(routes) as (url, requests):
            report = self.audit(url)
        self.assertIn("/listed", paths(requests))
        self.assertEqual(find(report["findings"], "sitemap_url_noindex", url + "/listed")["status"], "warning")

    def test_sitemap_ignores_off_origin_and_extension_metadata_locations(self):
        def sitemap(_path, root):
            xml = (f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="urn:image">'
                   f'<url><loc>{root}/listed</loc><image:image><image:loc>{root}/image-only</image:loc></image:image></url>'
                   '<url><loc>http://169.254.169.254/secret</loc></url></urlset>')
            return response(xml, content_type="application/xml")

        with fixture_server({"/": response(document()), "/sitemap.xml": sitemap,
                             "/listed": response(document(title="Listed"))}) as (url, requests):
            report = self.audit(url)
        self.assertIn("/listed", paths(requests))
        self.assertNotIn("/image-only", paths(requests))
        self.assertTrue(all(item.startswith(url) for item in report["coverage"]["discovered_urls"]))

    def test_sitemap_dtd_and_utf16_entity_declarations_are_rejected(self):
        xml = '<!DOCTYPE urlset [<!ENTITY leak SYSTEM "file:///etc/passwd">]><urlset><url><loc>&leak;</loc></url></urlset>'
        for payload in (xml.encode("utf-8"), xml.encode("utf-16")):
            with self.subTest(encoding=payload[:2]), fixture_server({"/": response(document()),
                "/sitemap.xml": response(payload, content_type="application/xml")}) as (url, requests):
                report = self.audit(url)
                errors = [item for item in report["coverage"]["sitemaps"] if item.get("status") == "not_checked"]
                self.assertTrue(any("DTD/entity" in item.get("reason", "") for item in errors))
                self.assertEqual(paths(requests), ["/robots.txt", "/sitemap.xml", "/"])

    def test_search_and_training_robots_decisions_remain_separate(self):
        robots = "User-agent: OAI-SearchBot\nAllow: /\nUser-agent: GPTBot\nDisallow: /\n"
        with fixture_server({"/robots.txt": response(robots, content_type="text/plain"), "/": response(document())}) as (url, _requests):
            report = self.audit(url)
        decisions = report["coverage"]["robots"]["target_path_decisions"]
        self.assertTrue(decisions["OAI-SearchBot"])
        self.assertFalse(decisions["GPTBot"])
        self.assertTrue(decisions["EWebCitySEO"])


if __name__ == "__main__":
    unittest.main()
