"""Network-boundary regressions; every real request stays on explicit loopback."""
from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "ewebcity-seo-optimizer" / "scripts"))
from safe_http import BudgetExceeded, FetchError, RobotsPolicy, SafeClient, normalise_url, origin, resolve_public_addresses


@contextmanager
def fixture_server(routes):
    """Serve controlled responses and retain the actual requested paths/headers."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"path": self.path, "headers": dict(self.headers), "time": time.monotonic()})
            item = routes.get(self.path, (404, {"Content-Type": "text/plain"}, b"Not found"))
            if callable(item):
                item = item(self.path, f"http://127.0.0.1:{self.server.server_port}")
            status, headers, body = item
            body = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            for name, value in headers.items():
                for item_value in value if isinstance(value, list) else [value]:
                    self.send_header(name, item_value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when the timeout/byte-limit tests close early.

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)


def dns_records(*addresses):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM,
             socket.IPPROTO_TCP, "", (address, 443)) for address in addresses]


class URLTests(unittest.TestCase):
    def test_normalises_identity_but_preserves_query_semantics(self):
        self.assertEqual(normalise_url("HTTPS://Example.ORG:443/a?b=2&a=1#part"),
                         "https://example.org/a?b=2&a=1")
        self.assertEqual(normalise_url("../other?q=x&y=2", "https://example.org/dir/page"),
                         "https://example.org/other?q=x&y=2")
        self.assertEqual(normalise_url("https://BÜCHER.example/über?q=A B"),
                         "https://xn--bcher-kva.example/%C3%BCber?q=A%20B")
        self.assertEqual(origin("https://example.org:8443/a"), "https://example.org:8443")

    def test_rejects_non_web_credentials_and_ambiguous_urls(self):
        for url in ["file:///etc/passwd", "ftp://example.org/a", "https://user:pass@example.org/",
                    "https://user@example.org/", "https://example.org/\nX: evil", "https://example.org\\evil/",
                    "http://[fe80::1%25eth0]/", "https://example.org:0/", "https://example.org:65536/", "//example.org/"]:
            with self.subTest(url=url), self.assertRaises(FetchError) as caught:
                normalise_url(url)
            self.assertEqual(caught.exception.code, "invalid_url")


class DNSBoundaryTests(unittest.TestCase):
    def test_accepts_only_public_addresses_and_deduplicates(self):
        with patch("safe_http.socket.getaddrinfo", return_value=dns_records("93.184.216.34", "93.184.216.34", "2001:4860:4860::8888")):
            result = resolve_public_addresses("example.org", 443)
        self.assertEqual(len(result), 2)

    def test_rejects_private_special_multicast_and_mapped_addresses(self):
        for address in ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
                        "0.0.0.0", "224.0.0.1", "100.64.0.1", "::1", "fc00::1", "fe80::1", "ff02::1", "::ffff:127.0.0.1"]:
            with self.subTest(address=address), patch("safe_http.socket.getaddrinfo", return_value=dns_records(address)):
                with self.assertRaises(FetchError) as caught:
                    resolve_public_addresses("example.org", 443)
                self.assertEqual(caught.exception.code, "non_public_address")

    def test_mixed_dns_is_rejected_even_when_first_address_is_public(self):
        with patch("safe_http.socket.getaddrinfo", return_value=dns_records("93.184.216.34", "127.0.0.1")):
            with self.assertRaises(FetchError) as caught:
                resolve_public_addresses("example.org", 443)
        self.assertEqual(caught.exception.code, "non_public_address")

    def test_localhost_exception_is_explicit_and_cannot_bless_other_hosts(self):
        with patch("safe_http.socket.getaddrinfo", return_value=dns_records("127.0.0.1")):
            self.assertEqual(resolve_public_addresses("localhost", 8080, allow_localhost=True), [(socket.AF_INET, "127.0.0.1")])
            for host, allowed in [("localhost", False), ("example.org", True)]:
                with self.subTest(host=host, allowed=allowed), self.assertRaises(FetchError):
                    resolve_public_addresses(host, 8080, allow_localhost=allowed)
        with patch("safe_http.socket.getaddrinfo", return_value=dns_records("10.0.0.1")):
            with self.assertRaises(FetchError):
                resolve_public_addresses("localhost", 8080, allow_localhost=True)

    def test_dns_errors_empty_results_and_timeout_are_not_success(self):
        with patch("safe_http.socket.getaddrinfo", side_effect=socket.gaierror("fixture failure")):
            with self.assertRaises(FetchError) as caught:
                resolve_public_addresses("example.org", 443)
            self.assertEqual(caught.exception.code, "dns_error")
        with patch("safe_http.socket.getaddrinfo", return_value=[]):
            with self.assertRaises(FetchError):
                resolve_public_addresses("example.org", 443)

        def delayed(*_args, **_kwargs):
            time.sleep(0.03)
            return dns_records("93.184.216.34")

        with patch("safe_http.socket.getaddrinfo", side_effect=delayed):
            with self.assertRaises(BudgetExceeded) as caught:
                resolve_public_addresses("example.org", 443, timeout=0.005)
            self.assertEqual(caught.exception.code, "dns_timeout")


class RobotsTests(unittest.TestCase):
    def test_specific_groups_override_wildcard_and_equal_groups_merge(self):
        policy = RobotsPolicy("""User-agent: *
Disallow: /
User-agent: EWebCitySEO
Disallow: /private
Allow: /private/public
User-agent: EWebCitySEO
Disallow: /second
""")
        self.assertTrue(policy.can_fetch("https://example.org/"))
        self.assertFalse(policy.can_fetch("https://example.org/private/data"))
        self.assertTrue(policy.can_fetch("https://example.org/private/public/data"))
        self.assertFalse(policy.can_fetch("https://example.org/second"))
        self.assertFalse(policy.can_fetch("https://example.org/", "Googlebot"))

    def test_allow_wins_equal_specificity_and_empty_disallow_is_permissive(self):
        policy = RobotsPolicy("User-agent: *\nDisallow:\nDisallow: /same\nAllow: /same\n")
        self.assertTrue(policy.can_fetch("https://example.org/"))
        self.assertTrue(policy.can_fetch("https://example.org/same/path"))

    def test_wildcards_terminal_marker_and_query_are_distinct(self):
        policy = RobotsPolicy("User-agent: *\nDisallow: /*?sort=*\nDisallow: /download$\nDisallow: /a*b*c$\n")
        for path, permitted in [("/?sort=price", False), ("/products?sort=date&x=1", False),
                                ("/download", False), ("/download?key=1", True), ("/downloads", True),
                                ("/a12b34c", False), ("/a12b34c/more", True)]:
            with self.subTest(path=path):
                self.assertEqual(policy.can_fetch("https://example.org" + path), permitted)

    def test_encoded_unreserved_unicode_and_reserved_paths(self):
        policy = RobotsPolicy("User-agent: *\nDisallow: /private/\nDisallow: /café\n")
        self.assertFalse(policy.can_fetch("https://example.org/%70rivate/file"))
        self.assertFalse(policy.can_fetch("https://example.org/caf%C3%A9"))
        self.assertTrue(policy.can_fetch("https://example.org/private%2Ffile"))

    def test_search_and_training_preferences_are_independent(self):
        policy = RobotsPolicy("User-agent: OAI-SearchBot\nAllow: /\nUser-agent: GPTBot\nDisallow: /\n")
        self.assertTrue(policy.can_fetch("https://example.org/", "OAI-SearchBot"))
        self.assertFalse(policy.can_fetch("https://example.org/", "GPTBot"))
        self.assertTrue(policy.can_fetch("https://example.org/", "EWebCitySEO"))

    def test_crawl_delay_and_parser_limits(self):
        policy = RobotsPolicy("\ufeffUser-agent: EWebCitySEO\nCrawl-delay: 0.5\nSitemap: https://example.org/sitemap.xml\n")
        self.assertEqual(policy.crawl_delay(), 0.5)
        self.assertEqual(policy.sitemaps, ["https://example.org/sitemap.xml"])
        with self.assertRaises(FetchError):
            RobotsPolicy("User-agent: *\nDisallow: /" + "x" * 8200)
        with self.assertRaises(FetchError):
            RobotsPolicy("#\n" * 10001)


class HTTPBoundaryTests(unittest.TestCase):
    def test_repeated_robot_headers_preserve_field_boundaries(self):
        with fixture_server({"/": (200, {
            "Content-Type": "text/html",
            "X-Robots-Tag": ["googlebot: noindex", "nofollow"],
        }, "<title>Example</title>")}) as (base, _requests):
            response = SafeClient(base, allow_localhost=True, delay=0).fetch(base + "/")
        self.assertEqual(response.header_values["x-robots-tag"], ["googlebot: noindex", "nofollow"])
        self.assertEqual(response.headers["x-robots-tag"], "googlebot: noindex, nofollow")

    def client(self, url, **options):
        return SafeClient(url, allow_localhost=True, delay=0, **options)

    def test_loopback_is_denied_by_default_without_making_a_request(self):
        with fixture_server({"/": (200, {"Content-Type": "text/html"}, "ok")}) as (url, requests):
            with self.assertRaises(FetchError) as caught:
                SafeClient(url, delay=0).fetch(url)
            self.assertEqual(caught.exception.code, "non_public_address")
            self.assertEqual(requests, [])

    def test_success_pins_one_dns_resolution_and_sends_no_credentials(self):
        with fixture_server({"/": (200, {"Content-Type": "text/plain"}, "complete response")}) as (url, requests):
            real_resolver = socket.getaddrinfo
            with patch("safe_http.socket.getaddrinfo", wraps=real_resolver) as resolver:
                response = self.client(url).fetch(url)
            self.assertEqual(resolver.call_count, 1)
            self.assertEqual(response.body, b"complete response")
            self.assertEqual(response.status, 200)
            self.assertEqual(requests[0]["headers"]["Accept-Encoding"], "identity")
            self.assertNotIn("Cookie", requests[0]["headers"])
            self.assertNotIn("Authorization", requests[0]["headers"])

    def test_same_origin_redirect_records_chain(self):
        with fixture_server({"/": (302, {"Location": "/final"}, ""), "/final": (200, {}, "ok")}) as (url, requests):
            response = self.client(url).fetch(url)
            self.assertEqual(response.url, url + "/final")
            self.assertEqual(response.requested_url, url + "/")
            self.assertEqual(len(response.redirects), 1)
            self.assertEqual([item["path"] for item in requests], ["/", "/final"])

    def test_redirect_to_private_or_other_origin_is_stopped_before_fetch(self):
        for location in ["http://169.254.169.254/latest/meta-data/", "https://example.org/", "http://user:pass@example.org/"]:
            with self.subTest(location=location), fixture_server({"/": (302, {"Location": location}, "")}) as (url, requests):
                with self.assertRaises(FetchError):
                    self.client(url).fetch(url)
                self.assertEqual([item["path"] for item in requests], ["/"])

    def test_redirect_is_checked_against_robots_before_following(self):
        with fixture_server({"/": (302, {"Location": "/private"}, ""), "/private": (200, {}, "secret")}) as (url, requests):
            with self.assertRaises(FetchError) as caught:
                self.client(url).fetch(url, allowed=lambda target: not target.endswith("/private"))
            self.assertEqual(caught.exception.code, "robots_disallowed")
            self.assertEqual([item["path"] for item in requests], ["/"])

    def test_redirect_loop_and_redirect_limit_are_bounded(self):
        with fixture_server({"/": (302, {"Location": "/again"}, ""), "/again": (302, {"Location": "/"}, "")}) as (url, requests):
            with self.assertRaises(FetchError) as caught:
                self.client(url).fetch(url)
            self.assertEqual(caught.exception.code, "redirect_loop")
            self.assertEqual(len(requests), 2)
        routes = {f"/{i}": (302, {"Location": f"/{i + 1}"}, "") for i in range(10)}
        with fixture_server(routes) as (url, requests):
            with self.assertRaises(FetchError) as caught:
                self.client(url).fetch(url + "/0")
            self.assertEqual(caught.exception.code, "redirect_limit")
            self.assertEqual(len(requests), 6)

    def test_request_and_response_byte_budgets(self):
        with fixture_server({"/": (200, {}, "x" * 100)}) as (url, requests):
            client = self.client(url, max_requests=1)
            client.fetch(url)
            with self.assertRaises(BudgetExceeded) as caught:
                client.fetch(url)
            self.assertEqual(caught.exception.code, "request_budget")
            self.assertEqual(len(requests), 1)
            with self.assertRaises(FetchError) as caught:
                self.client(url, max_bytes=32, max_total_bytes=1000).fetch(url)
            self.assertEqual(caught.exception.code, "response_too_large")
            with self.assertRaises(BudgetExceeded) as caught:
                self.client(url, max_bytes=1000, max_total_bytes=32).fetch(url)
            self.assertEqual(caught.exception.code, "byte_budget")

    def test_compressed_responses_are_not_unboundedly_decompressed(self):
        with fixture_server({"/": (200, {"Content-Encoding": "gzip"}, b"not important")}) as (url, requests):
            with self.assertRaises(FetchError) as caught:
                self.client(url).fetch(url)
            self.assertEqual(caught.exception.code, "unsupported_encoding")
            self.assertEqual(len(requests), 1)

    def test_timeout_and_total_time_budget(self):
        def slow(_path, _origin):
            time.sleep(0.15)
            return 200, {}, "late"

        with fixture_server({"/": slow}) as (url, _requests):
            with self.assertRaises(FetchError) as caught:
                self.client(url, timeout=0.03).fetch(url)
            self.assertEqual(caught.exception.code, "request_timeout")
            with self.assertRaises(BudgetExceeded) as caught:
                self.client(url, max_seconds=0).fetch(url)
            self.assertEqual(caught.exception.code, "time_budget")

    def test_configured_delay_is_observed_between_requests(self):
        with fixture_server({"/": (200, {}, "ok")}) as (url, requests):
            client = SafeClient(url, allow_localhost=True, delay=0.04)
            client.fetch(url)
            client.fetch(url)
            self.assertGreaterEqual(requests[1]["time"] - requests[0]["time"], 0.025)


if __name__ == "__main__":
    unittest.main()
