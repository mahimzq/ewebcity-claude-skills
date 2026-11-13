"""Bounded, read-only evidence from the optional eWebCity WordPress bridge.

Saved plugin overrides are not rendered metadata, effective robots policy, or
proof of indexing. The authenticated reader is deliberately separate from the
public crawler: one explicitly supplied, pinned HTTPS endpoint and no redirects.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from safe_http import FetchError, _PinnedConnection, normalise_url, origin, resolve_public_addresses


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_POSTS = 100
MAX_TEXT_BYTES = 8192
SNAPSHOT_FORMAT = "ewebcity-wordpress-snapshot"
SCHEMA_VERSION = "1.0"
METADATA_SEMANTICS = "stored_provider_overrides_not_rendered_metadata"
SNAPSHOT_ROUTE = "/ewebcity/v1/snapshot"
USER_AGENT = "EWebCitySEO/2.2 (+https://ewebcity.co.uk)"
USER_ENV = "EWEBCITY_WP_USER"
PASSWORD_ENV = "EWEBCITY_WP_APP_PASSWORD"
AUTH_REFERENCE = "https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/"
ENDPOINT_REFERENCE = "https://developer.wordpress.org/rest-api/extending-the-rest-api/adding-custom-endpoints/"
YOAST_FIELDS = ("title", "description", "canonical", "robots_noindex", "robots_nofollow", "robots_advanced")
RANKMATH_FIELDS = ("title", "description", "canonical")
DIAGNOSTIC_FIELDS = frozenset(
    ["yoast." + field for field in YOAST_FIELDS]
    + ["rankmath." + field for field in (*RANKMATH_FIELDS, "robots")]
)
NOTE = (
    "These are saved provider overrides, not resolved frontend titles, descriptions, canonicals or robots directives. "
    "Nulls and empty arrays do not establish the effective default. Provider templates, filters, rendered HTML, "
    "indexing and search visibility outcomes require separate verification."
)


class WordPressEvidenceError(ValueError):
    """A fixed, secret-free validation or connection diagnostic."""


def _fail(message: str) -> None:
    raise WordPressEvidenceError(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value, *, nullable: bool = False, maximum: int = MAX_TEXT_BYTES,
          nonempty: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _fail("WordPress snapshot contains an invalid text-field type.")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        _fail("WordPress snapshot contains invalid Unicode text.")
    if size > maximum or (nonempty and not value.strip()) or "\x00" in value:
        _fail("WordPress snapshot contains an empty, oversized or invalid text field.")
    return value


def _integer(value, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("WordPress snapshot contains an invalid integer or pagination bound.")
    return value


def _timestamp(value, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        _fail("WordPress snapshot requires valid UTC timestamps.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("WordPress snapshot requires valid UTC timestamps.")
    return result.isoformat().replace("+00:00", "Z")


def _url(value, *, target_origin: str | None = None, site: bool = False) -> str:
    try:
        value = _text(value, maximum=MAX_TEXT_BYTES, nonempty=True)
        if not isinstance(value, str) or "#" in value:
            raise ValueError
        result = _text(normalise_url(value), maximum=MAX_TEXT_BYTES, nonempty=True)
        parts = urlsplit(result)
        if (target_origin is not None and origin(result) != target_origin) or (site and parts.query):
            raise ValueError
        return result
    except (FetchError, ValueError, UnicodeError):
        raise WordPressEvidenceError("WordPress snapshot URLs must be valid, credential-free HTTP(S) URLs in the required origin.") from None


def _object(value) -> dict:
    if not isinstance(value, dict):
        _fail("WordPress snapshot contains an invalid object-field type.")
    return value


def _duplicate_free(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("WordPress snapshot JSON contains duplicate object keys.")
        result[key] = value
    return result


def _constant(_value):
    _fail("WordPress snapshot JSON cannot contain non-finite numbers.")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        _constant(value)
    return result


def _parse(body: bytes) -> dict:
    if not body or len(body) > MAX_FILE_BYTES:
        _fail("WordPress snapshot must be nonempty and at most 10 MiB.")
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_duplicate_free,
            parse_constant=_constant, parse_float=_finite_float)
    except WordPressEvidenceError:
        raise
    except (UnicodeError, ValueError, RecursionError, OverflowError):
        raise WordPressEvidenceError("WordPress snapshot is not valid bounded UTF-8 JSON.") from None
    return _object(value)


def _diagnostic_fields(value) -> list[str]:
    if not isinstance(value, list) or len(value) > len(DIAGNOSTIC_FIELDS):
        _fail("WordPress snapshot contains invalid metadata diagnostics.")
    if any(not isinstance(field, str) or field not in DIAGNOSTIC_FIELDS for field in value) or len(set(value)) != len(value):
        _fail("WordPress snapshot contains invalid metadata diagnostics.")
    return list(value)


def _normalise_snapshot(data: dict, target: str) -> dict:
    target_origin = origin(_url(target))
    if data.get("format") != SNAPSHOT_FORMAT or data.get("schema_version") != SCHEMA_VERSION:
        _fail("WordPress snapshot has an unsupported format or schema version.")
    version = _text(data.get("bridge_version"), maximum=80, nonempty=True)
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", version):
        _fail("WordPress snapshot contains an invalid bridge version.")
    if data.get("metadata_semantics", METADATA_SEMANTICS) != METADATA_SEMANTICS:
        _fail("WordPress snapshot has unsupported metadata semantics.")
    demonstration = data.get("_demonstration", False)
    if type(demonstration) is not bool:
        _fail("WordPress snapshot demonstration marker must be a boolean.")
    snapshot_auditor = _text(data.get("auditor"), maximum=160, nonempty=True)
    generated_at = _timestamp(data.get("generated_at"))
    site = _object(data.get("site"))
    visibility = site.get("search_visibility")
    if not isinstance(visibility, str) or visibility not in {"allow", "discourage"}:
        _fail("WordPress snapshot has an invalid search-visibility setting.")
    clean_site = {
        "home_url": _url(site.get("home_url"), target_origin=target_origin, site=True),
        "site_url": _url(site.get("site_url"), site=True),
        "search_visibility": visibility,
        "permalink_structure": _text(site.get("permalink_structure")),
    }
    providers = data.get("providers")
    if not isinstance(providers, list) or len(providers) > 2:
        _fail("WordPress snapshot must contain a bounded provider list.")
    clean_providers, active = [], set()
    for provider in providers:
        provider = _object(provider)
        identifier = provider.get("id")
        if not isinstance(identifier, str) or identifier not in {"yoast", "rankmath"} or identifier in active or provider.get("active") is not True:
            _fail("WordPress snapshot must identify unique, explicitly active supported providers.")
        active.add(identifier)
        clean_providers.append({"id": identifier, "active": True,
            "version": _text(provider.get("version"), maximum=80)})

    pagination = _object(data.get("pagination"))
    page = _integer(pagination.get("page"), 1, 100)
    per_page = _integer(pagination.get("per_page"), 1, 100)
    total_posts = _integer(pagination.get("total_posts"), 0, (1 << 63) - 1)
    total_pages = _integer(pagination.get("total_pages"), 0, (1 << 63) - 1)
    if total_pages != (total_posts + per_page - 1) // per_page or (total_posts == 0 and page != 1):
        _fail("WordPress snapshot pagination totals are inconsistent.")
    posts = data.get("posts")
    if not isinstance(posts, list) or len(posts) > min(MAX_POSTS, per_page, total_posts):
        _fail("WordPress snapshot posts exceed the declared or supported page bound.")
    clean_posts, seen_ids, seen_urls = [], set(), set()
    missing_provider_rows = incomplete_rows = duplicate_urls = 0
    for post in posts:
        post = _object(post)
        identifier = _integer(post.get("id"), 1, (1 << 63) - 1)
        if identifier in seen_ids:
            _fail("WordPress snapshot contains duplicate post identifiers.")
        seen_ids.add(identifier)
        post_type = _text(post.get("type"), maximum=64, nonempty=True)
        if not re.fullmatch(r"[a-z0-9_-]+", post_type):
            _fail("WordPress snapshot contains an invalid post type.")
        url = _url(post.get("url"), target_origin=target_origin)
        duplicate_urls += url in seen_urls
        seen_urls.add(url)
        metadata = _object(post.get("metadata"))
        clean_metadata = {}
        for provider, fields in (("yoast", YOAST_FIELDS), ("rankmath", RANKMATH_FIELDS)):
            if provider not in metadata:
                missing_provider_rows += provider in active
                continue
            if provider not in active:
                _fail("WordPress snapshot metadata refers to a provider that was not reported active.")
            values = _object(metadata[provider])
            if any(field not in values for field in fields):
                _fail("WordPress snapshot is missing required raw metadata fields.")
            clean_metadata[provider] = {field: _text(values[field], nullable=True) for field in fields}
            if provider == "rankmath":
                robots = values.get("robots")
                if not isinstance(robots, list) or len(robots) > 32:
                    _fail("WordPress snapshot has an invalid Rank Math robots override list.")
                clean_metadata[provider]["robots"] = [_text(value) for value in robots]
        truncated = _diagnostic_fields(post.get("truncated_fields", []))
        omitted = _diagnostic_fields(post.get("omitted_fields", []))
        incomplete_rows += bool(truncated or omitted)
        clean_posts.append({"id": identifier, "type": post_type, "url": url,
            "modified_gmt": _timestamp(post.get("modified_gmt"), nullable=True),
            "metadata": clean_metadata, "truncated_fields": truncated, "omitted_fields": omitted})

    complete = page == 1 and total_pages <= 1 and len(clean_posts) == total_posts
    issues = []
    if not complete:
        issues.append("Only one snapshot page was imported; published posts outside this page were not inspected and no additional pages were fetched.")
    if page > total_pages and total_posts:
        issues.append("The supplied page is outside the reported pagination range; it cannot establish complete post coverage.")
    if not active:
        issues.append("No supported active provider was reported; provider presence and effective SEO settings remain unverified.")
    elif len(active) == 2:
        issues.append("Both Yoast and Rank Math were reported active; inspect the frontend for overlapping output before changing settings.")
    if any(not provider["version"].strip() for provider in clean_providers):
        issues.append("An active provider's version was unavailable; no installed version was inferred.")
    if visibility == "discourage":
        issues.append("WordPress was configured to discourage search engines. Confirm that this is intentional and inspect frontend directives separately.")
    if missing_provider_rows:
        issues.append("Some reported active-provider metadata objects were absent from post records; those overrides are unknown.")
    if incomplete_rows:
        issues.append("Some stored metadata fields were truncated or omitted by the bridge; inspect their field diagnostics and original settings.")
    if duplicate_urls:
        issues.append("Multiple post records report the same URL; the snapshot does not prove distinct frontend pages.")
    if origin(clean_site["site_url"]) != target_origin:
        issues.append("The reported WordPress installation URL has another origin; it was recorded as a setting and was not contacted.")
    if demonstration:
        issues.insert(0, "DEMONSTRATION DATA: this supplied snapshot is a fixture, not evidence of a live WordPress connection.")
    return {"format": SNAPSHOT_FORMAT, "schema_version": SCHEMA_VERSION,
        "bridge_version": version, "generated_at": generated_at,
        "snapshot_auditor": snapshot_auditor, "metadata_semantics": METADATA_SEMANTICS,
        "_demonstration": demonstration, "site": clean_site, "providers": clean_providers,
        "provider_status": {key: "active" if key in active else "not_reported" for key in ("yoast", "rankmath")},
        "pagination": {"page": page, "per_page": per_page, "total_posts": total_posts, "total_pages": total_pages},
        "coverage": {"posts_imported": len(clean_posts), "total_posts_reported": total_posts,
            "total_pages_reported": total_pages, "page": page, "complete": complete,
            "scope": "one snapshot page of published posts; totals are reported by the bridge, not independently enumerated"},
        "posts": clean_posts, "issues": issues,
        "note": ("DEMONSTRATION DATA. " if demonstration else "") + NOTE,
        "reference_urls": [AUTH_REFERENCE, ENDPOINT_REFERENCE], "reference_checked_at": "2026-11-12"}


def _read_file(path: Path) -> tuple[bytes, str | None]:
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
            _fail("WordPress snapshot input must be a nonempty regular file of at most 10 MiB.")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            body = stream.read(MAX_FILE_BYTES + 1)
        if len(body) > MAX_FILE_BYTES:
            _fail("WordPress snapshot input exceeds the 10 MiB limit.")
        try:
            modified_at = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except (OSError, ValueError, OverflowError):
            modified_at = None
        return body, modified_at
    except WordPressEvidenceError:
        raise
    except (OSError, ValueError, TypeError):
        raise WordPressEvidenceError("WordPress snapshot input could not be read as a regular file.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_wordpress_evidence(path: Path | str, target: str) -> dict:
    """Import exactly one saved snapshot with no network access."""
    target = _url(target)
    try:
        path = Path(path)
    except (TypeError, ValueError):
        raise WordPressEvidenceError("WordPress snapshot input requires a file path.") from None
    body, modified_at = _read_file(path)
    result = _normalise_snapshot(_parse(body), target)
    result["mode"] = "offline_snapshot"
    result["provenance"] = {"kind": "local_file", "input_file": path.name,
        "input_sha256": hashlib.sha256(body).hexdigest(), "byte_count": len(body),
        "file_modified_at": modified_at, "collected_at": _now(), "source_url": None}
    return result


def _safe_path(path: str) -> bool:
    if not path.startswith("/") or re.search(r"%2f|%5c", path, re.I) or re.search(r"%(?![0-9a-fA-F]{2})", path):
        return False
    try:
        decoded = unquote(path, errors="strict")
    except UnicodeError:
        return False
    return not ("\\" in decoded or "//" in decoded or any(ord(char) < 32 or ord(char) == 127 for char in decoded)
                or any(segment in {".", ".."} for segment in decoded.split("/")))


def _endpoint(endpoint: str, target: str) -> tuple[str, dict[str, int]]:
    try:
        target_origin = origin(_url(target))
        endpoint = _url(endpoint, target_origin=target_origin)
        parts = urlsplit(endpoint)
        if parts.scheme != "https" or not _safe_path(parts.path):
            raise ValueError
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
        query = {}
        expected = {}
        for key, value in pairs:
            if key not in {"rest_route", "page", "per_page"} or key in query:
                raise ValueError
            if key == "rest_route":
                if value != SNAPSHOT_ROUTE:
                    raise ValueError
            else:
                if not re.fullmatch(r"[1-9][0-9]{0,2}", value) or not 1 <= int(value) <= 100:
                    raise ValueError
                expected[key] = int(value)
            query[key] = value
        if "rest_route" in query:
            if not (parts.path.endswith("/") or parts.path.endswith("/index.php")):
                raise ValueError
        elif not parts.path.rstrip("/").endswith("/wp-json" + SNAPSHOT_ROUTE):
            raise ValueError
        # Reconstruct only allowlisted query values. No untrusted token or
        # arbitrary parameter can enter a request or report provenance.
        clean_query = urlencode(list(query.items()), safe="/")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, clean_query, "")), expected
    except (FetchError, ValueError, UnicodeError):
        raise WordPressEvidenceError("WordPress API requires the same-origin HTTPS snapshot endpoint with only page/per_page arguments in 1..100.") from None


def _authorization(username: str, password: str) -> str:
    if (not isinstance(username, str) or not isinstance(password, str) or not username.strip() or not password.strip()
            or len(username) > 256 or len(password) > 1024 or ":" in username
            or any(ord(char) < 32 or ord(char) == 127 for char in username + password)):
        _fail("WordPress API requires a valid username and application password supplied through the configured environment variables.")
    try:
        return "Basic " + base64.b64encode((username + ":" + password).encode("utf-8")).decode("ascii")
    except UnicodeError:
        raise WordPressEvidenceError("WordPress API credentials must contain valid Unicode text.") from None


def _header_values(response) -> dict[str, list[str]]:
    result = {}
    for key, value in response.getheaders():
        result.setdefault(key.lower(), []).append(value.strip())
    return result


def _fetch_body(endpoint: str, authorization: str, timeout: float) -> bytes:
    """Send one request with pinned DNS/TLS; never expose server error text."""
    connection = response = None
    deadline = time.monotonic() + timeout
    try:
        parts = urlsplit(endpoint)
        port = parts.port or 443
        addresses = resolve_public_addresses(parts.hostname, port, allow_localhost=False, timeout=timeout)
        if time.monotonic() >= deadline:
            _fail("WordPress snapshot request exceeded its time limit.")
        connection = _PinnedConnection(parts.hostname, port, addresses[0], tls=True, timeout=timeout, deadline=deadline)
        request_path = parts.path + ("?" + parts.query if parts.query else "")
        connection.request("GET", request_path, headers={"Host": parts.netloc,
            "User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "identity",
            "Connection": "close", "Cache-Control": "no-store", "Authorization": authorization})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            _fail("WordPress snapshot redirects are not followed; provide the final HTTPS bridge endpoint.")
        if response.status in (401, 403):
            _fail("WordPress snapshot access was denied; verify the application password and required permissions.")
        if response.status == 429:
            _fail("WordPress snapshot was rate limited; no retry was made.")
        if response.status != 200:
            _fail("WordPress snapshot endpoint did not return HTTP 200; no response body was imported.")
        headers = _header_values(response)
        content_types = headers.get("content-type", [])
        if len(content_types) != 1 or not re.fullmatch(r'application/json(?:\s*;\s*charset\s*=\s*(?:utf-8|"utf-8"))?', content_types[0], re.I):
            _fail("WordPress snapshot endpoint must return UTF-8 application/json.")
        encodings = headers.get("content-encoding", [])
        if len(encodings) > 1 or (encodings and encodings[0].lower() not in {"", "identity"}):
            _fail("WordPress snapshot returned unsupported compressed content.")
        lengths = headers.get("content-length", [])
        length = None
        if lengths:
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                _fail("WordPress snapshot returned an invalid response length.")
            length = int(lengths[0])
            if length > MAX_FILE_BYTES:
                _fail("WordPress snapshot response exceeds the 10 MiB limit.")
        transfers = headers.get("transfer-encoding", [])
        if transfers and (length is not None or len(transfers) != 1 or transfers[0].lower() != "chunked"):
            _fail("WordPress snapshot returned unsupported response framing.")
        body = bytearray()
        while True:
            if time.monotonic() >= deadline:
                _fail("WordPress snapshot request exceeded its time limit.")
            chunk = response.read(min(65_536, MAX_FILE_BYTES - len(body) + 1))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > MAX_FILE_BYTES:
                _fail("WordPress snapshot response exceeds the 10 MiB limit.")
        if length is not None and len(body) != length:
            _fail("WordPress snapshot response ended before its declared length.")
        return bytes(body)
    except WordPressEvidenceError:
        raise
    except FetchError:
        raise WordPressEvidenceError("WordPress snapshot endpoint could not be resolved to permitted public addresses within the time limit.") from None
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        raise WordPressEvidenceError("WordPress snapshot HTTPS request failed; credentials and server diagnostics were not recorded.") from None
    finally:
        if response is not None:
            try:
                response.close()
            except (OSError, http.client.HTTPException):
                pass
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


def _contains_authentication(value: dict, sensitive: set[str]) -> bool:
    # Walk the bounded, allowlisted result rather than its JSON spelling.
    # JSON quoting must not hide echoed quotes, backslashes or Unicode secrets.
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(token and token in item for token in sensitive):
                return True
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return False


def fetch_wordpress_evidence(endpoint: str, target: str, username: str, password: str,
                             timeout: float = 10) -> dict:
    """Read one protected snapshot page; credentials never enter the crawler."""
    endpoint, expected = _endpoint(endpoint, target)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        _fail("WordPress API timeout must be a finite number greater than zero and at most 120 seconds.")
    authorization = _authorization(username, password)
    body = _fetch_body(endpoint, authorization, timeout)
    result = _normalise_snapshot(_parse(body), target)
    if any(result["pagination"][key] != value for key, value in expected.items()):
        _fail("WordPress snapshot pagination did not match the explicitly requested page arguments.")
    # A misconfigured or hostile endpoint must not turn an authentication echo
    # into retained metadata, even if it returned an otherwise valid snapshot.
    sensitive = {password, password.replace(" ", ""), authorization, authorization[6:]}
    if _contains_authentication(result, sensitive):
        _fail("WordPress snapshot contained reflected authentication material and was not imported.")
    result["mode"] = "authenticated_snapshot"
    result["provenance"] = {"kind": "authenticated_https", "input_file": None,
        "input_sha256": hashlib.sha256(body).hexdigest(), "byte_count": len(body),
        "collected_at": _now(), "source_url": endpoint, "http_status": 200,
        "requests": 1, "redirects_followed": 0, "credential_storage": "not recorded"}
    return result
