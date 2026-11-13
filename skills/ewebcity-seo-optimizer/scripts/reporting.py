"""Render audit evidence and compare explicit checks without inventing resolutions."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from html import escape
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


STATUSES = {"pass", "fail", "warning", "not_applicable", "not_checked"}
ISSUE_STATUSES = {"fail", "warning"}
MAX_BASELINE_BYTES = 20 * 1024 * 1024


def _origin(url: str) -> tuple:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("Expected an absolute HTTP(S) target")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Credential-bearing targets are not supported")
        return (parsed.scheme.lower(), parsed.hostname.lower(),
                parsed.port or (443 if parsed.scheme == "https" else 80))
    except (TypeError, ValueError) as exc:
        raise ValueError("Report target must be an absolute HTTP(S) URL") from exc


def _validate_report(report: dict) -> None:
    if not isinstance(report, dict):
        raise ValueError("The audit report must be a JSON object")
    for field in ("schema_version", "tool_version", "target", "mode"):
        if not isinstance(report.get(field), str) or not report[field]:
            raise ValueError(f"The report needs a non-empty {field}")
    _origin(report["target"])
    if not isinstance(report.get("findings"), list) or not isinstance(report.get("pages"), list):
        raise ValueError("The report needs findings and pages arrays")
    if not all(isinstance(page, dict) for page in report["pages"]):
        raise ValueError("Each page must be an object")
    keys = set()
    for finding in report["findings"]:
        if not isinstance(finding, dict):
            raise ValueError("Each finding must be an object")
        if not all(isinstance(finding.get(key), str) and finding[key] for key in ("rule_id", "url")):
            raise ValueError("Every finding needs a rule_id and URL")
        if finding.get("status") not in STATUSES:
            raise ValueError(f"Invalid finding status: {finding.get('status')!r}")
        key = (finding["rule_id"], finding["url"])
        if key in keys:
            raise ValueError(f"Duplicate finding key: {key!r}")
        keys.add(key)


def read_baseline(path: Path) -> dict:
    """Read a bounded data file; never interpret report content as instructions."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BASELINE_BYTES + 1)
    if len(raw) > MAX_BASELINE_BYTES:
        raise ValueError("Baseline is too large (maximum 20 MiB)")
    try:
        report = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Baseline is not valid UTF-8 JSON") from exc
    _validate_report(report)
    return report


def _brief(finding: dict, reason: str | None = None) -> dict:
    result = {key: finding.get(key) for key in ("rule_id", "url", "status", "severity")}
    if reason:
        result["reason"] = reason
    return result


def compare_reports(baseline: dict, current: dict) -> dict:
    """Only an explicit comparable recheck can resolve a previous issue."""
    _validate_report(baseline)
    _validate_report(current)
    old = {(f["rule_id"], f["url"]): f for f in baseline["findings"]}
    new = {(f["rule_id"], f["url"]): f for f in current["findings"]}
    incompatibilities = []
    for field in ("schema_version", "mode", "tool_version"):
        if baseline[field] != current[field]:
            incompatibilities.append(f"Different {field}")
    if _origin(baseline["target"]) != _origin(current["target"]):
        incompatibilities.append("Different target origin")
    comparable = not incompatibilities
    result = {
        "baseline_collected_at": baseline.get("collected_at"),
        "current_collected_at": current.get("collected_at"),
        "comparable": comparable,
        "limitations": incompatibilities,
        "new": [], "persistent": [], "resolved": [], "not_rechecked": [],
        "note": "A missing finding or uncrawled page is not proof that an issue was fixed.",
    }
    observed = {p.get("url") for p in current["pages"] if p.get("url")}
    for key, previous in old.items():
        if previous["status"] not in ISSUE_STATUSES:
            continue
        finding = new.get(key)
        if not comparable:
            result["not_rechecked"].append(_brief(previous, "; ".join(incompatibilities)))
        elif finding is None or finding["status"] == "not_checked":
            result["not_rechecked"].append(_brief(previous, "No explicit comparable check in this run"))
        elif finding["status"] in ISSUE_STATUSES:
            result["persistent"].append(_brief(finding))
        elif finding["status"] in {"pass", "not_applicable"}:
            evidence = previous.get("evidence", {})
            if isinstance(evidence, dict):
                related = evidence.get("comparison_scope_urls", [])
                if not related and previous["rule_id"].startswith("duplicate_"):
                    related = evidence.get("related_urls", [])
            else:
                related = []
            if not isinstance(related, list) or any(not isinstance(url, str) for url in related):
                result["not_rechecked"].append(_brief(previous, "Invalid baseline related-URL evidence"))
            elif any(url not in observed for url in related):
                result["not_rechecked"].append(_brief(previous, "Previously related URLs were not all rechecked"))
            else:
                reason = "Explicit pass" if finding["status"] == "pass" else "Explicitly not applicable; inspect the new evidence"
                result["resolved"].append(_brief(finding, reason))
    if comparable:
        for key, finding in new.items():
            if finding["status"] in ISSUE_STATUSES and (key not in old or old[key]["status"] not in ISSUE_STATUSES):
                result["new"].append(_brief(finding))
    result["counts"] = {key: len(result[key]) for key in ("new", "persistent", "resolved", "not_rechecked")}
    return result


def _plain(value) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return "Not recorded" if value is None else str(value)


def _html(value) -> str:
    return escape(_plain(value), quote=True)


def _auditor(value) -> str:
    """Do not attribute a legacy or malformed report to the current default auditor."""
    return value.strip() if isinstance(value, str) and value.strip() else "Not supplied"


def _has_synthetic_imports(report: dict) -> bool:
    snapshot = report.get("wordpress")
    if isinstance(snapshot, dict) and snapshot.get("_demonstration") is True:
        return True
    measurements = report.get("measurements")
    items = measurements.get("items") if isinstance(measurements, dict) else None
    return isinstance(items, list) and any(isinstance(item, dict) and item.get("demonstration") is True for item in items)


def _link(url) -> str:
    if not isinstance(url, str):
        return _html(url)
    try:
        _origin(url)
    except ValueError:
        return _html(url)
    return f'<a href="{_html(url)}" target="_blank" rel="noopener noreferrer">{_html(url)}</a>'


def _finding_id(finding: dict) -> str:
    return "finding-" + hashlib.sha256((finding["rule_id"] + "\0" + finding["url"]).encode()).hexdigest()[:16]


def _sorted_issues(findings: list) -> list:
    severity = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return sorted((f for f in findings if f["status"] in ISSUE_STATUSES),
                  key=lambda f: (severity.get(f.get("severity"), 5), f["rule_id"], f["url"]))


STATUS_ORDER = ("fail", "warning", "pass", "not_checked", "not_applicable")
STATUS_LABELS = {"fail": "Failed", "warning": "Review", "pass": "Passed", "not_checked": "Not checked", "not_applicable": "Not applicable"}
SEVERITIES = ("critical", "high", "medium", "low", "info")
CATEGORY_LABELS = {
    "crawl": "Crawl & indexing", "content": "Page content", "links": "Links & structure",
    "schema": "Structured data", "experience": "Page experience", "other": "Other checks",
}
RULE_TITLES = {
    "http_status": "Page response", "redirect_chain": "Redirect journey", "title_present": "Page title",
    "title_single": "Document title consistency", "description_present": "Search description",
    "canonical_present": "Canonical declaration", "canonical_single": "Canonical consistency",
    "canonical_valid_url": "Canonical URL format", "canonical_origin": "Canonical destination origin",
    "canonical_target_response": "Canonical destination response", "canonical_target_noindex": "Canonical destination directives",
    "noindex_directive": "Indexing directives", "html_lang": "Document language", "viewport_present": "Viewport declaration",
    "main_heading_present": "Main page heading", "image_alt_attribute": "Image alternatives",
    "jsonld_syntax": "Structured data syntax", "mixed_content_references": "Mixed-content references",
    "base_url_valid": "Document base URL", "link_url_syntax": "Link URL format",
    "duplicate_title": "Repeated page titles", "duplicate_description": "Repeated descriptions",
    "internal_link_target_response": "Internal link destinations", "robots_available": "Robots policy availability",
    "target_crawl_permission": "Permission to crawl the target", "resource_retrieval": "Resource availability",
    "sitemap_url_response": "Sitemap URL response", "sitemap_url_noindex": "Sitemap indexing directives",
    "sitemap_url_canonical": "Sitemap canonical consistency",
}


def _category(finding: dict) -> str:
    rule = finding["rule_id"].lower()
    if rule.startswith(("canonical", "sitemap", "robots", "noindex", "http_", "redirect", "resource_retrieval", "target_crawl")):
        return "crawl"
    if rule.startswith(("title", "description", "duplicate_title", "duplicate_description", "main_heading")):
        return "content"
    if rule.startswith(("internal_link", "link_", "base_", "hreflang")):
        return "links"
    if rule.startswith(("json", "schema", "structured")):
        return "schema"
    if rule.startswith(("image_", "mixed_", "viewport", "html_lang")):
        return "experience"
    return "other"


def _title(finding: dict) -> str:
    return finding.get("title") or RULE_TITLES.get(finding["rule_id"].lower(), finding["rule_id"].replace("_", " ").replace("-", " ").capitalize())


def _date(value) -> str:
    if not value:
        return "Not recorded"
    try:
        from datetime import datetime, timezone
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
        return parsed.strftime("%d %b %Y · %H:%M") + " (timezone not recorded)"
    except (ValueError, TypeError, OverflowError):
        return str(value)


def _number(value) -> str:
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else "Not recorded"


def _icon(name: str) -> str:
    paths = {
        "grid": '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
        "check": '<path d="m5 12 4 4L19 6"/>',
        "flag": '<path d="M5 21V4m0 0c5-4 9 4 14 0v10c-5 4-9-4-14 0"/>',
        "pages": '<rect x="6" y="3" width="14" height="17" rx="2"/><path d="M3 7v13a3 3 0 0 0 3 3M10 8h6m-6 4h6m-6 4h4"/>',
        "compare": '<path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>',
        "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
        "scope": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4"/>',
        "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
        "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
        "print": '<path d="M7 8V3h10v5M7 17H4V9h16v8h-3"/><rect x="7" y="13" width="10" height="8" rx="1"/>',
        "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
        "pulse": '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
        "chevron": '<path d="m8 10 4 4 4-4"/>',
    }
    return '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths.get(name, paths["grid"]) + '</svg>'


def _badge(status: str) -> str:
    return f'<span class="badge status-{status}"><span class="status-dot" aria-hidden="true"></span>{STATUS_LABELS[status]}</span>'


def _bar(counts: Counter, label: str) -> str:
    total = sum(counts.values())
    x = 0.0
    shapes = ['<rect class="bar-track" x="0" y="0" width="1000" height="12" rx="6"/>']
    for status in STATUS_ORDER:
        width = counts[status] / total * 1000 if total else 0
        if width:
            shapes.append(f'<rect class="fill-{status}" x="{x:.3f}" y="0" width="{width:.3f}" height="12"/>')
        x += width
    description = label + ": " + ", ".join(f"{counts[s]} {STATUS_LABELS[s].lower()}" for s in STATUS_ORDER)
    return f'<svg class="distribution-bar" viewBox="0 0 1000 12" preserveAspectRatio="none" role="img" aria-label="{_html(description)}">{"".join(shapes)}</svg>'


def _card(finding: dict, ordinal: int) -> str:
    category = _category(finding)
    severity = finding.get("severity") if finding.get("severity") in SEVERITIES else "unclassified"
    evidence = finding.get("evidence", {})
    observation = evidence.get("observation") if isinstance(evidence, dict) else None
    source = finding.get("reference_url") or finding.get("source_url")
    return f'''<article class="finding" id="{_finding_id(finding)}" data-status="{finding['status']}" data-severity="{severity}" data-category="{category}" data-page="{_html(finding['url'])}">
<div class="finding-top"><div class="finding-labels"><span class="check-index">{ordinal:02d}</span>{_badge(finding['status'])}<span class="category-tag">{CATEGORY_LABELS[category]}</span></div><span class="severity severity-{severity}">{_html(severity.capitalize())} severity</span></div>
<h3>{_html(_title(finding))}</h3><p class="finding-url">{_link(finding['url'])}</p>
<p class="observation">{_html(observation or 'Inspect the recorded evidence and the recommended action below.')}</p>
<details class="finding-details" open><summary><span>Evidence &amp; recommended action</span>{_icon('chevron')}</summary>
<div class="finding-body"><div class="action-panel"><span class="eyebrow">Recommended action</span><p>{_html(finding.get('recommendation'))}</p><dl class="fact-list"><div><dt>Rule</dt><dd><code>{_html(finding['rule_id'])}</code></dd></div><div><dt>Confidence</dt><dd>{_html(finding.get('confidence'))}</dd></div><div><dt>Evidence kind</dt><dd>{_html(finding.get('evidence_kind', 'Not recorded'))}</dd></div></dl></div>
<div class="evidence-panel"><span class="eyebrow">Recorded evidence</span><pre tabindex="0" aria-label="Recorded evidence for {_html(_title(finding))}">{_html(evidence)}</pre></div>
<div class="finding-source"><span>Guidance: {_link(source)}</span><span>Reference checked: {_html(finding.get('reference_checked_at'))}</span></div></div></details></article>'''


_STYLE = r'''
:root{color-scheme:light;--bg:#f4f6fa;--surface:#fff;--surface-2:#f7f9fc;--ink:#182234;--muted:#637087;--line:#e3e8f0;--brand:#16786a;--brand-soft:#e9f5f0;--brand-bright:#5ee0bd;--violet:#7255c5;--fail:#bc3e43;--fail-bg:#fff0ef;--warning:#9b6700;--warning-bg:#fff5df;--pass:#13765a;--pass-bg:#e7f5ee;--unchecked:#65718b;--unchecked-bg:#edf0f7;--na:#919caf;--shadow:0 4px 24px rgba(25,40,65,.035);--hero:#f0f7f4;--focus:#7653d6}
:root[data-theme="dark"]{color-scheme:dark;--bg:#111824;--surface:#192332;--surface-2:#1e2b3c;--ink:#edf3fb;--muted:#a0b1c7;--line:#2d3d51;--brand:#6bdcba;--brand-soft:#203e37;--brand-bright:#7de7c8;--violet:#b9a5ff;--fail:#ff9c9e;--fail-bg:#432a32;--warning:#edc575;--warning-bg:#443a28;--pass:#7ce0b7;--pass-bg:#213d36;--unchecked:#adbbd2;--unchecked-bg:#2b364b;--na:#6c7a90;--shadow:none;--hero:#1c302f;--focus:#c1adff}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#111824;--surface:#192332;--surface-2:#1e2b3c;--ink:#edf3fb;--muted:#a0b1c7;--line:#2d3d51;--brand:#6bdcba;--brand-soft:#203e37;--brand-bright:#7de7c8;--violet:#b9a5ff;--fail:#ff9c9e;--fail-bg:#432a32;--warning:#edc575;--warning-bg:#443a28;--pass:#7ce0b7;--pass-bg:#213d36;--unchecked:#adbbd2;--unchecked-bg:#2b364b;--na:#6c7a90;--shadow:none;--hero:#1c302f;--focus:#c1adff}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}a{color:var(--brand);text-underline-offset:3px;overflow-wrap:anywhere}button,input,select{font:inherit}button,select,summary{cursor:pointer}button{color:inherit}button:disabled{cursor:default}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,pre:focus-visible{outline:3px solid var(--focus);outline-offset:3px}button,input,select{min-height:42px}h1,h2,h3,h4,p{margin-top:0}h1,h2,h3{letter-spacing:-.035em}h1{font-size:clamp(34px,4.2vw,52px);line-height:1.1;font-weight:750;margin-bottom:15px}h2{font-size:24px;line-height:1.25;margin-bottom:7px;font-weight:720}h3{font-size:18px;line-height:1.35;margin-bottom:7px;font-weight:680}p{margin-bottom:13px}small{font-size:12px}.icon{width:20px;height:20px;flex-shrink:0;vertical-align:middle}.skip-link{position:fixed;left:20px;top:-100px;z-index:20;background:var(--surface);padding:12px 18px;border-radius:10px}.skip-link:focus{top:18px}.sidebar{position:fixed;inset:0 auto 0 0;width:224px;padding:32px 20px 22px;background:var(--surface);border-right:1px solid var(--line);display:flex;flex-direction:column;z-index:5}.brand{display:flex;align-items:center;gap:10px;color:var(--ink);font-size:21px;font-weight:780;letter-spacing:-1px;text-decoration:none;padding:0 8px}.brand-mark{width:34px;height:37px;border-radius:11px 11px 11px 3px;background:#16786a;color:#fff;display:grid;place-items:center;font-size:27px;font-weight:700;line-height:1}.brand-mark span{transform:translateY(-1px)}.brand-subtitle{font-size:11px;letter-spacing:.12em;font-weight:650;color:var(--muted);margin:12px 8px 0}.nav-label{font-size:10px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700;margin:46px 14px 12px}.sidebar nav{display:grid;gap:7px}.nav-link{display:flex;align-items:center;gap:12px;padding:11px 13px;border-radius:9px;text-decoration:none;color:var(--muted);font-size:13px;font-weight:600}.nav-link:hover,.nav-link:focus-visible{background:var(--surface-2);color:var(--ink)}.nav-link.primary{background:var(--brand-soft);color:var(--brand)}.nav-count{margin-left:auto;background:var(--surface-2);border:1px solid var(--line);border-radius:6px;font-size:10px;padding:1px 6px;min-width:24px;text-align:center}.sidebar-bottom{margin-top:auto;padding:18px 12px 0;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}.sidebar-bottom strong{display:block;color:var(--ink);font-size:12px;margin-bottom:4px}.workspace{margin-left:224px;max-width:1720px;padding:28px 42px 48px}.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:32px}.breadcrumb{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--muted)}.breadcrumb strong{color:var(--ink);font-weight:600}.top-actions{display:flex;align-items:center;gap:12px}.theme-control{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}.theme-control select{min-height:36px;padding:6px 28px 6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);max-width:100px}.button{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid var(--line);border-radius:9px;padding:8px 14px;background:var(--surface);text-decoration:none;font-weight:600;font-size:12px;line-height:1.3}.button:hover{background:var(--surface-2)}.button-primary{background:var(--brand);border-color:var(--brand);color:var(--surface)}.button-primary:hover{filter:brightness(.95);background:var(--brand)}.eyebrow{display:block;text-transform:uppercase;letter-spacing:.12em;font-size:10px;font-weight:750;color:var(--muted);margin-bottom:10px}.hero{border:1px solid var(--line);background:var(--hero);border-radius:18px;padding:32px 34px;display:grid;grid-template-columns:minmax(0,1.5fr) minmax(210px,.8fr);gap:30px;position:relative;overflow:hidden}.hero .eyebrow{color:var(--brand);display:flex;align-items:center;gap:8px}.hero-title{margin-bottom:12px}.hero-description{font-size:14px;color:var(--muted);max-width:560px;margin:0 0 18px}.target-link{display:inline-flex;align-items:center;gap:10px;font-size:15px;font-weight:650}.target-link a{color:var(--ink);text-decoration:none}.hero-meta{align-self:center;border-left:1px solid var(--line);padding-left:28px;display:grid;gap:17px}.hero-meta dt{font-size:11px;color:var(--muted);margin-bottom:3px}.hero-meta dd{margin:0;font-size:12px;font-weight:600}.collection-pill{display:inline-flex;gap:7px;align-items:center;border:1px solid var(--line);background:var(--surface);padding:5px 9px;border-radius:6px;color:var(--brand);font-size:11px}.collection-pill.partial{color:var(--warning)}.collection-pill .status-dot{width:6px;height:6px}.section{margin-top:32px;scroll-margin-top:24px}.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:18px}.section-heading p{margin:0;color:var(--muted);font-size:12px}.section-number{font-size:10px;font-weight:700;letter-spacing:.12em;color:var(--brand);text-transform:uppercase;display:block;margin-bottom:7px}.section-meta{font-size:11px;color:var(--muted);white-space:nowrap}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:20px 0}.kpi{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:21px 21px 18px;box-shadow:var(--shadow)}.kpi-top{display:flex;justify-content:space-between;gap:10px;align-items:center;color:var(--muted);font-size:11px;font-weight:650}.kpi-icon{width:30px;height:30px;display:grid;place-items:center;border-radius:8px;background:var(--surface-2);color:var(--brand)}.kpi-icon .icon{width:16px;height:16px}.kpi:nth-child(1) .kpi-icon{background:var(--warning-bg);color:var(--warning)}.kpi:nth-child(3) .kpi-icon{background:var(--pass-bg);color:var(--pass)}.kpi:nth-child(4) .kpi-icon{background:var(--unchecked-bg);color:var(--unchecked)}.kpi-value{display:block;font-size:36px;line-height:1.12;font-weight:750;letter-spacing:-1.5px;margin:13px 0 9px;font-variant-numeric:tabular-nums}.kpi-note{font-size:10px;color:var(--muted);line-height:1.5;margin:0}.overview-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1.3fr);gap:18px}.panel{background:var(--surface);border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow);padding:24px}.panel-title{display:flex;align-items:start;justify-content:space-between;gap:16px;margin-bottom:23px}.panel-title h3{font-size:15px;margin-bottom:4px}.panel-title p{font-size:11px;color:var(--muted);margin:0}.panel-total{color:var(--muted);font-size:11px;white-space:nowrap}.panel-total b{color:var(--ink);font-size:18px;margin-right:4px;letter-spacing:-.5px}.distribution-bar{display:block;width:100%;height:12px;border-radius:6px;overflow:hidden}.bar-track{fill:var(--surface-2)}.fill-fail{fill:var(--fail)}.fill-warning{fill:var(--warning)}.fill-pass{fill:var(--pass)}.fill-not_checked{fill:var(--unchecked)}.fill-not_applicable{fill:var(--na)}.status-legend{display:grid;grid-template-columns:1fr 1fr;gap:16px 24px;margin:23px 0 0;padding:0;list-style:none}.status-legend li{display:flex;align-items:center;gap:8px;font-size:11px}.status-legend strong{margin-left:auto;color:var(--ink);font-variant-numeric:tabular-nums}.legend-dot{width:8px;height:8px;border-radius:3px;flex-shrink:0}.legend-fail{background:var(--fail)}.legend-warning{background:var(--warning)}.legend-pass{background:var(--pass)}.legend-not_checked{background:var(--unchecked)}.legend-not_applicable{background:var(--na)}.legend-text{color:var(--muted)}.panel-footnote{margin:20px 0 0;padding-top:16px;border-top:1px solid var(--line);font-size:10px;color:var(--muted)}.category-rows{display:grid;gap:15px}.category-row .distribution-bar{height:6px;margin-top:7px}.category-caption{display:flex;justify-content:space-between;gap:12px;font-size:11px}.category-caption span{color:var(--muted);font-size:10px}.category-caption strong{font-weight:600}.scope-note{display:flex;align-items:flex-start;gap:12px;border:1px solid var(--line);background:var(--surface);border-radius:10px;padding:15px 18px;margin-top:18px;color:var(--muted);font-size:11px}.scope-note .icon{color:var(--brand);width:17px;height:17px;margin-top:1px}.scope-note p{margin:0}.scope-note strong{color:var(--ink);font-weight:600}.filter-panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:17px;margin-bottom:16px}.filter-grid{display:grid;grid-template-columns:minmax(180px,1.6fr) repeat(3,minmax(112px,1fr));gap:12px}.field{display:flex;flex-direction:column;gap:6px;min-width:0}.field label{font-size:10px;font-weight:650;color:var(--muted)}.field input,.field select{width:100%;border:1px solid var(--line);border-radius:8px;padding:9px 11px;color:var(--ink);background:var(--surface-2);min-width:0;font-size:12px}.search-wrap{position:relative}.search-wrap .icon{position:absolute;left:11px;top:12px;width:17px;height:17px;color:var(--muted);pointer-events:none}.search-wrap input{padding-left:36px}.filter-second{display:flex;gap:12px;align-items:end;margin-top:12px}.page-field{flex:1}.filter-second .button{min-height:42px}.results-bar{display:flex;justify-content:space-between;gap:16px;align-items:center;font-size:11px;color:var(--muted);margin:16px 0}.results-bar strong{color:var(--ink)}.text-button{border:0;background:transparent;padding:5px 0;color:var(--brand);font-weight:650;min-height:34px;font-size:11px}.finding{background:var(--surface);border:1px solid var(--line);border-radius:12px;margin-bottom:13px;overflow:hidden;box-shadow:var(--shadow);break-inside:avoid}.finding-top{padding:19px 22px 0;display:flex;justify-content:space-between;gap:12px;align-items:center}.finding-labels{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.check-index{font-size:10px;font-weight:650;color:var(--muted);font-variant-numeric:tabular-nums;margin-right:3px}.badge{display:inline-flex;gap:5px;align-items:center;border-radius:5px;font-size:9px;font-weight:700;padding:3px 7px;line-height:1.5;white-space:nowrap}.status-dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0}.status-fail{background:var(--fail-bg);color:var(--fail)}.status-warning{background:var(--warning-bg);color:var(--warning)}.status-pass{background:var(--pass-bg);color:var(--pass)}.status-not_checked,.status-not_applicable{background:var(--unchecked-bg);color:var(--unchecked)}.category-tag{font-size:10px;color:var(--muted)}.severity{font-size:9px;font-weight:650;color:var(--muted);white-space:nowrap}.severity-critical,.severity-high{color:var(--fail)}.severity-medium{color:var(--warning)}.finding h3{margin:12px 22px 5px;font-size:16px}.finding-url{font-size:10px;margin:0 22px 9px}.finding-url a{color:var(--muted);text-decoration:none}.finding-url a:hover{text-decoration:underline}.observation{font-size:12px;line-height:1.7;margin:0 22px 17px;max-width:1000px;color:var(--muted)}details summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 22px;border-top:1px solid var(--line);background:var(--surface-2);font-size:10px;font-weight:650;color:var(--brand)}summary::-webkit-details-marker{display:none}summary .icon{width:15px;height:15px;transition:transform .15s ease}details[open]>summary .icon{transform:rotate(180deg)}.finding-body{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:20px;padding:23px 22px}.finding-body p{font-size:12px;line-height:1.8}.finding-body .eyebrow{font-size:9px}.action-panel{min-width:0}.fact-list{margin:20px 0 0;font-size:10px;display:grid;gap:8px}.fact-list div{display:grid;grid-template-columns:85px minmax(0,1fr);gap:9px}.fact-list dt{color:var(--muted)}.fact-list dd{margin:0;overflow-wrap:anywhere}.fact-list code{font-size:10px;color:var(--ink)}.evidence-panel{min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:14px;font:10px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;margin:0;max-height:400px;overflow:auto;color:var(--muted)}.finding-source{grid-column:1/-1;border-top:1px solid var(--line);padding-top:13px;display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;font-size:9px;color:var(--muted)}.empty-state{padding:35px 26px;text-align:center;border:1px dashed var(--line);border-radius:12px;background:var(--surface);color:var(--muted);font-size:12px}.empty-state .icon{color:var(--brand);width:25px;height:25px;margin-bottom:8px}.empty-state h3{font-size:16px;color:var(--ink);margin-bottom:5px}.empty-state p{margin:0}.table-shell{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--surface);box-shadow:var(--shadow)}table{width:100%;border-collapse:collapse;font-size:11px}caption{text-align:left;font-size:11px;color:var(--muted);padding:15px 18px}th{text-align:left;background:var(--surface-2);color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.065em;font-weight:700;padding:12px 17px;white-space:nowrap}td{vertical-align:top;padding:16px 17px;border-top:1px solid var(--line)}.page-url{display:block;max-width:340px;overflow-wrap:anywhere;font-size:11px;font-weight:600;text-decoration:none}.page-title{display:block;max-width:340px;color:var(--muted);font-size:10px;margin-top:4px;overflow-wrap:anywhere}.page-canonical{max-width:240px;font-size:9px;color:var(--muted);overflow-wrap:anywhere}.page-canonical a{color:var(--muted)}.count-pair{display:flex;flex-wrap:wrap;gap:5px;min-width:90px}.count-chip{font-size:9px;padding:2px 6px;border-radius:4px;background:var(--surface-2);white-space:nowrap}.count-fail{color:var(--fail);background:var(--fail-bg)}.count-warning{color:var(--warning);background:var(--warning-bg)}.http-pill{display:inline-block;padding:3px 7px;border:1px solid var(--line);border-radius:5px;font:10px/1.3 ui-monospace,monospace;white-space:nowrap}.http-ok{color:var(--pass);background:var(--pass-bg);border-color:transparent}.http-error{color:var(--fail);background:var(--fail-bg);border-color:transparent}.snapshot-status{font-size:9px;line-height:1.4;color:var(--muted);display:block;max-width:95px}.page-tools{max-width:350px;width:100%}.table-note{font-size:10px;color:var(--muted);margin:12px 0 0}.comparison-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-bottom:18px}.comparison-kpi{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:18px}.comparison-kpi span{display:block;color:var(--muted);font-size:10px}.comparison-kpi strong{display:block;font-size:27px;line-height:1.2;margin-bottom:6px;letter-spacing:-1px}.comparison-kpi.resolved strong{color:var(--pass)}.comparison-kpi.new strong{color:var(--warning)}.comparison-state{font-size:9px;padding:3px 7px;border-radius:5px;background:var(--unchecked-bg);color:var(--unchecked);white-space:nowrap}.comparison-state.resolved{background:var(--pass-bg);color:var(--pass)}.comparison-state.new{background:var(--warning-bg);color:var(--warning)}.comparison-description{font-size:11px;color:var(--muted);margin:15px 0}.coverage-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:0}.coverage-grid dt{font-size:10px;color:var(--muted);margin-bottom:4px}.coverage-grid dd{margin:0;font-size:19px;font-weight:650;letter-spacing:-.5px}.coverage-layout{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:18px;margin-bottom:18px}.scope-list{padding:0;margin:0;list-style:none;display:grid;gap:12px}.scope-list li{display:flex;gap:9px;font-size:11px;color:var(--muted)}.scope-list .icon{width:16px;height:16px;color:var(--brand);margin-top:1px}.scope-list strong{color:var(--ink);display:block;font-size:11px}.raw-coverage{background:var(--surface);border:1px solid var(--line);border-radius:11px;overflow:hidden}.raw-coverage summary{border-top:0}.raw-coverage pre{margin:18px;max-height:480px}.limitations{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:23px;margin-top:18px}.limitations h3{font-size:15px}.limitations ul{margin:14px 0 0;padding-left:17px;display:grid;gap:9px;color:var(--muted);font-size:11px}.measurements{display:grid;gap:16px}.measurement{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:24px}.measurement-head{display:flex;gap:18px;justify-content:space-between;align-items:start;margin-bottom:18px}.measurement-head h3{font-size:16px;margin:6px 0}.measurement-head p{font-size:10px;margin:0;color:var(--muted)}.measurement-kind{color:var(--violet);background:var(--surface-2);font-size:9px;padding:4px 8px;border-radius:5px;display:inline-block;font-weight:700;text-transform:uppercase;letter-spacing:.07em}.measurement-scope{color:var(--muted);font-size:10px;max-width:50%;text-align:right;overflow-wrap:anywhere}.measurement-scope a{font-size:10px}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:12px}.metric{border:1px solid var(--line);background:var(--surface-2);border-radius:9px;padding:15px}.metric-label{font-size:10px;color:var(--muted);display:block;margin-bottom:9px}.metric-value{font-size:25px;font-weight:700;letter-spacing:-.8px;line-height:1.2;overflow-wrap:anywhere}.metric-unit{font-size:11px;font-weight:500;color:var(--muted);margin-left:4px}.metric-rating{font-size:9px;margin-top:9px;color:var(--muted)}.rating-good{color:var(--pass)}.rating-needs_improvement{color:var(--warning)}.rating-poor{color:var(--fail)}.measurement-provenance{margin-top:17px;border:1px solid var(--line);border-radius:8px;overflow:hidden}.measurement-provenance summary{border:0;padding:10px 13px}.measurement-provenance pre{border:0;border-top:1px solid var(--line);border-radius:0}.import-issues{color:var(--warning);font-size:11px;background:var(--warning-bg);padding:15px 18px;border-radius:10px;margin:15px 0}.import-issues ul{padding-left:18px;margin:6px 0}.footer{margin-top:36px;border-top:1px solid var(--line);padding-top:21px;display:flex;gap:20px;justify-content:space-between;align-items:start;color:var(--muted);font-size:10px}.footer strong{display:block;color:var(--ink);font-size:11px;margin-bottom:4px}.footer p{margin:0}.footer-right{text-align:right}.demo-banner{display:flex;gap:10px;align-items:flex-start;padding:14px 18px;border:1px solid var(--line);border-radius:10px;background:var(--warning-bg);color:var(--warning);font-size:11px;margin-bottom:20px}.demo-banner .icon{width:17px;height:17px;flex-shrink:0}.no-script{padding:14px 18px;background:var(--warning-bg);color:var(--warning);font-size:11px;border-radius:8px;margin-bottom:20px}.js-only{display:none!important}.enhanced .js-only{display:block!important}.enhanced .top-actions.js-only,.enhanced .results-bar.js-only{display:flex!important}.enhanced .button.js-only{display:inline-flex!important}[hidden]{display:none!important}
@media(min-width:1650px){.workspace{padding-left:56px;padding-right:56px}.hero{padding:38px 40px}.kpi{padding:25px}.kpi-value{font-size:41px}}
@media(max-width:1180px){.sidebar{width:192px;padding:28px 13px 20px}.workspace{margin-left:192px;padding:25px}.brand{font-size:19px}.hero{padding:27px}.kpi{padding:17px}.filter-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.overview-grid{grid-template-columns:1fr 1.15fr}.category-tag{font-size:9px}.coverage-layout{grid-template-columns:1fr}}
@media(max-width:900px){.sidebar{position:relative;width:auto;inset:auto;display:block;padding:16px 22px;border-right:0;border-bottom:1px solid var(--line)}.brand{display:inline-flex;font-size:20px}.brand-mark{width:30px;height:32px;font-size:24px}.brand-subtitle,.nav-label,.sidebar-bottom{display:none}.sidebar nav{display:flex;overflow:auto;gap:4px;margin-top:15px;padding-bottom:2px}.nav-link{white-space:nowrap;padding:8px 10px;font-size:11px}.nav-link .icon{width:16px;height:16px}.nav-count{display:none}.workspace{margin-left:0;padding:24px}.topbar{margin-bottom:22px}.hero{grid-template-columns:minmax(0,1.4fr) minmax(200px,1fr);gap:20px}.hero-meta{padding-left:20px}.overview-grid{gap:14px}.panel{padding:20px}.status-legend{gap:13px 14px}.finding-body{gap:16px}}
@media(max-width:650px){.workspace{padding:20px 16px 32px}.topbar{gap:12px;align-items:start}.breadcrumb{font-size:10px;gap:7px}.top-actions{gap:8px}.theme-control>span{display:none}.theme-control select{font-size:10px;min-height:34px;max-width:83px}.top-actions .button{font-size:0;gap:0;padding:8px 10px;min-height:34px}.top-actions .button .icon{width:17px;height:17px}.hero{grid-template-columns:1fr;padding:24px;gap:23px;border-radius:13px}.hero-meta{border-left:0;border-top:1px solid var(--line);padding:19px 0 0;grid-template-columns:1fr 1fr;gap:14px}.hero-meta>div:first-child{grid-column:1/-1}.hero-description{font-size:12px}.target-link{font-size:12px}.kpis{grid-template-columns:1fr 1fr;gap:11px;margin:15px 0}.kpi{padding:16px}.kpi-top{font-size:10px;align-items:start}.kpi-icon{width:26px;height:26px}.kpi-value{font-size:31px;margin-top:10px}.kpi-note{font-size:9px}.overview-grid{grid-template-columns:1fr}.section{margin-top:28px}.section-heading{align-items:start;gap:10px}h2{font-size:21px}.section-heading p{font-size:11px}.section-meta{display:none}.filter-panel{padding:13px}.filter-grid{gap:10px}.filter-second{flex-wrap:wrap}.page-field{flex-basis:100%}.filter-second .button{min-height:36px;font-size:11px}.results-bar{font-size:10px;align-items:start}.finding-top{padding:16px 16px 0;gap:7px}.finding-labels{gap:6px}.category-tag{display:none}.finding h3{margin:11px 16px 5px;font-size:15px}.finding-url{margin:0 16px 9px}.observation{margin:0 16px 15px;font-size:11px}.finding-body{grid-template-columns:1fr;padding:18px 16px}.finding-source{grid-column:auto}details summary{padding:12px 16px}.page-tools{max-width:none}.page-heading{display:block}.page-heading .page-tools{margin-top:14px}th,td{padding:12px}.comparison-kpis{grid-template-columns:1fr 1fr;gap:10px}.coverage-grid{gap:17px}.coverage-grid dd{font-size:17px}.coverage-grid dt{font-size:9px}.measurement{padding:19px}.measurement-head{display:block}.measurement-scope{max-width:none;text-align:left;margin-top:12px}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.metric{padding:13px}.metric-value{font-size:23px}.footer{display:block}.footer-right{text-align:left;margin-top:13px}.scope-note{padding:13px;font-size:10px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{transition:none!important;animation:none!important}}
@page{size:A4;margin:15mm 13mm}
@media print{:root,:root[data-theme],body{color-scheme:light;--bg:#fff;--surface:#fff;--surface-2:#f5f7fa;--ink:#152239;--muted:#56657a;--line:#dce3eb;--brand:#16786a;--hero:#f2f7f4;--fail:#a32935;--warning:#815500;--pass:#126b51;--unchecked:#58677b;--fail-bg:#fff1f0;--warning-bg:#fff5df;--pass-bg:#e9f5ef;--unchecked-bg:#eef1f6;--shadow:none;background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}.sidebar,.topbar,.js-only,.enhanced .js-only,.enhanced .top-actions.js-only,.enhanced .results-bar.js-only,.enhanced .button.js-only,.no-script,.skip-link,#no-findings,#no-pages{display:none!important}.workspace{margin:0;max-width:none;padding:0}.hero{padding:22px;border-radius:10px;gap:20px;break-inside:avoid}.hero h1{font-size:32px}.hero-meta{font-size:10px}.section{margin-top:24px}h2{font-size:20px}.kpis{gap:10px;margin:15px 0}.kpi{padding:14px}.kpi-value{font-size:28px}.overview-grid{grid-template-columns:1fr 1.2fr;gap:12px}.panel{padding:16px}.section-heading,.panel-title,h2,h3{break-after:avoid}.panel,.kpi,.comparison-kpi,.scope-note,.measurement,.coverage-layout{break-inside:avoid}.finding{box-shadow:none;break-inside:auto;margin-bottom:14px}.finding[hidden]{display:block!important}.page-row[hidden]{display:table-row!important}.finding-top,.finding h3,.finding-url,.observation,summary{break-after:avoid}.finding-body{grid-template-columns:1fr}.finding-source{grid-column:auto}.finding pre,pre{max-height:none;overflow:visible;font-size:9px}.table-shell{overflow:visible;box-shadow:none}.table-shell table{table-layout:fixed;font-size:9px}.table-shell th,.table-shell td{padding:9px 7px;overflow-wrap:anywhere;white-space:normal}.table-shell thead{display:table-header-group}.table-shell tr{break-inside:avoid}.table-shell .badge{font-size:8px}.page-url,.page-title,.page-canonical{max-width:none;font-size:9px}.count-pair{min-width:0}.snapshot-status{font-size:8px}.section-heading p{font-size:10px}.footer{font-size:9px}.raw-coverage pre{max-height:none}a{color:var(--brand);text-decoration:none}.coverage-grid{grid-template-columns:repeat(3,1fr)}.metric-grid{grid-template-columns:repeat(3,1fr)}.measurement-head{display:flex}.measurement-scope{max-width:50%;text-align:right}.comparison-kpis{grid-template-columns:repeat(4,1fr)}.scope-note{font-size:10px}}
'''.strip()

_SCRIPT = r'''
(() => {
  'use strict';
  const root = document.documentElement;
  const cards = Array.from(document.querySelectorAll('.finding'));
  const records = cards.map(card => ({card, text: card.textContent.toLocaleLowerCase()}));
  const controls = ['finding-search', 'status-filter', 'severity-filter', 'category-filter', 'page-filter'].map(id => document.getElementById(id));
  const counter = document.getElementById('finding-count');
  const noResults = document.getElementById('no-findings');
  const expand = document.getElementById('expand-findings');
  const pageSearch = document.getElementById('page-search');
  const pageRows = Array.from(document.querySelectorAll('.page-row'));
  const pageRecords = pageRows.map(row => ({row, text: row.textContent.toLocaleLowerCase()}));
  const theme = document.getElementById('theme-choice');
  function applyFilters() {
    const [search, status, severity, category, page] = controls.map(control => control.value);
    const query = search.trim().toLocaleLowerCase();
    let visible = 0;
    for (const {card, text} of records) {
      const match = (!query || text.includes(query)) &&
        (status === 'all' || (status === 'issues' ? ['fail', 'warning'].includes(card.dataset.status) : card.dataset.status === status)) &&
        (severity === 'all' || card.dataset.severity === severity) &&
        (category === 'all' || card.dataset.category === category) && (page === 'all' || card.dataset.page === page);
      card.hidden = !match;
      if (match) visible += 1;
    }
    counter.textContent = `Showing ${visible.toLocaleString()} of ${cards.length.toLocaleString()} recorded checks`;
    noResults.hidden = visible !== 0;
    expand.disabled = visible === 0;
    expand.textContent = 'Expand visible evidence';
  }
  controls.forEach(control => control.addEventListener(control.tagName === 'INPUT' ? 'input' : 'change', applyFilters));
  document.getElementById('reset-filters').addEventListener('click', () => {
    controls[0].value = '';
    controls.slice(1).forEach(control => { control.value = 'all'; });
    applyFilters();
    controls[0].focus();
  });
  expand.addEventListener('click', () => {
    const details = cards.filter(card => !card.hidden).map(card => card.querySelector('details'));
    const shouldOpen = details.some(detail => !detail.open);
    details.forEach(detail => { detail.open = shouldOpen; });
    expand.textContent = shouldOpen ? 'Collapse visible evidence' : 'Expand visible evidence';
  });
  document.querySelectorAll('[data-page-jump]').forEach(button => button.addEventListener('click', () => {
    controls[0].value = '';
    controls.slice(1).forEach(control => { control.value = 'all'; });
    controls[4].value = button.dataset.pageJump;
    applyFilters();
    document.getElementById('findings').scrollIntoView();
    controls[4].focus({preventScroll: true});
  }));
  pageSearch.addEventListener('input', () => {
    const query = pageSearch.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const {row, text} of pageRecords) { row.hidden = Boolean(query && !text.includes(query)); if (!row.hidden) visible += 1; }
    document.getElementById('page-count').textContent = `${visible.toLocaleString()} of ${pageRows.length.toLocaleString()} observed pages`;
    document.getElementById('no-pages').hidden = visible !== 0;
  });
  let savedTheme = 'system';
  try { const stored = localStorage.getItem('ewebcity-audit-theme'); if (['system', 'light', 'dark'].includes(stored)) savedTheme = stored; } catch (_) {}
  theme.value = savedTheme;
  root.dataset.theme = savedTheme;
  theme.addEventListener('change', () => { root.dataset.theme = theme.value; try { localStorage.setItem('ewebcity-audit-theme', theme.value); } catch (_) {} });
  let printState = null;
  window.addEventListener('beforeprint', () => {
    if (printState) return;
    printState = {details: Array.from(document.querySelectorAll('details')).map(node => [node, node.open]), hidden: [...cards, ...pageRows].map(node => [node, node.hidden])};
    printState.details.forEach(([node]) => { node.open = true; });
    printState.hidden.forEach(([node]) => { node.hidden = false; });
  });
  window.addEventListener('afterprint', () => {
    if (!printState) return;
    printState.details.forEach(([node, open]) => { node.open = open; });
    printState.hidden.forEach(([node, hidden]) => { node.hidden = hidden; });
    printState = null;
  });
  document.getElementById('print-report').addEventListener('click', () => window.print());
  cards.forEach(card => { card.querySelector('details').open = false; });
  root.classList.add('enhanced');
  applyFilters();
})();
'''.strip()


def _implementation_basis(value) -> str:
    labels = {
        "user_selected": "Selected by the user",
        "wordpress_snapshot": "Based on the supplied WordPress snapshot",
        "unspecified": "Platform unspecified",
    }
    return labels.get(value, "Not supplied") if isinstance(value, str) else "Not supplied"


def _implementation_html(report: dict) -> str:
    context = report.get("implementation")
    if not isinstance(context, dict):
        return ""
    label = context.get("label") or context.get("platform") or "Platform not supplied"
    guidance = context.get("guidance")
    guidance = [item for item in guidance if isinstance(item, str)] if isinstance(guidance, list) else []
    references = context.get("references")
    references = [item for item in references if isinstance(item, dict)] if isinstance(references, list) else []
    reference_html = ""
    if references:
        rows = ''.join(f'<li><strong>{_html(item.get("label") or "Official reference")}</strong> · {_link(item.get("url"))}<br>Reference checked: {_html(item.get("checked_at"))}</li>' for item in references)
        reference_html = '<details class="measurement-provenance" open><summary>Implementation references' + _icon('chevron') + '</summary><ul>' + rows + '</ul></details>'
    items = ''.join('<li>' + _html(item) + '</li>' for item in guidance) or '<li>No platform-specific guidance was supplied.</li>'
    note = '<p class="table-note">' + _html(context['note']) + '</p>' if context.get('note') else ''
    return f'''<section class="section" id="implementation" aria-labelledby="implementation-title"><div class="section-heading"><div><span class="section-number">Apply within your stack</span><h2 id="implementation-title">Implementation guidance</h2><p>Use the recorded platform context when acting on the observed findings.</p></div></div><div class="limitations"><h3>{_html(label)}</h3><p class="table-note">Context basis: {_html(_implementation_basis(context.get('basis')))}</p><ul>{items}</ul>{note}{reference_html}</div></section>'''


def _wordpress_providers(snapshot: dict) -> list:
    names = {"yoast": "Yoast SEO", "rankmath": "Rank Math"}
    providers = snapshot.get("providers")
    rows, recorded = [], set()
    for provider in providers if isinstance(providers, list) else []:
        if not isinstance(provider, dict):
            continue
        provider_id = provider.get("id")
        name = names.get(provider_id, provider_id) if isinstance(provider_id, str) else "Provider not supplied"
        if isinstance(provider_id, str):
            recorded.add(provider_id)
        activity = "Active in snapshot" if provider.get("active") is True else "Reported inactive" if provider.get("active") is False else "Activity not recorded"
        rows.append((name, activity, provider.get("version")))
    for provider_id, name in names.items():
        if provider_id not in recorded:
            rows.append((name, "Not reported in snapshot", None))
    return rows


def _wordpress_visibility(site: dict) -> str:
    visibility = site.get("search_visibility")
    if visibility == "allow":
        return "Allow search engines (WordPress setting)"
    if visibility == "discourage":
        return "Discourage search engines (WordPress setting)"
    return "Not recorded"


def _wordpress_html(report: dict) -> str:
    snapshot = report.get("wordpress")
    if not isinstance(snapshot, dict):
        return ""
    site = snapshot.get("site") if isinstance(snapshot.get("site"), dict) else {}
    coverage = snapshot.get("coverage") if isinstance(snapshot.get("coverage"), dict) else {}
    pagination = snapshot.get("pagination") if isinstance(snapshot.get("pagination"), dict) else {}
    provenance = snapshot.get("provenance") if isinstance(snapshot.get("provenance"), dict) else {}
    posts = snapshot.get("posts")
    posts = [post for post in posts if isinstance(post, dict)] if isinstance(posts, list) else []
    reported_total = coverage.get("total_posts_reported", pagination.get("total_posts"))
    page = coverage.get("page", pagination.get("page"))
    total_pages = coverage.get("total_pages_reported", pagination.get("total_pages"))
    page_label = _number(page) + " of " + _number(total_pages)
    mode = snapshot.get("mode")
    mode_label = "Local snapshot import" if mode == "offline_snapshot" else "Authenticated snapshot import" if mode == "authenticated_snapshot" else "Import mode not recorded"
    providers = ''.join(f'<tr><th scope="row">{_html(name)}</th><td>{_html(activity)}</td><td>{_html(version)}</td></tr>' for name, activity, version in _wordpress_providers(snapshot))
    post_panels = []
    for post in posts:
        post_panels.append(f'''<article class="panel wordpress-post"><div class="measurement-head"><div><span class="measurement-kind">Saved plugin overrides</span><h3>Post {_html(post.get('id'))} · {_html(post.get('type'))}</h3><p>Post modified (GMT): {_html(post.get('modified_gmt'))}</p></div><div class="measurement-scope">{_link(post.get('url'))}</div></div><details class="measurement-provenance wordpress-overrides" open><summary>Stored override values{_icon('chevron')}</summary><pre tabindex="0">{_html({'metadata': post.get('metadata', {}), 'truncated_fields': post.get('truncated_fields', []), 'omitted_fields': post.get('omitted_fields', [])})}</pre></details></article>''')
    issues = snapshot.get("issues")
    issue_html = '<div class="import-issues"><strong>Snapshot import limitations</strong><ul>' + ''.join('<li>' + _html(issue) + '</li>' for issue in issues) + '</ul></div>' if isinstance(issues, list) and issues else ''
    record = {key: snapshot.get(key) for key in ("format", "schema_version", "bridge_version", "mode", "generated_at", "snapshot_auditor", "pagination", "coverage", "provenance")}
    note = '<p class="table-note">' + _html(snapshot['note']) + '</p>' if snapshot.get('note') else ''
    permalink = site.get("permalink_structure")
    permalink = "Empty string" if permalink == "" else permalink
    return f'''<section class="section" id="wordpress" aria-labelledby="wordpress-title"><div class="section-heading"><div><span class="section-number">CMS snapshot evidence</span><h2 id="wordpress-title">WordPress &amp; SEO plugins</h2><p>Saved settings and plugin overrides, imported independently of the source-HTML audit.</p></div></div><div class="coverage-layout"><div class="panel"><div class="panel-title"><h3>Bounded snapshot coverage</h3></div><dl class="coverage-grid"><div><dt>Posts in this import</dt><dd data-wordpress-records="{len(posts)}">{len(posts):,}</dd></div><div><dt>Plugin-reported posts</dt><dd>{_html(_number(reported_total))}</dd></div><div><dt>Snapshot page</dt><dd>{_html(page_label)}</dd></div></dl><p class="table-note">Coverage is limited to the imported records; this is not a frontend crawl.</p></div><div class="panel"><ul class="scope-list"><li>{_icon('scope')}<div><strong>Search visibility preference</strong>{_html(_wordpress_visibility(site))}</div></li><li>{_icon('clock')}<div><strong>{_html(mode_label)}</strong>Snapshot generated: {_html(_date(snapshot.get('generated_at')))}<br>Imported: {_html(_date(provenance.get('collected_at')))}<br>Snapshot auditor: {_html(_auditor(snapshot.get('snapshot_auditor')))}</div></li><li>{_icon('pages')}<div><strong>WordPress URLs &amp; permalinks</strong>Home: {_link(site.get('home_url'))}<br>Site: {_link(site.get('site_url'))}<br>Permalink structure: <code>{_html(permalink)}</code></div></li></ul></div></div><div class="table-shell"><table><caption>Provider versions and activity recorded by the snapshot</caption><thead><tr><th scope="col">Provider</th><th scope="col">Recorded state</th><th scope="col">Version</th></tr></thead><tbody>{providers}</tbody></table></div><p class="table-note">A provider that is not reported is not assumed to be installed or inactive. Saved overrides may be empty, contain template variables or be superseded by defaults, filters and caches.</p><div class="measurements">{''.join(post_panels) or '<div class="empty-state"><h3>No post overrides imported</h3><p>Review the snapshot pagination and import limitations.</p></div>'}</div>{issue_html}<details class="raw-coverage" open><summary>Snapshot provenance &amp; pagination{_icon('chevron')}</summary><pre tabindex="0">{_html(record)}</pre></details>{note}<p class="table-note">This snapshot does not verify resolved frontend metadata, indexability, indexing or search performance. Its records do not change the source-audit check counts.</p></section>'''


def _measurements_html(report: dict) -> str:
    measurements = report.get("measurements")
    if not isinstance(measurements, dict):
        return ""
    items = measurements.get("items", [])
    panels = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind") if item.get("kind") in ("lab", "field") else "not recorded"
        scope = {"url": "URL-specific", "origin": "Origin-wide"}.get(item.get("scope"), "Scope not recorded")
        metrics = []
        for metric in item.get("metrics", []):
            if not isinstance(metric, dict):
                continue
            value = metric.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                import math
                display = f"{value:,.3f}".rstrip("0").rstrip(".") if math.isfinite(value) else "Not recorded"
            else:
                display = "Not recorded"
            unit = metric.get("unit", "")
            unit = "" if unit == "score" else unit
            rating = metric.get("rating") if metric.get("rating") in ("good", "needs_improvement", "poor", "unrated") else "unrated"
            metrics.append(f'<div class="metric"><span class="metric-label">{_html(metric.get("label") or metric.get("id"))}</span><div class="metric-value">{_html(display)}<span class="metric-unit">{_html(unit)}</span></div><div class="metric-rating rating-{rating}">{_html(rating.replace("_", " ").capitalize())}</div></div>')
        period = item.get("collection_period")
        time_detail = ""
        if kind == "field":
            period_label = ("Collection window: " + str(period.get("start", "Not recorded")) + " to " + str(period.get("end", "Not recorded"))) if isinstance(period, dict) else "Collection window not recorded"
            if item.get("collected_at") is not None:
                time_detail = '<p class="measurement-timestamp">Export analysis timestamp: ' + _html(_date(item.get("collected_at"))) + '</p>'
        else:
            period_label = ("Run timestamp: " if kind == "lab" else "Export timestamp: ") + _date(item.get("collected_at"))
        item_note = '<p class="table-note measurement-note">' + _html(item["note"]) + '</p>' if item.get("note") else ""
        provenance = {key: item.get(key) for key in ("source", "source_version", "input_file", "input_sha256", "collected_at", "collection_period", "aggregation", "device", "scope") if item.get(key) is not None}
        panels.append(f'''<article class="measurement"><div class="measurement-head"><div><span class="measurement-kind">{_html(kind)} measurement</span><h3>{_html(item.get('source'))}</h3><p>{_html(period_label)} · {_html(item.get('aggregation', 'Aggregation not recorded'))}</p>{time_detail}</div><div class="measurement-scope"><strong>{_html(scope)}</strong><br>{_link(item.get('url'))}<br>Device: {_html(item.get('device', 'Not recorded'))}</div></div><div class="metric-grid">{''.join(metrics) or '<p>No supported metric values were supplied.</p>'}</div>{item_note}<details class="measurement-provenance" open><summary>Measurement provenance{_icon('chevron')}</summary><pre tabindex="0">{_html(provenance)}</pre></details></article>''')
    issues = measurements.get("issues", [])
    issue_html = '<div class="import-issues"><strong>Import limitations</strong><ul>' + ''.join('<li>' + _html(issue) + '</li>' for issue in issues) + '</ul></div>' if isinstance(issues, list) and issues else ''
    return f'''<section class="section" id="performance" aria-labelledby="performance-title"><div class="section-heading"><div><span class="section-number">Measured performance</span><h2 id="performance-title">Performance evidence</h2><p>Imported measurements, with their original scope and collection conditions.</p></div></div><div class="measurements">{''.join(panels) or '<div class="empty-state"><h3>No measurements available</h3><p>No supported measurement records could be imported.</p></div>'}</div>{issue_html}<p class="table-note">{_html(measurements.get('note') or 'Lab runs describe a controlled sample. Field data describes real-user observations over its collection window; origin data does not establish page-specific performance.')}</p></section>'''


def _comparison_html(report: dict) -> str:
    comparison = report.get("comparison")
    heading = '<div class="section-heading"><div><span class="section-number">Change tracking</span><h2 id="comparison-title">Before &amp; after</h2><p>Only an explicit comparable recheck can resolve an earlier issue.</p></div></div>'
    if not isinstance(comparison, dict):
        return '<section class="section" id="comparison" aria-labelledby="comparison-title">' + heading + '<div class="empty-state">' + _icon('compare') + '<h3>No baseline supplied</h3><p>Compare with an earlier audit to distinguish verified changes from checks that were not repeated.</p></div></section>'
    rows, cards = [], []
    for state, label in (("resolved", "Resolved"), ("persistent", "Still present"), ("new", "New findings"), ("not_rechecked", "Not rechecked")):
        items = comparison.get(state, [])
        items = items if isinstance(items, list) else []
        cards.append(f'<div class="comparison-kpi {state}" data-comparison="{state}" data-count="{len(items)}"><strong>{len(items):,}</strong><span>{label}</span></div>')
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(f'<tr><td><span class="comparison-state {state}">{label}</span></td><td><code>{_html(item.get("rule_id"))}</code></td><td>{_link(item.get("url"))}</td><td>{_html(item.get("reason") or "Observed in both reports" if state == "persistent" else item.get("reason") or "Observed in the current run")}</td></tr>')
    comparable = comparison.get("comparable") is True
    limitations = comparison.get("limitations", [])
    detail = '; '.join(str(item) for item in limitations) if isinstance(limitations, list) else str(limitations)
    return f'''<section class="section" id="comparison" aria-labelledby="comparison-title">{heading}<div class="comparison-kpis">{''.join(cards)}</div><p class="comparison-description"><strong>{'Comparable observations' if comparable else 'Reports are not comparable'}.</strong> Baseline: {_html(_date(comparison.get('baseline_collected_at')))}. {_html(detail)}</p><div class="table-shell"><table><caption>Recorded change in findings</caption><thead><tr><th scope="col">Outcome</th><th scope="col">Check</th><th scope="col">URL</th><th scope="col">Evidence of change</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="4">No issue changes were recorded.</td></tr>'}</tbody></table></div><p class="table-note">{_html(comparison.get('note') or 'A missing finding or uncrawled page is not proof that an issue was fixed.')}</p></section>'''


def render_html(report: dict) -> str:
    """A self-contained report: no remote assets and no report data in executable JS."""
    _validate_report(report)
    import base64
    findings, pages = report["findings"], report["pages"]
    counts = Counter(f["status"] for f in findings)
    coverage = report.get("coverage") if isinstance(report.get("coverage"), dict) else {}
    issues = _sorted_issues(findings)
    issue_urls = {finding["url"] for finding in issues}
    categories = {key: Counter() for key in CATEGORY_LABELS}
    page_counts = {}
    for finding in findings:
        categories[_category(finding)][finding["status"]] += 1
        page_counts.setdefault(finding["url"], Counter())[finding["status"]] += 1
    category_rows = []
    for category, label in CATEGORY_LABELS.items():
        group = categories[category]
        if not group:
            continue
        category_rows.append(f'<div class="category-row" data-category-summary="{category}" data-total="{sum(group.values())}" data-issues="{group["fail"] + group["warning"]}"><div class="category-caption"><strong>{label}</strong><span>{group["fail"] + group["warning"]:,} to review · {sum(group.values()):,} checks</span></div>{_bar(group, label)}</div>')
    legend = ''.join(f'<li data-status-summary="{status}" data-count="{counts[status]}"><span class="legend-dot legend-{status}" aria-hidden="true"></span><span class="legend-text">{STATUS_LABELS[status]}</span><strong>{counts[status]:,}</strong></li>' for status in STATUS_ORDER)
    observed_urls = sorted({finding["url"] for finding in findings})
    page_options = ''.join(f'<option value="{_html(url)}">{_html(url)}</option>' for url in observed_urls)
    status_options = ''.join(f'<option value="{status}">{STATUS_LABELS[status]} ({counts[status]:,})</option>' for status in STATUS_ORDER)
    category_options = ''.join(f'<option value="{category}">{label}</option>' for category, label in CATEGORY_LABELS.items() if categories[category])
    severity_options = ''.join(f'<option value="{severity}">{severity.capitalize()}</option>' for severity in (*SEVERITIES, 'unclassified'))
    sort_key = lambda f: ((0 if f["status"] in ISSUE_STATUSES else 1), {"fail": 0, "warning": 1, "not_checked": 2, "pass": 3, "not_applicable": 4}[f["status"]], SEVERITIES.index(f.get("severity")) if f.get("severity") in SEVERITIES else 5, f["rule_id"], f["url"])
    cards = ''.join(_card(finding, index) for index, finding in enumerate(sorted(findings, key=sort_key), 1))
    page_rows = []
    for page in pages:
        url = page.get("url")
        group = page_counts.get(url, Counter())
        status = page.get("http_status")
        if status is None:
            http = '<span class="snapshot-status">Not measured (snapshot)</span>'
        else:
            tone = "http-ok" if isinstance(status, int) and 200 <= status < 300 else "http-error"
            http = f'<span class="http-pill {tone}">{_html(status)}</span>'
        canonical = page.get("canonical")
        canonical = canonical if isinstance(canonical, list) else [canonical] if canonical else []
        canonical_html = '<br>'.join(_link(value) for value in canonical) or 'No declaration recorded'
        page_rows.append(f'''<tr class="page-row" data-page="{_html(url)}"><td><span class="page-url">{_link(url)}</span><span class="page-title">{_html(page.get('title') or 'No title recorded')}</span><button type="button" class="text-button js-only" data-page-jump="{_html(url)}">View page checks {_icon('arrow')}</button></td><td>{http}</td><td><div class="count-pair"><span class="count-chip count-fail">{group['fail']} failed</span><span class="count-chip count-warning">{group['warning']} review</span></div></td><td>{group['not_checked']}</td><td class="page-canonical">{canonical_html}</td></tr>''')
    offline = report['mode'].startswith('offline')
    collected = _date(report.get('collected_at'))
    auditor = _auditor(report.get('auditor'))
    collection_label = 'Saved HTML snapshot' if offline else 'Bounded sample complete' if coverage.get('complete') is True else 'Partial collection'
    collection_class = '' if offline or coverage.get('complete') is True else ' partial'
    discovery = coverage.get('discovered_urls')
    discovered_count = len(set(value for value in discovery if isinstance(value, str))) if isinstance(discovery, list) else None
    requests = coverage.get('requests')
    skipped = coverage.get('skipped')
    skipped_count = len({item.get('url') for item in skipped if isinstance(item, dict) and isinstance(item.get('url'), str)}) if isinstance(skipped, list) else None
    byte_count = coverage.get('bytes_received')
    byte_label = f'{byte_count / 1_000_000:.2f} MB' if isinstance(byte_count, (int, float)) and not isinstance(byte_count, bool) else 'Not recorded'
    coverage_values = [('Observed pages', len(pages)), ('Discovered URLs', discovered_count), ('HTTP requests', requests), ('Skipped URLs', skipped_count), ('Body data received', byte_label), ('Page responses', coverage.get('pages_fetched'))]
    coverage_stats = ''.join(f'<div><dt>{label}</dt><dd>{_html(value if isinstance(value, str) else _number(value))}</dd></div>' for label, value in coverage_values)
    stop_reasons = coverage.get('stop_reasons', [])
    stop_text = ', '.join(str(item).replace('_', ' ') for item in stop_reasons) if isinstance(stop_reasons, list) and stop_reasons else 'No collection stop reason recorded'
    scope_origin = coverage.get('scope_origin') or report['target']
    unchecked = report.get('checks_not_performed') if isinstance(report.get('checks_not_performed'), list) else []
    demonstration = ('<div class="demo-banner" role="note">' + _icon("info") + '<span><strong>Demonstration report</strong> · Sample HTML and synthetic imports; not a live website assessment.</span></div>') if report.get("demonstration") is True else ""
    if not demonstration and _has_synthetic_imports(report):
        demonstration = '<div class="demo-banner" role="note">' + _icon("info") + '<span><strong>Includes demonstration evidence</strong> · Some imported WordPress or performance data is synthetic. Review its provenance separately from the source-page findings.</span></div>'
    measurements = _measurements_html(report)
    performance_nav = f'<a class="nav-link" href="#performance">{_icon("pulse")}<span>Performance</span></a>' if measurements else ''
    wordpress = _wordpress_html(report)
    wordpress_nav = f'<a class="nav-link" href="#wordpress">{_icon("pages")}<span>WordPress</span></a>' if wordpress else ''
    implementation = _implementation_html(report)
    implementation_nav = f'<a class="nav-link" href="#implementation">{_icon("check")}<span>Implementation</span></a>' if implementation else ''
    style_hash = base64.b64encode(hashlib.sha256(_STYLE.encode('utf-8')).digest()).decode('ascii')
    script_hash = base64.b64encode(hashlib.sha256(_SCRIPT.encode('utf-8')).digest()).decode('ascii')
    policy = f"default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'sha256-{style_hash}'; script-src-attr 'none'; style-src-attr 'none'; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    return f'''<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="author" content="{_html(auditor)}"><meta http-equiv="Content-Security-Policy" content="{_html(policy)}"><title>eWebCity website audit — {_html(report['target'])}</title><style id="audit-style">{_STYLE}</style></head><body>
<a class="skip-link" href="#main">Skip to report</a><aside class="sidebar" aria-label="Report navigation"><a class="brand" href="#overview" aria-label="eWebCity audit overview"><span class="brand-mark" aria-hidden="true"><span>e</span></span>eWebCity</a><p class="brand-subtitle">WEBSITE INTELLIGENCE</p><div class="nav-label">This report</div><nav><a class="nav-link primary" href="#overview">{_icon('grid')}<span>Overview</span></a><a class="nav-link" href="#findings">{_icon('flag')}<span>Findings</span><span class="nav-count">{len(issues):,}</span></a><a class="nav-link" href="#pages">{_icon('pages')}<span>Pages</span><span class="nav-count">{len(pages):,}</span></a>{wordpress_nav}{performance_nav}<a class="nav-link" href="#comparison">{_icon('compare')}<span>Comparison</span></a>{implementation_nav}<a class="nav-link" href="#coverage">{_icon('scope')}<span>Evidence &amp; scope</span></a></nav><div class="sidebar-bottom"><strong>Evidence, then action.</strong>Source observations with clear limits.<br>Audit engine v{_html(report['tool_version'])}</div></aside>
<main class="workspace" id="main"><div class="topbar"><div class="breadcrumb"><span>eWebCity</span><span aria-hidden="true">/</span><strong>Website audit</strong></div><div class="top-actions js-only"><label class="theme-control"><span>Appearance</span><select id="theme-choice" aria-label="Report appearance"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label><button id="print-report" class="button" type="button" aria-label="Print or save the complete report as PDF">{_icon('print')}<span>Print / PDF</span></button></div></div>
<noscript><p class="no-script">JavaScript is disabled. All findings and evidence are available below. Interactive filtering and the appearance selector require JavaScript; your browser's print command remains available.</p></noscript>
{demonstration}<section id="overview" aria-labelledby="report-title"><header class="hero"><div><span class="eyebrow">{_icon('scope')}SEO · AEO · GEO</span><h1 id="report-title" class="hero-title">Website audit</h1><p class="hero-description">A clear view of the observed issues, supporting evidence and practical next steps for your website.</p><div class="target-link">{_link(report['target'])}{_icon('arrow')}</div></div><dl class="hero-meta"><div><dt>Auditor</dt><dd>{_html(auditor)}</dd></div><div><dt>Collection status</dt><dd><span class="collection-pill{collection_class}"><span class="status-dot" aria-hidden="true"></span>{collection_label}</span></dd></div><div><dt>Collected</dt><dd>{_html(collected)}</dd></div><div><dt>Audit mode</dt><dd>{'Saved source HTML' if offline else _html(report['mode'].replace('_', ' ').capitalize())}</dd></div></dl></header>
<div class="kpis"><div class="kpi" data-kpi="issues" data-count="{len(issues)}"><div class="kpi-top"><span>Findings to review</span><span class="kpi-icon">{_icon('flag')}</span></div><strong class="kpi-value">{len(issues):,}</strong><p class="kpi-note">{counts['fail']:,} failed · {counts['warning']:,} review<br>Across {len(issue_urls):,} observed URL(s)</p></div><div class="kpi" data-kpi="pages" data-count="{len(pages)}"><div class="kpi-top"><span>Pages observed</span><span class="kpi-icon">{_icon('pages')}</span></div><strong class="kpi-value">{len(pages):,}</strong><p class="kpi-note">Source HTML analysed<br>Bounded collection, not the whole site</p></div><div class="kpi" data-kpi="passed" data-count="{counts['pass']}"><div class="kpi-top"><span>Passing checks</span><span class="kpi-icon">{_icon('check')}</span></div><strong class="kpi-value">{counts['pass']:,}</strong><p class="kpi-note">Explicit observed passes<br>Across {len(findings):,} recorded checks</p></div><div class="kpi" data-kpi="unchecked" data-count="{counts['not_checked']}"><div class="kpi-top"><span>Checks unavailable</span><span class="kpi-icon">{_icon('clock')}</span></div><strong class="kpi-value">{counts['not_checked']:,}</strong><p class="kpi-note">Individual checks without evidence<br>Broader limitations are listed below</p></div></div>
<div class="overview-grid"><section class="panel" aria-labelledby="outcomes-title"><div class="panel-title"><div><h3 id="outcomes-title">Check outcomes</h3><p>What the collected evidence establishes</p></div><span class="panel-total"><b>{len(findings):,}</b> checks</span></div>{_bar(counts, 'All recorded checks')}<ul class="status-legend">{legend}</ul><p class="panel-footnote">Counts describe recorded checks. They are not a search ranking, site score or AI-citation probability.</p></section><section class="panel" aria-labelledby="categories-title"><div class="panel-title"><div><h3 id="categories-title">Review by category</h3><p>Use the evidence to choose the next action</p></div></div><div class="category-rows">{''.join(category_rows) or '<p class="table-note">No check categories were recorded.</p>'}</div></section></div>
<div class="scope-note">{_icon('info')}<p><strong>Know the scope.</strong> This source-HTML audit does not establish Google indexing, rankings, AI citations, rendered-page behaviour or real-user Core Web Vitals. Imported measurements, when supplied, retain their own scope below.</p></div></section>
<section class="section" id="findings" aria-labelledby="findings-title"><div class="section-heading"><div><span class="section-number">Investigate &amp; improve</span><h2 id="findings-title">Findings &amp; evidence</h2><p>Review the observation, confirm the intent and act on the recommendation.</p></div><span class="section-meta">{len(findings):,} checks · {len(observed_urls):,} URLs</span></div>
<div class="filter-panel js-only" role="search" aria-label="Filter audit checks"><div class="filter-grid"><div class="field"><label for="finding-search">Search findings</label><div class="search-wrap">{_icon('search')}<input id="finding-search" type="search" placeholder="URL, check or evidence…" autocomplete="off"></div></div><div class="field"><label for="status-filter">Status</label><select id="status-filter"><option value="issues" selected>Needs attention</option><option value="all">All checks</option>{status_options}</select></div><div class="field"><label for="severity-filter">Severity</label><select id="severity-filter"><option value="all">All severities</option>{severity_options}</select></div><div class="field"><label for="category-filter">Category</label><select id="category-filter"><option value="all">All categories</option>{category_options}</select></div></div><div class="filter-second"><div class="field page-field"><label for="page-filter">Page or resource URL</label><select id="page-filter"><option value="all">All URLs</option>{page_options}</select></div><button class="button" id="reset-filters" type="button">Reset filters</button></div></div><div class="results-bar js-only"><span id="finding-count" role="status" aria-live="polite">{len(findings):,} recorded checks</span><button class="text-button" id="expand-findings" type="button">Expand visible evidence</button></div><div id="finding-list">{cards}</div><div class="empty-state" id="no-findings" hidden><h3>No checks match these filters</h3><p>Choose a different status, URL or search term to inspect the recorded evidence.</p></div>{'<div class="empty-state"><h3>No checks were recorded</h3><p>Review the collection scope and any stop reasons below.</p></div>' if not findings else ''}</section>
<section class="section" id="pages" aria-labelledby="pages-title"><div class="section-heading page-heading"><div><span class="section-number">URL-level overview</span><h2 id="pages-title">Observed pages</h2><p id="page-count" role="status" aria-live="polite">{len(pages):,} source-HTML pages in this run</p></div><div class="field page-tools js-only"><label for="page-search">Search observed pages</label><div class="search-wrap">{_icon('search')}<input id="page-search" type="search" placeholder="Find a page or title…" autocomplete="off"></div></div></div><div class="table-shell"><table><caption>Responses, findings and declared canonicals for analysed HTML pages</caption><thead><tr><th scope="col">Page</th><th scope="col">HTTP</th><th scope="col">Findings</th><th scope="col">Not checked</th><th scope="col">Declared canonical</th></tr></thead><tbody>{''.join(page_rows) or '<tr><td colspan="5">No HTML pages were analysed.</td></tr>'}<tr id="no-pages" hidden><td colspan="5">No observed pages match this search.</td></tr></tbody></table></div><p class="table-note">This table covers analysed HTML pages. Resource and crawl-policy findings remain available in Findings &amp; evidence.</p></section>
{wordpress}{measurements}{_comparison_html(report)}{implementation}
<section class="section" id="coverage" aria-labelledby="coverage-title"><div class="section-heading"><div><span class="section-number">Transparency &amp; provenance</span><h2 id="coverage-title">Evidence &amp; collection scope</h2><p>Understand what was observed, what was skipped and what still needs verification.</p></div></div><div class="coverage-layout"><div class="panel"><div class="panel-title"><h3>Collection record</h3></div><dl class="coverage-grid">{coverage_stats}</dl></div><div class="panel"><ul class="scope-list"><li>{_icon('scope')}<div><strong>Selected scope</strong>{_link(scope_origin)}</div></li><li>{_icon('pages')}<div><strong>Coverage statement</strong>{_html(coverage.get('completeness_scope') or 'Coverage beyond the recorded sample is unverified.')}</div></li><li>{_icon('clock')}<div><strong>Stop reasons</strong>{_html(stop_text)}</div></li></ul></div></div><details class="raw-coverage" open><summary>Full collection evidence &amp; configured limits{_icon('chevron')}</summary><pre tabindex="0" aria-label="Full collection evidence">{_html(coverage)}</pre></details><div class="limitations"><h3>Checks not performed by this source audit</h3><ul>{''.join('<li>'+_html(item)+'</li>' for item in unchecked) or '<li>Consult the recorded scope and individual check statuses. Unspecified checks remain unverified.</li>'}</ul>{'<p class="table-note">Imported performance evidence is listed separately above; the source crawler did not perform those measurements.</p>' if measurements else ''}</div></section>
<footer class="footer"><div><strong>eWebCity · Evidence, then action.</strong><p>This report did not apply changes to the audited website.</p></div><div class="footer-right"><p>Engine v{_html(report['tool_version'])} · Schema {_html(report['schema_version'])}</p><p>Structured evidence: audit.json · Action list: fixes.md</p></div></footer></main><script id="audit-interactions">{_SCRIPT}</script></body></html>'''

def _md(value) -> str:
    return escape(_plain(value), quote=False).replace("\\", "\\\\").replace("`", "\\`").replace("[", "\\[").replace("]", "\\]").replace("*", "\\*").replace("_", "\\_").replace("\n", " ")


def render_fixes(report: dict) -> str:
    lines = ["# eWebCity audit: prioritised actions", "", f"Target: {_md(report['target'])}",
             f"Auditor: {_md(_auditor(report.get('auditor')))}",
             f"Collected: {_md(report.get('collected_at'))}", "",
             "These are recommendations derived from observed evidence. This audit did not edit the website.",
             "Confirm the page's intended visibility and apply changes within the existing authorisation. Recheck each changed rule and retain the baseline.", ""]
    if report.get("demonstration") is True or _has_synthetic_imports(report):
        lines += ["**Demonstration evidence is included.** Synthetic imports are not live-site measurements or proof of a WordPress connection; inspect the provenance of each input.", ""]
    context = report.get("implementation")
    if isinstance(context, dict):
        lines += ["## Implementation guidance", "",
                  f"Platform: {_md(context.get('label') or context.get('platform') or 'Platform not supplied')}",
                  f"Context basis: {_md(_implementation_basis(context.get('basis')))}", ""]
        if context.get("note"):
            lines += [_md(context["note"]), ""]
        guidance = context.get("guidance")
        if isinstance(guidance, list):
            lines.extend("- " + _md(item) for item in guidance if isinstance(item, str))
        references = context.get("references")
        if isinstance(references, list) and references:
            lines += ["", "Implementation references:", ""]
            lines.extend(f"- {_md(item.get('label') or 'Official reference')}: {_md(item.get('url'))} (checked {_md(item.get('checked_at'))})" for item in references if isinstance(item, dict))
        lines += [""]
    issues = _sorted_issues(report["findings"])
    if not issues:
        lines += ["No failing or warning checks were observed in the sample. This does not establish that unchecked areas passed.", ""]
    for index, finding in enumerate(issues, 1):
        lines += [f"## {index}. {_md(finding.get('title') or finding['rule_id'])}", "",
                  f"- Rule: {_md(finding['rule_id'])}", f"- URL: {_md(finding['url'])}",
                  f"- Status: {_md(finding['status'])}; severity: {_md(finding.get('severity'))}; confidence: {_md(finding.get('confidence'))}",
                  f"- Action: {_md(finding.get('recommendation'))}",
                  f"- Reference: {_md(finding.get('reference_url'))}", "", "Evidence:", ""]
        lines.extend("    " + line for line in _plain(finding.get("evidence", {})).splitlines())
        lines += ["", "Verification: re-run the same check on the affected URL, inspect the response/rendered output as applicable, and record an explicit result. A local fix is not evidence of deployment or indexing.", ""]
    snapshot = report.get("wordpress")
    if isinstance(snapshot, dict):
        site = snapshot.get("site") if isinstance(snapshot.get("site"), dict) else {}
        posts = snapshot.get("posts")
        post_count = sum(isinstance(post, dict) for post in posts) if isinstance(posts, list) else 0
        lines += ["## WordPress snapshot context", "",
                  f"- Posts in this import: {post_count}",
                  f"- Snapshot generated: {_md(snapshot.get('generated_at'))}",
                  f"- Snapshot auditor: {_md(_auditor(snapshot.get('snapshot_auditor')))}",
                  f"- Search visibility preference: {_md(_wordpress_visibility(site))}"]
        lines.extend(f"- {_md(name)}: {_md(activity)}; version {_md(version)}" for name, activity, version in _wordpress_providers(snapshot))
        lines += ["", "Saved settings and plugin overrides do not verify resolved frontend metadata, indexability or indexing. Coverage is limited to the imported records; these records do not change the source-audit check counts. Inspect report.html or audit.json for raw overrides and snapshot provenance.", ""]
        if snapshot.get("note"):
            lines += [_md(snapshot["note"]), ""]
        limitations = snapshot.get("issues")
        if isinstance(limitations, list) and limitations:
            lines += ["Snapshot import limitations:", ""]
            lines.extend("- " + _md(item) for item in limitations)
            lines += [""]
    lines += ["## Coverage and limitations", ""]
    lines.extend("    " + line for line in _plain(report.get("coverage", {})).splitlines())
    lines += ["", "## Checks not performed", ""]
    lines.extend("- " + _md(item) for item in report.get("checks_not_performed", []))
    if report.get("comparison"):
        lines += ["", "## Comparison", ""]
        lines.extend("    " + line for line in _plain(report["comparison"]).splitlines())
    return "\n".join(lines) + "\n"


def write_reports(report: dict, output_dir: Path, baseline_path: Path | None = None) -> None:
    """Write three new artifacts. Never overwrite an earlier run or a baseline."""
    _validate_report(report)
    output = Path(output_dir)
    for parent in (output, *output.parents):
        if parent.is_symlink():
            raise ValueError("Report output must not pass through a symbolic link")
    result = deepcopy(report)
    if baseline_path is not None:
        result["comparison"] = compare_reports(read_baseline(Path(baseline_path)), result)
    payloads = {
        "audit.json": json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "report.html": render_html(result),
        "fixes.md": render_fixes(result),
    }
    for name in payloads:
        target = output / name
        if target.exists() or target.is_symlink():
            raise ValueError(f"Output already exists: {target}. Choose a new run directory.")
    output.mkdir(parents=True, exist_ok=True)
    for name, contents in payloads.items():
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(contents)
