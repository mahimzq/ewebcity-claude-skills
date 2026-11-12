#!/usr/bin/env python3
"""Evidence-producing, bounded source-HTML audit. Python 3.10+, standard library.

This does not execute JavaScript, measure Core Web Vitals, query an index, or
prove that an AI answer engine has cited a website. It never edits a website.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required for the eWebCity audit runtime.")

from safe_http import BudgetExceeded, FetchError, PRODUCT_TOKEN, RobotsPolicy, SafeClient, normalise_url, origin

TOOL_VERSION = "2.0.0"
SCHEMA_VERSION = "1.0"
REFERENCE_CHECKED_AT = "2026-11-12"
SEARCH_DOCS = "https://developers.google.com/search/docs/"
REFERENCES = {
    "http": SEARCH_DOCS + "crawling-indexing/http-network-errors",
    "robots": SEARCH_DOCS + "crawling-indexing/robots/intro",
    "index": SEARCH_DOCS + "crawling-indexing/block-indexing",
    "title": SEARCH_DOCS + "appearance/title-link",
    "description": SEARCH_DOCS + "appearance/snippet",
    "canonical": SEARCH_DOCS + "crawling-indexing/consolidate-duplicate-urls",
    "schema": SEARCH_DOCS + "appearance/structured-data/intro-structured-data",
    "sitemap": SEARCH_DOCS + "crawling-indexing/sitemaps/build-sitemap",
    "image": SEARCH_DOCS + "appearance/google-images",
    "html": SEARCH_DOCS + "fundamentals/seo-starter-guide",
    "mobile": SEARCH_DOCS + "crawling-indexing/mobile/mobile-sites-mobile-first-indexing",
}
NOT_PERFORMED = [
    "JavaScript execution, rendered DOM, CSS layout, visual accessibility and mobile interaction testing.",
    "Core Web Vitals (LCP, INP, CLS), Lighthouse, browser loading performance and field measurements.",
    "Google/Bing indexing status, rankings, Search Console, Analytics or other authenticated account data.",
    "AI answer citations, brand mentions, AI visibility, model training use or guaranteed search inclusion.",
    "Full structured-data eligibility or truth validation; JSON-LD checks cover JSON syntax only.",
    "Unlinked/orphan pages, exhaustive site coverage, external destinations, assets or backlink validation.",
    "Business accuracy, ownership, content expertise, editorial quality and search intent validation.",
    "llms.txt adoption and PWA manifest checks; their absence is not treated as an SEO failure.",
]
ASSET_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".css", ".js", ".mjs", ".map", ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".webm", ".pdf", ".zip", ".gz", ".xml", ".json"}


class CrawlStopped(FetchError):
    def __init__(self, code: str, message: str, url: str, http_status: int):
        super().__init__(code, message)
        self.url, self.http_status = url, http_status


def _check_access_response(response) -> None:
    if response.status in (401, 403, 407, 429):
        code = "rate_limited" if response.status == 429 else "access_denied"
        raise CrawlStopped(code,
            f"HTTP {response.status} at {response.url}; crawling stopped and the unavailable/challenge content was not analysed.",
            response.url, response.status)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: str) -> str:
    return " ".join(value.split())


def finding(rule_id: str, url: str, status: str, severity: str, observation: str,
            recommendation: str, *, collected_at: str, reference: str = "html",
            confidence: str = "high", evidence_kind: str = "observed", **details) -> dict:
    return {
        "id": f"{rule_id}|{url}", "rule_id": rule_id, "url": url,
        "status": status, "severity": severity if status in ("fail", "warning") else "info",
        "confidence": confidence, "evidence_kind": evidence_kind,
        "evidence": {"source_url": url, "collected_at": collected_at,
                     "observation": observation, **details},
        "recommendation": recommendation,
        "reference_url": REFERENCES.get(reference, reference),
        "reference_checked_at": REFERENCE_CHECKED_AT,
    }


class SourceHTML(HTMLParser):
    """Extract only facts present in the saved/received HTML source."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self.descriptions: list[str] = []
        self.robots: list[dict] = []
        self.canonicals: list[str] = []
        self.headings: list[dict] = []
        self.hrefs: list[str] = []
        self.resources: list[str] = []
        self.images: list[dict] = []
        self.json_ld: list[str] = []
        self.lang = ""
        self.viewport: list[str] = []
        self.base: str | None = None
        self._title: list[str] | None = None
        self._heading: dict | None = None
        self._json: list[str] | None = None
        self._script = False
        self._suppressed = 0
        self._inert_depth = 0
        self.text_parts: list[str] = []
        self.href_count = self.image_count = self.script_count = 0
        self.extraction_limited = False
        self.links_extraction_limited = False
        self.images_extraction_limited = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in ("template", "noscript"):
            self._inert_depth += 1
            return
        if self._inert_depth:
            return
        if tag == "html" and not self.lang:
            self.lang = values.get("lang") or ""
        if tag == "base" and self.base is None:
            self.base = values.get("href")
        if tag == "title":
            self._title = []
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = {"level": int(tag[1]), "parts": []}
        if tag == "meta":
            name, content = (values.get("name") or "").lower(), values.get("content") or ""
            if name == "description":
                self.descriptions.append(content)
            elif name in ("robots", "googlebot", "bingbot"):
                self.robots.append({"agent": name, "content": content})
            elif name == "viewport":
                self.viewport.append(content)
        if tag == "link":
            relations = (values.get("rel") or "").lower().split()
            href = values.get("href") or ""
            if "canonical" in relations:
                self.canonicals.append(href)
            if any(rel in relations for rel in ("stylesheet", "preload", "modulepreload")):
                self.resources.append(href)
        if tag in ("a", "area") and values.get("href") is not None:
            self.href_count += 1
            if len(self.hrefs) < 2000:
                self.hrefs.append(values["href"])
            else:
                self.extraction_limited = True
                self.links_extraction_limited = True
        if tag == "img":
            self.image_count += 1
            if len(self.images) < 2000:
                self.images.append({"src": values.get("src") or "", "alt": values.get("alt"),
                    "width": values.get("width"), "height": values.get("height"),
                    "loading": values.get("loading")})
            else:
                self.extraction_limited = True
                self.images_extraction_limited = True
            self.resources.append(values.get("src") or "")
        if tag in ("iframe", "audio", "video", "source") and values.get("src"):
            self.resources.append(values["src"])
        if tag == "script":
            self._script = True
            self.script_count += 1
            self._json = [] if (values.get("type") or "").lower().strip() == "application/ld+json" else None
            if values.get("src"):
                self.resources.append(values["src"])
        if tag == "style":
            self._suppressed += 1

    def handle_startendtag(self, tag, attrs) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("template", "noscript"):
            self._inert_depth = max(0, self._inert_depth - 1)
            return
        if self._inert_depth:
            return
        if tag == "title" and self._title is not None:
            self.titles.append(_text("".join(self._title)))
            self._title = None
        if self._heading and tag == f"h{self._heading['level']}":
            self.headings.append({"level": self._heading["level"], "text": _text("".join(self._heading["parts"]))})
            self._heading = None
        if tag == "script":
            if self._json is not None:
                self.json_ld.append("".join(self._json))
            self._script, self._json = False, None
        if tag == "style":
            self._suppressed = max(0, self._suppressed - 1)

    def handle_data(self, data: str) -> None:
        if self._inert_depth:
            return
        if self._json is not None:
            self._json.append(data)
        if self._title is not None:
            self._title.append(data)
        if self._heading is not None:
            self._heading["parts"].append(data)
        if not self._script and not self._suppressed:
            self.text_parts.append(data)

    def close(self) -> None:
        super().close()
        # Preserve present-but-unclosed elements; never fabricate missing tags.
        if self._title is not None:
            self.titles.append(_text("".join(self._title)))
            self._title = None
        if self._json is not None:
            self.json_ld.append("".join(self._json))
            self._json = None


def _schema_summary(blocks: list[str]) -> dict:
    types: set[str] = set()
    errors: list[dict] = []
    for number, block in enumerate(blocks, 1):
        try:
            payload = json.loads(block, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant {value}")))
            queue = deque([payload])
            visited = 0
            while queue and visited < 5000:
                item = queue.popleft()
                visited += 1
                if isinstance(item, dict):
                    kind = item.get("@type", [])
                    if isinstance(kind, str):
                        types.add(kind)
                    elif isinstance(kind, list):
                        types.update(value for value in kind if isinstance(value, str))
                    queue.extend(value for value in item.values() if isinstance(value, (dict, list)))
                elif isinstance(item, list):
                    queue.extend(value for value in item if isinstance(value, (dict, list)))
        except (ValueError, RecursionError) as exc:
            errors.append({"block": number, "error": str(exc)[:250]})
    return {"blocks": len(blocks), "types": sorted(types), "syntax_errors": errors,
            "eligibility_checked": False}


def _noindex_sources(meta: list[dict], headers: dict) -> list[dict]:
    sources = [{"source": f"meta:{item['agent']}", "value": item["content"]} for item in meta]
    if headers.get("x-robots-tag"):
        sources.append({"source": "http:x-robots-tag", "value": headers["x-robots-tag"]})
    return [item for item in sources if re.search(r"\b(noindex|none)\b", item["value"], re.I)]


def analyse_html(url: str, html: str, *, collected_at: str | None = None,
                 http_status: int | None = None, headers: dict | None = None,
                 requested_url: str | None = None, redirects: list | None = None,
                 source_bytes: int | None = None) -> tuple[dict, list[dict]]:
    """Pure analysis: no requests, DNS, disk writes, rendering or index assertions."""
    url = normalise_url(url)
    collected_at = collected_at or utc_now()
    headers_were_supplied = headers is not None
    headers = {key.lower(): value for key, value in (headers or {}).items()}
    parser = SourceHTML()
    parser.feed(html)
    parser.close()
    base = url
    invalid_base = None
    if parser.base:
        try:
            base = normalise_url(parser.base, url)
        except FetchError:
            invalid_base = parser.base[:250]
    links: set[str] = set()
    invalid_links: list[str] = []
    for href in parser.hrefs:
        try:
            if urlsplit(href).scheme.lower() in ("mailto", "tel", "javascript", "data", "sms"):
                continue
            links.add(normalise_url(href.strip() or base, base))
        except (FetchError, ValueError):
            invalid_links.append(href[:250])
    canonical: list[str] = []
    bad_canonical: list[str] = []
    for value in parser.canonicals:
        try:
            if not value.strip():
                raise FetchError("invalid_url", "Empty canonical href.")
            canonical.append(normalise_url(value, base))
        except FetchError:
            bad_canonical.append(value[:250])
    mixed: list[str] = []
    if urlsplit(url).scheme == "https":
        for value in parser.resources:
            try:
                resource = normalise_url(value, base)
                if urlsplit(resource).scheme == "http":
                    mixed.append(resource)
            except FetchError:
                pass
    schema = _schema_summary(parser.json_ld)
    noindex = _noindex_sources(parser.robots, headers)
    source_text = _text(" ".join(parser.text_parts))
    page = {
        "url": url, "requested_url": requested_url or url, "http_status": http_status,
        "content_type": headers.get("content-type"), "fetched_at": collected_at,
        "observation_kind": "source_html", "redirects": redirects or [],
        "title": parser.titles[0] if parser.titles else None, "titles": parser.titles,
        "meta_description": parser.descriptions[0] if parser.descriptions else None,
        "meta_descriptions": parser.descriptions, "robots": parser.robots,
        "x_robots_tag": headers.get("x-robots-tag"), "noindex_observations": noindex,
        "canonical": canonical, "headings": parser.headings, "lang": parser.lang,
        "viewport": parser.viewport, "base_url": base, "links": sorted(links),
        "images": {"count": parser.image_count, "sampled": len(parser.images),
                   "missing_alt": sum(image["alt"] is None for image in parser.images),
                   "empty_alt": sum(image["alt"] == "" for image in parser.images),
                   "missing_dimension_attributes": sum(not image["width"] or not image["height"] for image in parser.images)},
        "json_ld": schema, "source_bytes": source_bytes if source_bytes is not None else len(html.encode("utf-8")),
        "content_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "source_text_word_count": len(source_text.split()),
        "script_count": parser.script_count, "discovered_link_count": parser.href_count,
        "extraction_limited": parser.extraction_limited,
        "links_extraction_limited": parser.links_extraction_limited,
        "images_extraction_limited": parser.images_extraction_limited,
        "question_heading_count": sum("?" in heading["text"] for heading in parser.headings),
    }
    findings = []

    def add(rule_id, status, severity, observation, recommendation, reference="html", **details):
        findings.append(finding(rule_id, url, status, severity, observation, recommendation,
            collected_at=collected_at, reference=reference, **details))

    if http_status is None:
        add("http_status", "not_checked", "info", "Saved HTML has no observed HTTP status.", "Fetch the live URL separately to verify its response status.", "http")
        add("redirect_chain", "not_checked", "info", "Saved HTML has no observed redirect chain.", "Fetch the live URL separately to inspect redirects.", "http")
    else:
        add("http_status", "pass" if 200 <= http_status < 300 else "fail", "high",
            f"The observed final HTTP status was {http_status}.",
            "Review the route and server response if this URL is intended to serve public content.", "http", http_status=http_status)
        add("redirect_chain", "warning" if len(redirects or []) > 1 else "pass", "low",
            f"Observed {len(redirects or [])} redirect(s) before this response.",
            "Point internal links directly to the intended final URL; preserve necessary redirects.", "http", redirects=redirects or [])
    usable_title = any(title.strip() for title in parser.titles)
    add("title_present", "pass" if usable_title else "fail", "medium",
        "A nonempty title is present in source HTML." if usable_title else "No nonempty title was found in source HTML.",
        "Provide a descriptive page title using the framework's metadata mechanism; verify the rendered result.", "title", values=parser.titles)
    add("title_single", "warning" if len(parser.titles) > 1 else "pass", "low",
        f"Source HTML contains {len(parser.titles)} title element(s).",
        "Review multiple title elements and retain one intended document title.", "title", values=parser.titles)
    has_description = any(item.strip() for item in parser.descriptions)
    add("description_present", "pass" if has_description else "warning", "low",
        "A meta description is present in source HTML." if has_description else "No nonempty meta description was found in source HTML.",
        "Consider a page-specific summary; Google may choose a different snippet and no fixed character length guarantees display.", "description", values=parser.descriptions)
    add("canonical_present", "pass" if parser.canonicals else "warning", "low",
        f"Source HTML contains {len(parser.canonicals)} canonical link element(s).",
        "Review canonicalisation where duplicate URLs exist. A missing canonical tag alone does not prove an indexing problem.", "canonical", values=parser.canonicals)
    add("canonical_single", "fail" if len(parser.canonicals) > 1 else "pass", "medium",
        f"Observed {len(parser.canonicals)} canonical link element(s).",
        "Use one consistent intended canonical declaration per document.", "canonical", values=parser.canonicals)
    add("canonical_valid_url", "fail" if bad_canonical else ("pass" if parser.canonicals else "not_applicable"), "medium",
        "Some canonical hrefs are empty, malformed or unsupported." if bad_canonical else "Canonical hrefs checked here resolve to HTTP(S) URLs." if parser.canonicals else "No canonical href is present to validate.",
        "Use the intended canonical HTTP(S) URL and verify its response, index directives and content separately.", "canonical", invalid_values=bad_canonical, resolved_values=canonical)
    external_canonical = [item for item in canonical if origin(item) != origin(url)]
    add("canonical_origin", "warning" if external_canonical else ("pass" if canonical else "not_applicable"), "medium",
        "A canonical points to another origin." if external_canonical else "No cross-origin canonical was observed.",
        "Confirm whether cross-origin canonicalisation is intentional, for example for syndicated content; do not change it automatically.", "canonical", related_urls=external_canonical)
    add("noindex_directive", "warning" if noindex else "pass", "medium",
        ("A noindex/none directive was observed; intended indexing policy is not known." if noindex else
         "No noindex/none directive was observed in inspected source meta tags" + (" or observed HTTP headers." if headers_were_supplied else ". HTTP response headers were not inspected.")),
        "Confirm whether the page should be indexed before changing directives; source observations do not prove search-engine indexing status.", "index", directives=noindex, http_headers_checked=headers_were_supplied)
    add("html_lang", "pass" if parser.lang.strip() else "warning", "low",
        f"The source html lang value is {parser.lang!r}.",
        "Set a correct document language for assistive technology; confirm the actual language and translations.", lang=parser.lang)
    add("viewport_present", "pass" if parser.viewport else "warning", "low",
        f"Observed {len(parser.viewport)} viewport meta element(s) in source HTML.",
        "Check a suitable viewport declaration and test the actual responsive layout in a browser.", "mobile", values=parser.viewport)
    h1s = [item["text"] for item in parser.headings if item["level"] == 1]
    add("main_heading_present", "pass" if any(h1s) else "warning", "low",
        f"Observed {len(h1s)} h1 element(s) in source HTML. Multiple h1s are not automatically an SEO failure.",
        "Check that the page has a clear, accessible main heading in its rendered structure.", headings=h1s)
    absent_alt = [item["src"][:250] for item in parser.images if item["alt"] is None]
    add("image_alt_attribute", "warning" if absent_alt else ("not_checked" if parser.image_count > len(parser.images) else "pass" if parser.image_count else "not_applicable"), "low",
        f"{len(absent_alt)} of {len(parser.images)} inspected img elements omit the alt attribute.",
        "Use informative alt text for meaningful images and an empty alt attribute for decorative images; inspect context before writing text.", "image", missing_alt_sources=absent_alt[:30], total_images=parser.image_count, sampled_images=len(parser.images))
    add("jsonld_syntax", "fail" if schema["syntax_errors"] else "pass" if schema["blocks"] else "not_applicable", "medium",
        f"Parsed {schema['blocks']} JSON-LD block(s); {len(schema['syntax_errors'])} have invalid JSON syntax. Rich-result eligibility was not checked.",
        "Repair invalid JSON and then validate the applicable supported schema and truthful visible content separately.", "schema", **schema)
    add("mixed_content_references", "warning" if mixed else "pass", "low",
        f"Observed {len(mixed)} HTTP resource reference(s) in the source of an HTTPS page." if urlsplit(url).scheme == "https" else "Mixed-content check does not apply to an HTTP source URL.",
        "Check browser behaviour and replace eligible resource references with verified HTTPS URLs; no resource was fetched by this check.", "http", related_urls=sorted(set(mixed)))
    if invalid_base:
        add("base_url_valid", "fail", "medium", "The source base href cannot be resolved as an HTTP(S) URL.", "Review the base href and the links it changes.", invalid_value=invalid_base)
    else:
        add("base_url_valid", "pass" if parser.base else "not_applicable", "low", "No invalid base href was observed.", "Preserve the intended document base URL.", value=parser.base)
    add("link_url_syntax", "warning" if invalid_links else "not_checked" if parser.links_extraction_limited else "pass", "low",
        f"{len(invalid_links)} inspected link href(s) could not be resolved as HTTP(S) URLs. Inspected {len(parser.hrefs)} of {parser.href_count} hyperlink href(s)."
        + (" Omitted hrefs remain unverified because extraction was limited." if parser.links_extraction_limited else ""),
        "Review these references; non-web application links may be intentional. The crawler follows only HTTP(S) URLs.",
        invalid_values=invalid_links[:30], links_extraction_limited=parser.links_extraction_limited,
        sampled_link_count=len(parser.hrefs), total_link_count=parser.href_count)
    return page, findings


def _decode(body: bytes, headers: dict) -> str:
    match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", headers.get("content-type", ""), re.I)
    charset = match.group(1) if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _is_html(headers: dict, body: bytes) -> bool:
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type in ("text/html", "application/xhtml+xml"):
        return True
    return not content_type and bool(re.search(br"<(?:!doctype\s+html|html|head|body)\b", body[:1024], re.I))


def _base_report(target: str, mode: str, limits: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
        "target": target, "collected_at": utc_now(), "mode": mode,
        "coverage": {"scope_origin": origin(target), "limits": limits, "requests": 0,
            "bytes_received": 0, "pages_fetched": 0, "pages_analysed": 0,
            "byte_measurement": "Response body bytes only; excludes headers and transport overhead. Identity encoding is requested and compressed responses are not analysed.",
            "discovered_urls": [], "skipped": [], "robots": {}, "sitemaps": [],
            "complete": False, "completeness_scope": "bounded discovered source-HTML sample only; never the entire website",
            "stop_reasons": []},
        "pages": [], "responses": [], "findings": [], "checks_not_performed": list(NOT_PERFORMED)}


def _record_duplicates(report: dict) -> None:
    for field, rule, reference in (("title", "duplicate_title", "title"), ("meta_description", "duplicate_description", "description")):
        groups: dict[str, list[str]] = defaultdict(list)
        for page in report["pages"]:
            if page.get(field):
                groups[_text(page[field]).casefold()].append(page["url"])
        for page in report["pages"]:
            value = page.get(field)
            if value is None:
                continue
            related = sorted(set(groups[_text(value).casefold()]) - {page["url"]})
            report["findings"].append(finding(rule, page["url"], "warning" if related else "pass", "low",
                f"This {field} exactly matches {len(related)} other URL(s) in the inspected sample; unvisited pages are unknown.",
                "Review whether these pages need different summaries/titles or intentional canonicalisation; do not infer keyword cannibalisation from this check.",
                collected_at=page["fetched_at"], reference=reference, related_urls=related, value=value,
                comparison_scope_urls=sorted(item["url"] for item in report["pages"])))


def _record_destination_checks(report: dict) -> None:
    responses: dict[str, dict] = {}
    pages = {page["url"]: page for page in report["pages"]}
    for response in report.get("responses", []):
        responses[response["requested_url"]] = response
        # A canonical pointing directly to the final URL does not inherit the
        # redirects of a different incoming URL.
        responses.setdefault(response["url"], {**response, "requested_url": response["url"], "redirects": []})
    for page in report["pages"]:
        for category, targets in (
            ("internal_link", sorted({url for url in page["links"] if origin(url) == origin(report["target"])})),
            ("canonical", page["canonical"])):
            observations, unknown, issues = [], [], []
            for target in targets:
                response = responses.get(target)
                if response is None or response["http_status"] in (401, 403, 407, 429):
                    unknown.append(target)
                    if response is not None:
                        observations.append({"target_url": target, "http_status": response["http_status"], "availability": "access_limited"})
                    continue
                item = {"target_url": target, "final_url": response["url"], "http_status": response["http_status"],
                        "redirects": response["redirects"], "collected_at": response["collected_at"]}
                observations.append(item)
                if not 200 <= response["http_status"] < 300 or response["redirects"]:
                    issues.append(target)
            incomplete_links = category == "internal_link" and page.get("links_extraction_limited", page.get("extraction_limited", False))
            status = "warning" if issues else "not_checked" if unknown or incomplete_links else "pass" if targets else "not_applicable"
            report["findings"].append(finding(f"{category}_target_response", page["url"], status, "medium" if category == "canonical" else "low",
                f"Observed {len(observations)} of {len(targets)} retained {category.replace('_', ' ')} destination response(s); {len(issues)} returned a non-success status or redirects. {len(unknown)} retained destinations remain unverified."
                + (" Hyperlink extraction was incomplete; omitted destinations remain unknown." if incomplete_links else ""),
                "Review observed failures and link directly to intended final URLs. Unvisited, off-origin and access-limited targets remain unknown.",
                collected_at=page["fetched_at"], reference="canonical" if category == "canonical" else "http",
                related_urls=sorted(set(issues)), unverified_urls=sorted(set(unknown)), destination_observations=observations,
                links_extraction_limited=incomplete_links))
        noindex_targets, unchecked, checked = [], [], []
        for target in page["canonical"]:
            response = responses.get(target)
            destination = pages.get(response["url"]) if response is not None and 200 <= response["http_status"] < 300 else None
            if destination is None:
                unchecked.append(target)
            else:
                checked.append(target)
                if destination["noindex_observations"]:
                    noindex_targets.append({"url": target, "directives": destination["noindex_observations"]})
        report["findings"].append(finding("canonical_target_noindex", page["url"],
            "warning" if noindex_targets else "not_checked" if unchecked else "pass" if checked else "not_applicable", "medium",
            f"Found noindex/none directives at {len(noindex_targets)} observed canonical destination(s); {len(unchecked)} destinations remain unverified.",
            "Confirm the intended canonical and indexing policy before changing either. These directives do not establish actual index membership.",
            collected_at=page["fetched_at"], reference="canonical", related_urls=[item["url"] for item in noindex_targets],
            target_directives=noindex_targets, unverified_urls=unchecked))


def _finish(report: dict) -> dict:
    _record_duplicates(report)
    _record_destination_checks(report)
    report["pages"].sort(key=lambda page: (page["url"], page["requested_url"]))
    report["findings"].sort(key=lambda item: (item["url"], item["rule_id"]))
    report["coverage"]["discovered_urls"] = sorted(set(report["coverage"]["discovered_urls"]))
    report["coverage"]["pages_analysed"] = len(report["pages"])
    report["coverage"]["stop_reasons"] = list(dict.fromkeys(report["coverage"]["stop_reasons"]))
    report["summary"] = {"statuses": dict(sorted(Counter(item["status"] for item in report["findings"]).items())),
                         "issues_by_severity": dict(sorted(Counter(item["severity"] for item in report["findings"] if item["status"] in ("fail", "warning")).items()))}
    return report


def audit_offline(path: Path, target: str, *, max_bytes: int = 2_000_000) -> dict:
    target = normalise_url(target)
    report = _base_report(target, "offline_source_html", {"max_bytes": max_bytes, "max_pages": 1})
    with path.open("rb") as source:
        body = source.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise FetchError("response_too_large", "Saved HTML exceeds --max-bytes; no partial HTML was analysed.")
    page, findings = analyse_html(target, _decode(body, {}), collected_at=report["collected_at"], source_bytes=len(body))
    page["source_file"] = str(path.resolve())
    report["pages"].append(page)
    report["findings"].extend(findings)
    report["coverage"].update({"discovered_urls": [target], "complete": not page["extraction_limited"],
        "completeness_scope": "one supplied HTML snapshot only; links were not fetched",
        "robots": {"status": "not_checked", "reason": "Offline mode never makes network requests."}})
    report["checks_not_performed"].append("HTTP headers/status, redirects, robots.txt and sitemap retrieval: offline mode uses only the supplied file.")
    return _finish(report)


def _read_robots(client: SafeClient, report: dict) -> RobotsPolicy | None:
    url = client.scope + "/robots.txt"
    when = utc_now()
    try:
        response = client.fetch(url)
        if response.status in (404, 410):
            report["coverage"]["robots"] = {"url": url, "http_status": response.status, "status": "absent", "policy": "Crawling permitted after an observed 404/410; absence is not an SEO failure."}
            report["findings"].append(finding("robots_available", url, "not_applicable", "info",
                f"robots.txt returned HTTP {response.status}; no published rules were available.",
                "Add robots.txt only when deliberate crawl controls or sitemap discovery are needed.", collected_at=when, reference="robots"))
            return RobotsPolicy()
        if response.status != 200:
            raise FetchError("robots_unavailable", f"robots.txt returned HTTP {response.status}; crawling stopped conservatively.")
        text = _decode(response.body, response.headers)
        if _is_html(response.headers, response.body) or re.search(r"<(?:html|!doctype|body)\b", text[:1024], re.I):
            raise FetchError("robots_invalid_content", "robots.txt returned HTML instead of crawl rules.")
        policy = RobotsPolicy(text)
        meaningful = any(line.split("#", 1)[0].strip() for line in text.splitlines())
        if meaningful and not policy.recognised_lines:
            raise FetchError("robots_unrecognised", "robots.txt contained no recognised directives; crawling stopped conservatively.")
        client.delay = max(client.delay, policy.crawl_delay())
        tokens = (PRODUCT_TOKEN, "Googlebot", "Bingbot", "OAI-SearchBot", "GPTBot", "ClaudeBot", "Claude-SearchBot", "PerplexityBot")
        report["coverage"]["robots"] = {"url": response.url, "http_status": 200, "status": "parsed",
            "effective_delay_seconds": client.delay, "declared_sitemaps": policy.sitemaps,
            "target_path_decisions": {token: policy.can_fetch(report["target"], token) for token in tokens},
            "decision_scope": "Rules at the requested target path only; bot names have different purposes and these observations do not establish indexing, training or AI visibility."}
        report["findings"].append(finding("robots_available", url, "pass", "info", "robots.txt was fetched and parsed within the audit limits.",
            "Preserve deliberate crawl and AI-training preferences; review each bot's purpose before making changes.", collected_at=when, reference="robots"))
        return policy
    except FetchError as exc:
        report["coverage"]["robots"] = {"url": url, "status": "unavailable", "reason": str(exc), "error_code": exc.code}
        report["coverage"]["stop_reasons"].append(exc.code)
        report["findings"].append(finding("robots_available", url, "not_checked", "info", str(exc),
            "Resolve access or use an authorised offline HTML snapshot. No site pages were crawled after this failure.", collected_at=when, reference="robots"))
        return None


def _sitemap_urls(client: SafeClient, policy: RobotsPolicy, report: dict) -> set[str]:
    candidates = policy.sitemaps or [client.scope + "/sitemap.xml"]
    pending = deque((url, 0) for url in candidates)
    seen: set[str] = set()
    urls: set[str] = set()
    while pending and len(seen) < 3 and len(urls) < 1000:
        raw_url, depth = pending.popleft()
        try:
            url = normalise_url(raw_url, client.scope + "/")
            if origin(url) != client.scope:
                report["coverage"]["skipped"].append({"url": url, "reason": "sitemap_outside_origin"})
                continue
            if url in seen:
                continue
            seen.add(url)
            response = client.fetch(url, allowed=policy.can_fetch)
            _check_access_response(response)
            record = {"url": url, "http_status": response.status, "urls_observed": 0}
            report["coverage"]["sitemaps"].append(record)
            if response.status in (404, 410):
                record["status"] = "absent"
                continue
            if response.status != 200:
                record["status"] = "unavailable"
                report["coverage"]["stop_reasons"].append("sitemap_unavailable")
                continue
            # External entities are never needed in a sitemap. Reject DTDs before
            # parsing, including UTF-16/32 NUL-interleaved declarations.
            compact = response.body.replace(b"\x00", b"").upper()
            if b"<!DOCTYPE" in compact or b"<!ENTITY" in compact:
                raise FetchError("sitemap_unsafe_xml", "Sitemap DTD/entity declarations are not supported.")
            document = ET.fromstring(response.body)
            kind = document.tag.rsplit("}", 1)[-1]
            if kind not in ("urlset", "sitemapindex"):
                raise ValueError("Expected urlset or sitemapindex root.")
            namespace = document.tag[:-len(kind)]
            if namespace not in ("", "{http://www.sitemaps.org/schemas/sitemap/0.9}"):
                raise ValueError("Unsupported sitemap namespace.")
            item_tag = namespace + ("url" if kind == "urlset" else "sitemap")
            loc_tag = namespace + "loc"
            entries = [node.text.strip() for item in document if item.tag == item_tag
                       for node in item if node.tag == loc_tag and node.text]
            record.update({"status": "parsed", "kind": kind, "locations_observed": len(entries)})
            for entry in entries[:1000]:
                try:
                    candidate = normalise_url(entry)
                    if origin(candidate) != client.scope:
                        continue
                    if kind == "sitemapindex":
                        if depth < 1:
                            pending.append((candidate, depth + 1))
                    elif len(urls) < 1000:
                        urls.add(candidate)
                except FetchError:
                    record["invalid_location_count"] = record.get("invalid_location_count", 0) + 1
            record["urls_observed"] = len(entries) if kind == "urlset" else 0
            if len(entries) > 1000:
                report["coverage"]["stop_reasons"].append("sitemap_location_limit")
        except (BudgetExceeded, CrawlStopped):
            raise
        except (FetchError, ET.ParseError, ValueError) as exc:
            report["coverage"]["sitemaps"].append({"url": raw_url, "status": "not_checked", "reason": str(exc)})
            report["coverage"]["stop_reasons"].append("sitemap_unavailable")
    if pending:
        report["coverage"]["stop_reasons"].append("sitemap_document_limit")
    return urls


def audit_live(target: str, *, max_pages: int = 30, max_depth: int = 3,
               timeout: float = 10.0, delay: float = 0.25, max_bytes: int = 2_000_000,
               max_requests: int = 100, max_total_bytes: int = 20_000_000,
               max_seconds: float = 120.0, allow_localhost: bool = False) -> dict:
    target = normalise_url(target)
    limits = {"max_pages": max_pages, "max_depth": max_depth, "timeout_seconds": timeout,
        "delay_seconds": delay, "max_bytes_per_response": max_bytes, "max_requests": max_requests,
        "max_total_bytes": max_total_bytes, "max_seconds": max_seconds,
        "max_redirects": 5, "max_sitemap_documents": 3, "max_sitemap_locations": 1000,
        "allow_localhost": allow_localhost}
    report = _base_report(target, "live_source_html", limits)
    client = SafeClient(target, timeout=timeout, delay=delay, max_bytes=max_bytes,
        max_requests=max_requests, max_total_bytes=max_total_bytes,
        max_seconds=max_seconds, allow_localhost=allow_localhost)
    policy = _read_robots(client, report)
    sitemap_urls: set[str] = set()
    seen: set[str] = set()
    visited_finals: set[str] = set()
    pending = deque([(target, 0)])
    discovered = {target}
    try:
        if policy is None:
            return _finish(report)
        if not policy.can_fetch(target):
            report["coverage"]["stop_reasons"].append("target_robots_disallowed")
            report["coverage"]["skipped"].append({"url": target, "reason": "robots_disallowed"})
            report["findings"].append(finding("target_crawl_permission", target, "warning", "info",
                "robots.txt disallows the requested target for EWebCitySEO; its content was not fetched.",
                "Confirm the intended crawl policy. Do not change search or training rules merely to silence this audit.", collected_at=utc_now(), reference="robots"))
            return _finish(report)
        report["findings"].append(finding("target_crawl_permission", target, "pass", "info",
            "The observed robots.txt policy permits EWebCitySEO to request the target path. This does not establish permission for other bots or actual index membership.",
            "Preserve deliberate crawl controls and verify each crawler's own policy before changing it.",
            collected_at=utc_now(), reference="robots", product_token=PRODUCT_TOKEN,
            robots_status=report["coverage"]["robots"].get("status")))
        sitemap_urls = _sitemap_urls(client, policy, report)
        discovered.update(sitemap_urls)
        pending.extend((url, 0) for url in sorted(sitemap_urls) if url != target)
        while pending and report["coverage"]["pages_fetched"] < max_pages:
            url, depth = pending.popleft()
            if url in seen or url in visited_finals:
                continue
            seen.add(url)
            if depth > max_depth:
                report["coverage"]["skipped"].append({"url": url, "reason": "depth_limit"})
                report["coverage"]["stop_reasons"].append("depth_limit")
                continue
            if Path(urlsplit(url).path).suffix.lower() in ASSET_EXTENSIONS:
                report["coverage"]["skipped"].append({"url": url, "reason": "non_html_extension"})
                continue
            if not policy.can_fetch(url):
                report["coverage"]["skipped"].append({"url": url, "reason": "robots_disallowed"})
                continue
            when = utc_now()
            try:
                response = client.fetch(url, allowed=policy.can_fetch)
                report["coverage"]["pages_fetched"] += 1
                report["responses"].append({"requested_url": url, "url": response.url,
                    "http_status": response.status, "redirects": response.redirects,
                    "content_type": response.headers.get("content-type"), "collected_at": when})
                _check_access_response(response)
                if response.url in visited_finals:
                    report["coverage"]["skipped"].append({"url": url, "reason": "final_url_already_analysed", "final_url": response.url})
                    continue
                visited_finals.add(response.url)
                if not _is_html(response.headers, response.body):
                    report["coverage"]["skipped"].append({"url": url, "reason": "non_html_response", "http_status": response.status})
                    report["findings"].append(finding("http_status", response.url,
                        "pass" if 200 <= response.status < 300 else "fail", "high",
                        f"Observed HTTP {response.status}; the response was not HTML and no HTML checks were performed.",
                        "Check whether this URL is intended to be a public HTML page.", collected_at=when, reference="http", http_status=response.status))
                    continue
                page, findings = analyse_html(response.url, _decode(response.body, response.headers),
                    collected_at=when, http_status=response.status, headers=response.headers,
                    requested_url=url, redirects=response.redirects, source_bytes=len(response.body))
                page["depth"] = depth
                page["in_inspected_sitemap"] = url in sitemap_urls
                report["pages"].append(page)
                report["findings"].extend(findings)
                if page["extraction_limited"]:
                    report["coverage"]["stop_reasons"].append("page_extraction_limit")
                if url in sitemap_urls:
                    for rule, status, observation, recommendation in (
                        ("sitemap_url_response", "pass" if response.status == 200 and not response.redirects else "warning",
                         f"Inspected sitemap lists this URL; its final status is {response.status} with {len(response.redirects)} redirect(s).",
                         "List the intended canonical, successful public URL directly in the sitemap."),
                        ("sitemap_url_noindex", "warning" if page["noindex_observations"] else "pass",
                         "A sitemap URL has a noindex/none directive." if page["noindex_observations"] else "No noindex/none directive was observed for this inspected sitemap URL.",
                         "Align sitemap membership with the intended indexing policy; do not remove intentional noindex automatically."),
                        ("sitemap_url_canonical", "warning" if page["canonical"] and response.url not in page["canonical"] else "pass" if page["canonical"] else "not_applicable",
                         "Compared source canonical declarations with this inspected sitemap URL.",
                         "List the intended canonical URL and verify the chosen destination before changing either signal.")):
                        report["findings"].append(finding(rule, response.url, status, "low", observation, recommendation,
                            collected_at=when, reference="sitemap", canonical=page["canonical"], requested_url=url))
                if 200 <= response.status < 300:
                    for link in sorted(set(page["links"] + page["canonical"])):
                        if origin(link) == client.scope and link not in discovered:
                            discovered.add(link)
                            pending.append((link, depth + 1))
            except (BudgetExceeded, CrawlStopped):
                raise
            except FetchError as exc:
                report["coverage"]["skipped"].append({"url": url, "reason": exc.code, "detail": str(exc)})
                report["coverage"]["stop_reasons"].append("resource_unavailable")
                report["findings"].append(finding("resource_retrieval", url, "not_checked", "info", str(exc),
                    "Resolve access or audit an authorised saved snapshot; retrieval failure does not prove an SEO defect.", collected_at=when, reference="http", error_code=exc.code))
        if pending:
            report["coverage"]["stop_reasons"].append("page_limit")
        report["coverage"]["complete"] = not report["coverage"]["stop_reasons"] and not any(item["reason"] == "robots_disallowed" for item in report["coverage"]["skipped"])
    except (BudgetExceeded, CrawlStopped) as exc:
        report["coverage"]["stop_reasons"].append(exc.code)
        stopped_url = getattr(exc, "url", target)
        report["coverage"]["skipped"].append({"url": stopped_url, "reason": exc.code, "detail": str(exc)})
        if isinstance(exc, CrawlStopped):
            report["findings"].append(finding("resource_retrieval", stopped_url, "not_checked", "info", str(exc),
                "Wait for access/rate limits to be resolved or use an authorised saved HTML snapshot; do not bypass the restriction.",
                collected_at=utc_now(), reference="http", http_status=exc.http_status, error_code=exc.code))
    finally:
        report["coverage"].update({"requests": client.requests, "bytes_received": client.bytes_received,
            "discovered_urls": sorted(discovered), "elapsed_seconds": round(__import__("time").monotonic() - client.started, 3)})
    return _finish(report)


def _bounded_int(minimum: int, maximum: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Expected an integer.") from exc
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"Expected a value from {minimum} to {maximum}.")
        return number
    return parse


def _bounded_float(minimum: float, maximum: float):
    def parse(value: str) -> float:
        try:
            number = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Expected a number.") from exc
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"Expected a value from {minimum} to {maximum}.")
        return number
    return parse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Canonical HTTP(S) target and exact origin scope.")
    parser.add_argument("--output", type=Path, required=True, help="Directory for audit.json, report.html and fixes.md.")
    parser.add_argument("--html", type=Path, help="Analyse one saved HTML file with no network access.")
    parser.add_argument("--max-pages", type=_bounded_int(1, 500), default=30)
    parser.add_argument("--max-depth", type=_bounded_int(0, 10), default=3)
    parser.add_argument("--timeout", type=_bounded_float(0.1, 60), default=10.0)
    parser.add_argument("--delay", type=_bounded_float(0, 60), default=0.25)
    parser.add_argument("--max-bytes", type=_bounded_int(1024, 10_000_000), default=2_000_000)
    parser.add_argument("--max-requests", type=_bounded_int(1, 2000), default=100)
    parser.add_argument("--max-total-bytes", type=_bounded_int(1024, 100_000_000), default=20_000_000)
    parser.add_argument("--max-seconds", type=_bounded_float(0.1, 3600), default=120.0)
    parser.add_argument("--allow-localhost", action="store_true", help="Explicitly allow localhost and literal loopback targets only; never other private networks.")
    parser.add_argument("--compare", type=Path, help="Prior compatible audit.json; missing coverage is never proof of resolution.")
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    args = parser.parse_args(argv)
    try:
        target = normalise_url(args.url)
        if args.html:
            report = audit_offline(args.html, target, max_bytes=args.max_bytes)
        else:
            report = audit_live(target, max_pages=args.max_pages, max_depth=args.max_depth,
                timeout=args.timeout, delay=args.delay, max_bytes=args.max_bytes,
                max_requests=args.max_requests, max_total_bytes=args.max_total_bytes,
                max_seconds=args.max_seconds, allow_localhost=args.allow_localhost)
        # Imported only on the CLI output path; analyse_html stays a pure helper.
        from reporting import write_reports
        write_reports(report, args.output, args.compare)
        print(json.dumps({"output": str(args.output.resolve()), "mode": report["mode"],
            "pages_analysed": report["coverage"]["pages_analysed"],
            "stop_reasons": report["coverage"]["stop_reasons"], "summary": report["summary"]}, ensure_ascii=False))
        return 0 if report["pages"] else 1
    except (FetchError, OSError, ValueError) as exc:
        print(f"Audit could not complete: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
