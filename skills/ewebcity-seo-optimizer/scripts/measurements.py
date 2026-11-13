"""Import bounded, user-supplied performance evidence without making requests.

Supported inputs: Lighthouse JSON, PageSpeed Insights JSON, and CrUX API JSON.
Values remain attributed to their original URL, device, time and measurement mode.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import stat
from urllib.parse import urlsplit

from safe_http import FetchError, normalise_url, origin

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_FILES = 8

PSI_REFERENCE = "https://developers.google.com/speed/docs/insights/rest/v5/pagespeedapi/runpagespeed"
CRUX_REFERENCE = "https://developer.chrome.com/docs/crux/api"
THRESHOLD_REFERENCE = "https://web.dev/articles/defining-core-web-vitals-thresholds"

# id: label, unit, good upper bound, needs-improvement upper bound.
METRICS = {
    "lcp": ("Largest contentful paint", "ms", 2500, 4000),
    "inp": ("Interaction to next paint", "ms", 200, 500),
    "cls": ("Cumulative layout shift", "score", 0.1, 0.25),
    "fcp": ("First contentful paint", "ms", 1800, 3000),
    "ttfb": ("Time to first byte", "ms", 800, 1800),
    "tbt": ("Total blocking time", "ms", None, None),
    "speed_index": ("Speed index", "ms", None, None),
}
LAB_KEYS = {
    "largest-contentful-paint": "lcp", "cumulative-layout-shift": "cls",
    "first-contentful-paint": "fcp", "total-blocking-time": "tbt", "speed-index": "speed_index",
}
PSI_KEYS = {
    "LARGEST_CONTENTFUL_PAINT_MS": "lcp", "INTERACTION_TO_NEXT_PAINT": "inp",
    "INTERACTION_TO_NEXT_PAINT_MS": "inp", "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
    "FIRST_CONTENTFUL_PAINT_MS": "fcp", "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb",
}
CRUX_KEYS = {
    "largest_contentful_paint": "lcp", "interaction_to_next_paint": "inp",
    "cumulative_layout_shift": "cls", "first_contentful_paint": "fcp",
    "experimental_time_to_first_byte": "ttfb",
}


def _number(value, *, strings: bool = False) -> float | int | None:
    if strings and isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if 0 <= value < 1e15 and math.isfinite(value) else None


def _choice(value, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


def _metric(key: str, value: float | int, *, field: bool, **extra) -> dict:
    label, unit, good, moderate = METRICS[key]
    rating = "unrated"
    if field and good is not None:
        rating = "good" if value <= good else "needs_improvement" if value <= moderate else "poor"
    return {"id": key, "label": label, "value": value, "unit": unit, "rating": rating, **extra}


def _url(value, target: str, name: str, *, origin_only: bool = False) -> str:
    try:
        url = normalise_url(value)
        if origin(url) != origin(target):
            raise ValueError(f"{name}: performance evidence belongs to another origin")
        if origin_only:
            parts = urlsplit(url)
            if parts.path != "/" or parts.query:
                raise ValueError(f"{name}: origin evidence must identify an origin, not a page path")
            return origin(url)
        return url
    except FetchError as exc:
        raise ValueError(f"{name}: performance evidence needs a valid HTTP(S) URL without credentials") from exc


def _timestamp(value, issues: list[str], name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and len(value) <= 80:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.isoformat()
        except ValueError:
            pass
    issues.append(f"{name}: invalid or timezone-free measurement timestamp was omitted")
    return None


def _collection_period(value, issues: list[str], name: str) -> dict | None:
    if value is None:
        return None
    try:
        dates = []
        for key in ("firstDate", "lastDate"):
            part = value.get(key, value.get("endDate") if key == "lastDate" else None)
            if not isinstance(part, dict) or any(type(part.get(k)) is not int for k in ("year", "month", "day")):
                raise ValueError
            dates.append(date(part["year"], part["month"], part["day"]))
        if dates[0] > dates[1]:
            raise ValueError
        return {"start": dates[0].isoformat(), "end": dates[1].isoformat()}
    except (AttributeError, TypeError, ValueError, OverflowError):
        issues.append(f"{name}: invalid collection period was omitted")
        return None


def _lab(data: dict, target: str, name: str, issues: list[str]) -> dict | None:
    if data.get("runtimeError"):
        issues.append(f"{name}: Lighthouse reported a runtime error; its lab metrics were not imported")
        return None
    url = _url(data.get("finalUrl") or data.get("finalDisplayedUrl") or data.get("requestedUrl"), target, name)
    audits = data.get("audits")
    if not isinstance(audits, dict):
        raise ValueError(f"{name}: Lighthouse audits must be an object")
    metrics = []
    for source_key, key in LAB_KEYS.items():
        audit = audits.get(source_key)
        if audit is None:
            continue
        if not isinstance(audit, dict) or _choice(audit.get("scoreDisplayMode"), {"error", "notApplicable", "manual", "informative"}):
            issues.append(f"{name}: {source_key} has no usable lab measurement")
            continue
        value = _number(audit.get("numericValue"))
        if value is None:
            issues.append(f"{name}: {source_key} has no finite non-negative numericValue")
            continue
        expected_units = {"unitless"} if key == "cls" else {"millisecond", "milliseconds", "ms"}
        if audit.get("numericUnit") is not None and not _choice(audit["numericUnit"], expected_units):
            issues.append(f"{name}: {source_key} uses an unsupported numericUnit")
            continue
        metrics.append(_metric(key, value, field=False, source_key=source_key))
    if not metrics:
        issues.append(f"{name}: no supported Lighthouse numeric measurements were available")
        return None
    settings = data.get("configSettings") if isinstance(data.get("configSettings"), dict) else {}
    form_factor = settings.get("formFactor") or settings.get("emulatedFormFactor")
    version = data.get("lighthouseVersion")
    warnings = data.get("runWarnings")
    if isinstance(warnings, list) and warnings:
        issues.append(f"{name}: Lighthouse recorded {len(warnings)} run warning(s); review the original export")
    return {
        "source": "Lighthouse", "kind": "lab", "scope": "url", "url": url,
        "collected_at": _timestamp(data.get("fetchTime"), issues, name),
        "device": form_factor if _choice(form_factor, {"mobile", "desktop"}) else "not recorded",
        "aggregation": "navigation sample", "metrics": metrics,
        "source_version": version[:80] if isinstance(version, str) else "not recorded",
        "throttling_method": settings.get("throttlingMethod") if _choice(settings.get("throttlingMethod"), {"simulate", "devtools", "provided"}) else "not recorded",
        "reference_url": PSI_REFERENCE,
        "note": "Lab diagnostics from the supplied run. TBT is not INP; lab values do not establish a field Core Web Vitals pass.",
    }


def _psi_cls(value, data: dict, name: str, issues: list[str]):
    # PSI historically scales CLS by 100, unlike Lighthouse and the CrUX API.
    # Derive the scale only when the exported histogram proves its convention.
    bins = data.get("distributions")
    if isinstance(bins, list) and len(bins) >= 2 and all(isinstance(x, dict) for x in bins[:2]):
        boundaries = (_number(bins[0].get("max")), _number(bins[1].get("max")))
        if boundaries == (10, 25):
            return value / 100, "Divided by 100 using supplied CLS histogram boundaries 10 and 25"
        if boundaries == (0.1, 0.25):
            return value, "Unitless CLS confirmed by supplied histogram boundaries 0.1 and 0.25"
    issues.append(f"{name}: PSI CLS omitted because its scale is not established by histogram boundaries; supply a CrUX API export")
    return None, None


def _psi_field(data: dict, target: str, name: str, issues: list[str], *, scope: str, timestamp) -> dict | None:
    metrics_data = data.get("metrics")
    if not isinstance(metrics_data, dict) or not metrics_data:
        issues.append(f"{name}: no {scope}-level PSI field metrics were available")
        return None
    if data.get("origin_fallback") is not None and type(data["origin_fallback"]) is not bool:
        raise ValueError(f"{name}: origin_fallback must be a boolean")
    if data.get("origin_fallback") is True:
        scope = "origin"
    url = _url(data.get("id"), target, name, origin_only=scope == "origin")
    metrics, devices, seen_keys = [], set(), set()
    for source_key, key in PSI_KEYS.items():
        part = metrics_data.get(source_key)
        if part is None:
            continue
        value = _number(part.get("percentile")) if isinstance(part, dict) else None
        if value is None:
            issues.append(f"{name}: {source_key} has no usable field percentile")
            continue
        if key in seen_keys:
            issues.append(f"{name}: duplicate {key} field metric alias was omitted")
            continue
        seen_keys.add(key)
        extra = {"source_key": source_key, "raw_value": value}
        if key == "cls":
            value, scale = _psi_cls(value, part, name, issues)
            if value is None:
                continue
            extra["normalisation"] = scale
        factor = part.get("formFactor")
        device = factor if _choice(factor, {"PHONE", "DESKTOP", "TABLET"}) else "not recorded"
        devices.add(device)
        extra["device"] = device
        metrics.append(_metric(key, value, field=True, **extra))
    if not metrics:
        issues.append(f"{name}: no supported {scope}-level PSI field percentiles were imported")
        return None
    if len(devices) > 1:
        issues.append(f"{name}: field metrics mix device labels; inspect the original export before comparing")
    return {
        "source": "PageSpeed Insights / CrUX", "kind": "field", "scope": scope, "url": url,
        "collected_at": _timestamp(timestamp, issues, name),
        "device": next(iter(devices)) if len(devices) == 1 else "mixed / inspect export",
        "aggregation": "p75", "metrics": metrics, "reference_url": PSI_REFERENCE,
        "collection_period": None,
        "note": "Supplied field percentiles. Exact collection dates are not recorded in this PSI export; analysis time is not the field collection window.",
    }


def _crux(data: dict, target: str, name: str, issues: list[str]) -> dict | None:
    key, metrics_data = data.get("key"), data.get("metrics")
    if not isinstance(key, dict) or not isinstance(metrics_data, dict):
        raise ValueError(f"{name}: CrUX record requires key and metrics objects")
    if bool(key.get("url")) == bool(key.get("origin")):
        raise ValueError(f"{name}: CrUX key must identify exactly one URL or origin")
    scope = "url" if key.get("url") else "origin"
    url = _url(key.get(scope), target, name, origin_only=scope == "origin")
    metrics = []
    for source_key, metric_id in CRUX_KEYS.items():
        part = metrics_data.get(source_key)
        if part is None:
            continue
        percentiles = part.get("percentiles") if isinstance(part, dict) else None
        value = _number(percentiles.get("p75"), strings=metric_id == "cls") if isinstance(percentiles, dict) else None
        if value is None:
            issues.append(f"{name}: {source_key} has no usable p75 value")
            continue
        metrics.append(_metric(metric_id, value, field=True, source_key=source_key))
    if not metrics:
        issues.append(f"{name}: no supported CrUX p75 measurements were available")
        return None
    factor = key.get("formFactor")
    device = factor if _choice(factor, {"PHONE", "TABLET", "DESKTOP"}) else "all form factors" if factor is None else "not recorded"
    return {
        "source": "CrUX API", "kind": "field", "scope": scope, "url": url,
        "collected_at": None, "device": device, "aggregation": "p75", "metrics": metrics,
        "collection_period": _collection_period(data.get("collectionPeriod"), issues, name),
        "reference_url": CRUX_REFERENCE,
        "note": "Field evidence from the supplied CrUX record. Origin data describes aggregate experiences across that origin, not every page.",
    }


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key[:80]}")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("Non-finite JSON numeric constant")


def load_performance_evidence(paths: list[Path], target: str) -> dict:
    """Validate all supplied exports before any crawl or output mutation.

    This imports evidence, not authenticated provider claims. No network calls,
    browser launch, JavaScript execution or automatic merging of different runs.
    """
    paths = list(paths)
    if len(paths) > MAX_FILES:
        raise ValueError(f"At most {MAX_FILES} performance JSON exports can be imported")
    result = {"items": [], "issues": [], "note": "User-supplied exports; provenance is recorded but the source is not authenticated. Lab and field results remain separate. No overall SEO or AI-visibility score is calculated."}
    seen, total = set(), 0
    for raw_path in paths:
        path = Path(raw_path)
        name = path.name
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError(f"{name}: expected a regular JSON file")
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        total += len(raw)
        if len(raw) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError("Performance exports exceed the 10 MiB/file or 40 MiB/total input limit")
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen:
            result["issues"].append(f"{name}: duplicate input content was imported only once")
            continue
        seen.add(digest)
        try:
            data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_strict_object, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError(f"{name}: expected valid, finite UTF-8 JSON with unique object keys") from exc
        if not isinstance(data, dict) or data.get("error"):
            raise ValueError(f"{name}: expected a successful performance export object")
        items = []
        if any(k in data for k in ("lighthouseResult", "loadingExperience", "originLoadingExperience")):
            if "lighthouseResult" in data:
                if not isinstance(data["lighthouseResult"], dict):
                    raise ValueError(f"{name}: lighthouseResult must be an object")
                items.append(_lab(data["lighthouseResult"], target, name, result["issues"]))
            for key, scope in (("loadingExperience", "url"), ("originLoadingExperience", "origin")):
                if key in data:
                    if not isinstance(data[key], dict):
                        raise ValueError(f"{name}: {key} must be an object")
                    items.append(_psi_field(data[key], target, name, result["issues"], scope=scope, timestamp=data.get("analysisUTCTimestamp")))
        elif isinstance(data.get("audits"), dict):
            items.append(_lab(data, target, name, result["issues"]))
        elif "record" in data:
            if not isinstance(data["record"], dict):
                raise ValueError(f"{name}: CrUX record must be an object")
            items.append(_crux(data["record"], target, name, result["issues"]))
        else:
            raise ValueError(f"{name}: unsupported export; use Lighthouse, PageSpeed Insights or CrUX API JSON")
        for item in items:
            if item:
                demonstration = data.get("_demonstration")
                if demonstration is True or (isinstance(demonstration, str) and demonstration.strip()):
                    item["demonstration"] = True
                    item["note"] = "SYNTHETIC DEMONSTRATION INPUT — not actual provider measurements. " + item.get("note", "")
                item.update(input_file=name, input_sha256=digest, thresholds_reference=THRESHOLD_REFERENCE,
                            reference_checked_at="2026-11-12")
                result["items"].append(item)
    return result
