"""Offline snapshot and mocked pinned-HTTPS WordPress connector regressions."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "ewebcity-seo-optimizer" / "scripts"))
from safe_http import FetchError
from wordpress import MAX_FILE_BYTES, METADATA_SEMANTICS, fetch_wordpress_evidence, load_wordpress_evidence


TARGET = "https://example.org/article/"
ENDPOINT = "https://example.org/wp-json/ewebcity/v1/snapshot"
USERNAME = "fixture-connector-user"
PASSWORD = "AbCd EfGh IjKl MnOp QrSt UvWx"


def snapshot() -> dict:
    return {"format": "ewebcity-wordpress-snapshot", "schema_version": "1.0", "bridge_version": "2.2.0",
        "generated_at": "2026-11-12T12:00:00Z", "auditor": "Mahim", "metadata_semantics": METADATA_SEMANTICS,
        "site": {"home_url": "https://example.org/", "site_url": "https://example.org/wordpress/",
            "search_visibility": "allow", "permalink_structure": "/%postname%/"},
        "providers": [{"id": "yoast", "active": True, "version": "26.0"}],
        "pagination": {"page": 1, "per_page": 20, "total_posts": 1, "total_pages": 1},
        "posts": [{"id": 7, "type": "page", "url": TARGET, "modified_gmt": "2026-11-11T10:30:00Z",
            "metadata": {"yoast": {"title": "%%title%% | Example", "description": None,
                "canonical": "../saved-canonical/", "robots_noindex": "0", "robots_nofollow": None,
                "robots_advanced": None}}, "truncated_fields": [], "omitted_fields": []}]}


class SnapshotImportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "snapshot.json"

    def load(self, data=None, *, body=None, target=TARGET):
        if body is None:
            body = json.dumps(snapshot() if data is None else data, ensure_ascii=False).encode()
        self.path.write_bytes(body)
        return load_wordpress_evidence(self.path, target)

    def test_local_import_has_provenance_and_never_connects(self):
        data = snapshot()
        data["unknown_authentication"] = {"Authorization": "not-to-be-retained"}
        data["posts"][0]["author_email"] = "private@example.org"
        data["posts"][0]["metadata"]["yoast"]["unknown_key"] = "ignored"
        with patch("wordpress.resolve_public_addresses") as resolver, patch("wordpress._PinnedConnection") as connection:
            result = self.load(data)
        resolver.assert_not_called()
        connection.assert_not_called()
        self.assertEqual(result["mode"], "offline_snapshot")
        self.assertEqual(result["snapshot_auditor"], "Mahim")
        self.assertNotIn("auditor", result)
        self.assertTrue(result["coverage"]["complete"])
        self.assertEqual(result["provenance"]["input_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(result["provenance"]["byte_count"], self.path.stat().st_size)
        self.assertEqual(result["provenance"]["input_file"], "snapshot.json")
        self.assertIsNone(result["provenance"]["source_url"])
        self.assertTrue(result["provenance"]["collected_at"].endswith("Z"))
        self.assertTrue(result["provenance"]["file_modified_at"].endswith("Z"))
        for value in ("not-to-be-retained", "private@example.org", "unknown_key"):
            self.assertNotIn(value, json.dumps(result))
        self.assertNotIn("findings", result)

    def test_provider_overrides_are_raw_and_nullable(self):
        result = self.load()
        values = result["posts"][0]["metadata"]["yoast"]
        self.assertEqual(values["title"], "%%title%% | Example")
        self.assertEqual(values["canonical"], "../saved-canonical/")
        self.assertEqual(values["robots_noindex"], "0")
        self.assertIsNone(values["description"])
        self.assertEqual(result["metadata_semantics"], METADATA_SEMANTICS)
        self.assertIn("not resolved frontend", result["note"])

    def test_rank_math_and_two_active_providers_remain_explicit(self):
        data = snapshot()
        data["providers"].append({"id": "rankmath", "active": True, "version": "1.0.250"})
        data["posts"][0]["metadata"]["rankmath"] = {"title": None, "description": "Saved description",
            "canonical": "%%custom_variable%%", "robots": ["noindex", "nofollow"]}
        result = self.load(data)
        self.assertEqual(result["posts"][0]["metadata"]["rankmath"]["robots"], ["noindex", "nofollow"])
        self.assertEqual(result["provider_status"], {"yoast": "active", "rankmath": "active"})
        self.assertTrue(any("Both Yoast and Rank Math" in value for value in result["issues"]))

    def test_absent_provider_is_not_inferred_inactive(self):
        data = snapshot()
        data["providers"] = []
        data["posts"][0]["metadata"] = {}
        result = self.load(data)
        self.assertEqual(result["provider_status"], {"yoast": "not_reported", "rankmath": "not_reported"})
        self.assertTrue(any("unverified" in value for value in result["issues"]))

    def test_missing_provider_version_remains_unknown(self):
        data = snapshot()
        data["providers"][0]["version"] = ""
        result = self.load(data)
        self.assertEqual(result["providers"][0]["version"], "")
        self.assertEqual(result["provider_status"]["yoast"], "active")
        self.assertTrue(any("version was unavailable" in value for value in result["issues"]))

    def test_missing_active_metadata_and_diagnostics_are_disclosed(self):
        data = snapshot()
        data["posts"][0]["metadata"] = {}
        data["posts"][0]["truncated_fields"] = ["yoast.title"]
        data["posts"][0]["omitted_fields"] = ["yoast.robots_advanced"]
        result = self.load(data)
        self.assertTrue(any("absent" in value for value in result["issues"]))
        self.assertTrue(any("truncated or omitted" in value for value in result["issues"]))
        self.assertEqual(result["posts"][0]["truncated_fields"], ["yoast.title"])

    def test_partial_page_does_not_claim_complete_coverage(self):
        data = snapshot()
        data["pagination"] = {"page": 2, "per_page": 1, "total_posts": 3, "total_pages": 3}
        result = self.load(data)
        self.assertFalse(result["coverage"]["complete"])
        self.assertEqual(result["coverage"]["posts_imported"], 1)
        self.assertEqual(result["coverage"]["total_posts_reported"], 3)
        self.assertTrue(any("no additional pages were fetched" in value for value in result["issues"]))

    def test_zero_post_snapshot_has_bounded_empty_coverage(self):
        data = snapshot()
        data["posts"] = []
        data["pagination"].update(total_posts=0, total_pages=0)
        result = self.load(data)
        self.assertTrue(result["coverage"]["complete"])
        self.assertEqual(result["coverage"]["posts_imported"], 0)

    def test_demonstration_and_discourage_setting_are_visible(self):
        data = snapshot()
        data["_demonstration"] = True
        data["site"]["search_visibility"] = "discourage"
        result = self.load(data)
        self.assertTrue(result["_demonstration"])
        self.assertTrue(result["note"].startswith("DEMONSTRATION DATA"))
        self.assertTrue(any("not evidence of a live" in value for value in result["issues"]))
        self.assertTrue(any("discourage search engines" in value for value in result["issues"]))

    def test_external_site_url_is_a_setting_and_never_a_fetch_target(self):
        data = snapshot()
        data["site"]["site_url"] = "https://admin.example.org/wordpress/"
        result = self.load(data)
        self.assertTrue(any("was not contacted" in value for value in result["issues"]))

    def test_rejects_duplicate_keys_and_non_finite_json_even_in_unknown_fields(self):
        overflow = json.dumps(snapshot()).encode()[:-1] + b', "ignored": 1e999}'
        for body in (b'{"format":"a","format":"b"}', b'{"unused":NaN}', b'{"unused":Infinity}', b'{"unused":-Infinity}', overflow):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.load(body=body)

    def test_rejects_bad_utf8_json_and_deeply_nested_json(self):
        for body in (b"\xff", b"{", b"[]", b'"text"', b"[" * 2000 + b"0" + b"]" * 2000):
            with self.subTest(length=len(body)), self.assertRaises(ValueError):
                self.load(body=body)

    def test_rejects_nonregular_missing_empty_and_oversized_files(self):
        with self.assertRaises(ValueError):
            load_wordpress_evidence(self.path, TARGET)
        with self.assertRaises(ValueError):
            load_wordpress_evidence(Path(self.directory.name), TARGET)
        for size in (0, MAX_FILE_BYTES + 1):
            with self.path.open("wb") as stream:
                stream.truncate(size)
            with self.subTest(size=size), self.assertRaises(ValueError):
                load_wordpress_evidence(self.path, TARGET)
        if hasattr(os, "mkfifo"):
            self.path.unlink()
            os.mkfifo(self.path)
            with self.assertRaises(ValueError):
                load_wordpress_evidence(self.path, TARGET)

    def test_rejects_bad_home_and_post_origins_credentials_and_fragments(self):
        for bad_url in ("https://other.example/", "http://example.org/", "https://example.org:8443/",
                        "https://user:password@example.org/", "https://example.org/#hidden", "file:///etc/passwd"):
            for field in ("home", "post"):
                data = snapshot()
                if field == "home":
                    data["site"]["home_url"] = bad_url
                else:
                    data["posts"][0]["url"] = bad_url
                with self.subTest(url=bad_url, field=field), self.assertRaises(ValueError):
                    self.load(data)

    def test_url_limits_apply_to_utf8_bytes_before_normalisation(self):
        for field in ("home", "site", "post"):
            data = snapshot()
            value = "https://example.org/" + "é" * 4096
            if field in ("home", "site"):
                data["site"][field + "_url"] = value
            else:
                data["posts"][0]["url"] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load(data)

    def test_offline_same_origin_loopback_is_not_contacted(self):
        data = snapshot()
        data["site"].update(home_url="http://127.0.0.1/", site_url="http://127.0.0.1/")
        data["posts"][0]["url"] = "http://127.0.0.1/article/"
        with patch("wordpress.resolve_public_addresses") as resolver:
            result = self.load(data, target="http://127.0.0.1/")
        resolver.assert_not_called()
        self.assertEqual(result["posts"][0]["url"], "http://127.0.0.1/article/")

    def test_rejects_wrong_schema_types_provider_state_and_timestamp(self):
        mutations = [
            lambda d: d.update(format="another-format"),
            lambda d: d.update(schema_version="2.0"),
            lambda d: d.update(generated_at="2026-11-12T12:00:00"),
            lambda d: d.update(generated_at="2026-02-31T12:00:00Z"),
            lambda d: d.update(generated_at="2026-11-12T12:00:00+01:00"),
            lambda d: d.update(_demonstration="true"),
            lambda d: d.update(metadata_semantics="rendered"),
            lambda d: d["providers"][0].update(active=False),
            lambda d: d["providers"][0].update(active=1),
            lambda d: d["providers"][0].update(id="unknown"),
            lambda d: d["providers"].append(deepcopy(d["providers"][0])),
            lambda d: d["site"].update(search_visibility=True),
            lambda d: d["posts"][0].update(id=True),
            lambda d: d["posts"][0].update(type="page/script"),
            lambda d: d["posts"][0]["metadata"]["yoast"].update(robots_noindex=True),
            lambda d: d["posts"][0]["metadata"]["yoast"].update(title={"value": "invalid"}),
            lambda d: d["posts"][0]["metadata"]["yoast"].pop("title"),
            lambda d: d["posts"][0].update(omitted_fields=["private.password"]),
            lambda d: d["posts"][0].update(truncated_fields=["yoast.title", "yoast.title"]),
        ]
        for index, mutate in enumerate(mutations):
            data = snapshot()
            mutate(data)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.load(data)

    def test_rejects_invalid_pagination_and_post_counts(self):
        mutations = [
            lambda d: d["pagination"].update(page=0),
            lambda d: d["pagination"].update(page=101),
            lambda d: d["pagination"].update(page=True),
            lambda d: d["pagination"].update(per_page=101),
            lambda d: d["pagination"].update(total_posts=-1),
            lambda d: d["pagination"].update(total_pages=2),
            lambda d: d["posts"].append(deepcopy(d["posts"][0])),
        ]
        for index, mutate in enumerate(mutations):
            data = snapshot()
            mutate(data)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.load(data)
        data = snapshot()
        data["pagination"].update(total_posts=2)
        data["posts"].append(deepcopy(data["posts"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate post"):
            self.load(data)

    def test_text_bounds_are_utf8_bytes_and_surrogates_cannot_escape(self):
        for value in ("x" * 8193, "é" * 4097, "\ud800", "invalid\x00text"):
            data = snapshot()
            data["posts"][0]["metadata"]["yoast"]["title"] = value
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                self.load(body=json.dumps(data).encode())
        data = snapshot()
        data["posts"][0]["metadata"]["yoast"]["title"] = "é" * 4096
        self.assertEqual(len(self.load(data)["posts"][0]["metadata"]["yoast"]["title"]), 4096)

    def test_rank_math_robots_requires_a_bounded_list_of_strings(self):
        data = snapshot()
        data["providers"] = [{"id": "rankmath", "active": True, "version": "1.0.250"}]
        for robots in (None, "noindex", [True], ["x"] * 33):
            data["posts"][0]["metadata"] = {"rankmath": {"title": None, "description": None, "canonical": None, "robots": robots}}
            with self.subTest(robots=robots), self.assertRaises(ValueError):
                self.load(data)
        data["posts"][0]["metadata"]["rankmath"]["robots"] = []
        self.assertEqual(self.load(data)["posts"][0]["metadata"]["rankmath"]["robots"], [])


class FakeResponse:
    def __init__(self, body=None, *, status=200, headers=None):
        body = json.dumps(snapshot()).encode() if body is None else body
        self.status = status
        self.headers = [("Content-Type", "application/json; charset=UTF-8"), ("Content-Length", str(len(body)))] if headers is None else headers
        self.buffer = io.BytesIO(body)
        self.read_calls = 0
        self.closed = False

    def getheaders(self):
        return self.headers

    def read(self, amount):
        self.read_calls += 1
        return self.buffer.read(amount)

    def close(self):
        self.closed = True


class AuthenticatedReaderTests(unittest.TestCase):
    def call(self, response=None, endpoint=ENDPOINT, *, timeout=10, username=USERNAME, password=PASSWORD):
        response = FakeResponse() if response is None else response
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch("wordpress.resolve_public_addresses", return_value=[(socket.AF_INET, "93.184.216.34")]) as resolver, \
                patch("wordpress._PinnedConnection", return_value=connection) as constructor:
            result = fetch_wordpress_evidence(endpoint, TARGET, username, password, timeout=timeout)
        return result, connection, resolver, constructor, response

    def test_exactly_one_pinned_https_get_keeps_credentials_out_of_evidence(self):
        endpoint = "https://example.org/blog/wp-json/ewebcity/v1/snapshot?page=1&per_page=20"
        with patch.dict(os.environ, {"HTTPS_PROXY": "https://proxy.invalid", "HTTP_PROXY": "https://proxy.invalid"}):
            result, connection, resolver, constructor, response = self.call(endpoint=endpoint)
        resolver.assert_called_once()
        self.assertEqual(resolver.call_args.kwargs["allow_localhost"], False)
        self.assertEqual(constructor.call_args.args, ("example.org", 443, (socket.AF_INET, "93.184.216.34")))
        self.assertTrue(constructor.call_args.kwargs["tls"])
        connection.request.assert_called_once()
        args, kwargs = connection.request.call_args
        self.assertEqual(args, ("GET", "/blog/wp-json/ewebcity/v1/snapshot?page=1&per_page=20"))
        self.assertNotIn("body", kwargs)
        headers = kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Basic " + base64.b64encode((USERNAME + ":" + PASSWORD).encode()).decode())
        self.assertEqual(headers["Host"], "example.org")
        self.assertEqual(headers["Accept-Encoding"], "identity")
        self.assertNotIn("Cookie", headers)
        self.assertNotIn("Proxy-Authorization", headers)
        self.assertTrue(response.closed)
        connection.close.assert_called_once()
        self.assertEqual(result["mode"], "authenticated_snapshot")
        self.assertEqual(result["provenance"]["requests"], 1)
        self.assertEqual(result["provenance"]["redirects_followed"], 0)
        self.assertEqual(result["provenance"]["source_url"], endpoint)
        for sensitive in (USERNAME, PASSWORD, headers["Authorization"]):
            self.assertNotIn(sensitive, json.dumps(result))

    def test_plain_permalink_route_is_allowed_and_normalised(self):
        for endpoint, path in (
            ("https://example.org/?rest_route=%2Fewebcity%2Fv1%2Fsnapshot", "/?rest_route=/ewebcity/v1/snapshot"),
            ("https://example.org/blog/index.php?rest_route=/ewebcity/v1/snapshot&page=1", "/blog/index.php?rest_route=/ewebcity/v1/snapshot&page=1"),
        ):
            with self.subTest(endpoint=endpoint):
                _result, connection, *_ = self.call(endpoint=endpoint)
                self.assertEqual(connection.request.call_args.args[1], path)

    def test_unapproved_endpoints_fail_before_dns_or_credentials_are_sent(self):
        bad = ["http://example.org/wp-json/ewebcity/v1/snapshot", "https://other.example/wp-json/ewebcity/v1/snapshot",
            "https://example.org:8443/wp-json/ewebcity/v1/snapshot", "https://user:secret@example.org/wp-json/ewebcity/v1/snapshot",
            ENDPOINT + "#part", ENDPOINT + "?token=secret", ENDPOINT + "?page=0", ENDPOINT + "?page=101",
            ENDPOINT + "?per_page=101", ENDPOINT + "?page=-1", ENDPOINT + "?page=1&page=2", ENDPOINT + "?page=true",
            ENDPOINT + "?page=01", ENDPOINT + "?page=1.0", ENDPOINT + "?page=1;token=secret",
            "https://example.org/wp-json/wp/v2/users", "https://example.org/?rest_route=/wp/v2/users",
            "https://example.org/admin.php?rest_route=/ewebcity/v1/snapshot", "https://example.org/?rest_route=/ewebcity/v1/snapshot&context=edit",
            "https://example.org/../wp-json/ewebcity/v1/snapshot", "https://example.org/%2e%2e/wp-json/ewebcity/v1/snapshot",
            "https://example.org/a%2fb/wp-json/ewebcity/v1/snapshot", "https://example.org//wp-json/ewebcity/v1/snapshot",
            "https://example.org/wp-json/ewebcity/v1/snapshot?rest_route=/ewebcity/v1/snapshot",
        ]
        for endpoint in bad:
            with self.subTest(endpoint=endpoint), patch("wordpress.resolve_public_addresses") as resolver, \
                    patch("wordpress._PinnedConnection") as connection, self.assertRaises(ValueError) as caught:
                fetch_wordpress_evidence(endpoint, TARGET, USERNAME, PASSWORD)
            resolver.assert_not_called()
            connection.assert_not_called()
            self.assertNotIn("secret", str(caught.exception))

    def test_all_redirects_are_refused_without_reading_body_or_following_location(self):
        for status in (300, 301, 302, 303, 304, 307, 308):
            response = FakeResponse(b"server debug " + PASSWORD.encode(), status=status,
                headers=[("Location", "https://attacker.example/" + PASSWORD)])
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "redirects are not followed") as caught:
                self.call(response)
            self.assertEqual(response.read_calls, 0)
            self.assertTrue(response.closed)
            self.assertNotIn(PASSWORD, str(caught.exception))

    def test_status_errors_never_read_or_reflect_server_body(self):
        for status in (401, 403, 404, 407, 429, 500, 503):
            response = FakeResponse((USERNAME + PASSWORD).encode(), status=status)
            with self.subTest(status=status), self.assertRaises(ValueError) as caught:
                self.call(response)
            self.assertEqual(response.read_calls, 0)
            self.assertNotIn(USERNAME, str(caught.exception))
            self.assertNotIn(PASSWORD, str(caught.exception))

    def test_private_and_mixed_dns_are_refused_before_connection(self):
        for addresses in (("127.0.0.1",), ("93.184.216.34", "10.0.0.1"), ("169.254.169.254",), ("::1",)):
            records = [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443)) for address in addresses]
            with self.subTest(addresses=addresses), patch("safe_http.socket.getaddrinfo", return_value=records), \
                    patch("wordpress._PinnedConnection") as connection, self.assertRaisesRegex(ValueError, "permitted public"):
                fetch_wordpress_evidence(ENDPOINT, TARGET, USERNAME, PASSWORD)
            connection.assert_not_called()

    def test_dns_and_transport_error_details_are_not_reflected(self):
        with patch("wordpress.resolve_public_addresses", side_effect=FetchError("fixture", PASSWORD)), self.assertRaises(ValueError) as caught:
            fetch_wordpress_evidence(ENDPOINT, TARGET, USERNAME, PASSWORD)
        self.assertNotIn(PASSWORD, str(caught.exception))
        connection = MagicMock()
        connection.request.side_effect = OSError(USERNAME + PASSWORD)
        with patch("wordpress.resolve_public_addresses", return_value=[(socket.AF_INET, "93.184.216.34")]), \
                patch("wordpress._PinnedConnection", return_value=connection), self.assertRaises(ValueError) as caught:
            fetch_wordpress_evidence(ENDPOINT, TARGET, USERNAME, PASSWORD)
        self.assertNotIn(USERNAME, str(caught.exception))
        self.assertNotIn(PASSWORD, str(caught.exception))
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    def test_bad_credentials_and_timeouts_are_rejected_before_dns(self):
        credentials = [("", PASSWORD), (USERNAME, ""), ("name:part", PASSWORD), (USERNAME, "secret\r\nheader"),
                       (None, PASSWORD), (USERNAME, "\ud800"), ("x" * 257, PASSWORD)]
        for username, password in credentials:
            with self.subTest(username=username), patch("wordpress.resolve_public_addresses") as resolver, self.assertRaises(ValueError):
                fetch_wordpress_evidence(ENDPOINT, TARGET, username, password)
            resolver.assert_not_called()
        for timeout in (0, -1, 121, float("nan"), float("inf"), True, "10"):
            with self.subTest(timeout=timeout), patch("wordpress.resolve_public_addresses") as resolver, self.assertRaises(ValueError):
                fetch_wordpress_evidence(ENDPOINT, TARGET, USERNAME, PASSWORD, timeout=timeout)
            resolver.assert_not_called()

    def test_deadline_includes_dns_wait(self):
        with patch("wordpress.time.monotonic", side_effect=[0.0, 11.0]), \
                patch("wordpress.resolve_public_addresses", return_value=[(socket.AF_INET, "93.184.216.34")]), \
                patch("wordpress._PinnedConnection") as connection, self.assertRaisesRegex(ValueError, "time limit"):
            fetch_wordpress_evidence(ENDPOINT, TARGET, USERNAME, PASSWORD, timeout=10)
        connection.assert_not_called()

    def test_content_type_compression_and_framing_are_strict(self):
        header_sets = [[], [("Content-Type", "text/html")], [("Content-Type", "application/json; charset=latin1")],
            [("Content-Type", "application/json"), ("Content-Type", "application/json")],
            [("Content-Type", "application/json"), ("Content-Encoding", "gzip")],
            [("Content-Type", "application/json"), ("Content-Length", str(MAX_FILE_BYTES + 1))],
            [("Content-Type", "application/json"), ("Content-Length", "invalid")],
            [("Content-Type", "application/json"), ("Content-Length", "1"), ("Content-Length", "1")],
            [("Content-Type", "application/json"), ("Content-Length", "1"), ("Transfer-Encoding", "chunked")],
            [("Content-Type", "application/json"), ("Transfer-Encoding", "gzip")]]
        for headers in header_sets:
            response = FakeResponse(headers=headers)
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                self.call(response)
            self.assertEqual(response.read_calls, 0)

    def test_byte_limit_applies_without_content_length_and_short_body_is_rejected(self):
        response = FakeResponse(b"x" * (MAX_FILE_BYTES + 1), headers=[("Content-Type", "application/json")])
        with self.assertRaisesRegex(ValueError, "10 MiB"):
            self.call(response)
        response = FakeResponse(b"{}", headers=[("Content-Type", "application/json"), ("Content-Length", "99")])
        with self.assertRaisesRegex(ValueError, "declared length"):
            self.call(response)

    def test_malformed_success_body_has_fixed_diagnostic(self):
        response = FakeResponse(("<html>" + USERNAME + PASSWORD).encode())
        with self.assertRaises(ValueError) as caught:
            self.call(response)
        self.assertNotIn(USERNAME, str(caught.exception))
        self.assertNotIn(PASSWORD, str(caught.exception))

    def test_success_credential_echo_is_not_imported(self):
        data = snapshot()
        for reflected in (PASSWORD, PASSWORD.replace(" ", ""), "Basic " + base64.b64encode((USERNAME + ":" + PASSWORD).encode()).decode()):
            data["posts"][0]["metadata"]["yoast"]["title"] = reflected
            with self.subTest(reflected=reflected), self.assertRaisesRegex(ValueError, "reflected authentication") as caught:
                self.call(FakeResponse(json.dumps(data).encode()))
            self.assertNotIn(PASSWORD, str(caught.exception))

    def test_json_escaped_password_echo_is_rejected_after_decoding(self):
        for password in ('review-only-quote"and-backslash\\marker', "review-only-unicode-চাবি"):
            data = snapshot()
            data["posts"][0]["metadata"]["yoast"]["description"] = password
            body = json.dumps(data).encode()
            with self.subTest(password=password), self.assertRaisesRegex(ValueError, "reflected authentication") as caught:
                self.call(FakeResponse(body), password=password)
            self.assertNotIn(password, str(caught.exception))

    def test_explicit_pagination_must_match_response_and_no_next_page_is_fetched(self):
        with self.assertRaisesRegex(ValueError, "did not match"):
            self.call(endpoint=ENDPOINT + "?page=2")
        data = snapshot()
        data["pagination"] = {"page": 2, "per_page": 1, "total_posts": 3, "total_pages": 3}
        result, connection, *_ = self.call(FakeResponse(json.dumps(data).encode()), endpoint=ENDPOINT + "?page=2&per_page=1")
        self.assertFalse(result["coverage"]["complete"])
        connection.request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
