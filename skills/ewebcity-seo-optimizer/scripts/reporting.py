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


def _card(finding: dict) -> str:
    title = finding.get("title") or finding["rule_id"].replace("_", " ").replace("-", " ")
    source = finding.get("reference_url") or finding.get("source_url")
    return f'''<article class="finding" id="{_finding_id(finding)}">
      <div class="finding-meta"><span class="badge {finding['status']}">{_html(finding['status'])}</span>
        <span>{_html(finding.get('severity', 'unclassified'))} severity</span>
        <span>{_html(finding.get('confidence'))} confidence</span></div>
      <h3>{_html(title)}</h3><p class="url">{_link(finding['url'])}</p>
      <p class="rule">Rule: {_html(finding['rule_id'])}</p>
      <h4>Observed evidence</h4><pre>{_html(finding.get('evidence', {}))}</pre>
      <h4>Recommended action</h4><p>{_html(finding.get('recommendation'))}</p>
      <p class="source">Reference: {_link(source)}<br>Rule reference checked: {_html(finding.get('reference_checked_at'))}</p>
    </article>'''


def render_html(report: dict) -> str:
    _validate_report(report)
    findings = report["findings"]
    counts = Counter(f["status"] for f in findings)
    coverage = report.get("coverage", {})
    issues = _sorted_issues(findings)
    checks = [f for f in findings if f["status"] not in ISSUE_STATUSES]
    comparison = report.get("comparison")
    comparison_html = ""
    if comparison:
        rows = []
        for state in ("resolved", "persistent", "new", "not_rechecked"):
            for item in comparison.get(state, []):
                rows.append(f"<tr><td>{_html(state.replace('_', ' '))}</td><td>{_html(item.get('rule_id'))}</td><td>{_link(item.get('url'))}</td><td>{_html(item.get('reason', ''))}</td></tr>")
        comparison_html = f'''<section id="comparison"><h2>Before and after</h2>
          <p>Comparable: {_html(comparison.get('comparable'))}. Baseline: {_html(comparison.get('baseline_collected_at'))}.</p>
          <p>{_html(comparison.get('note'))}</p>
          <pre>{_html(comparison.get('counts', {}))}</pre>
          <p>{_html('; '.join(comparison.get('limitations', [])))}</p>
          <div class="table-scroll"><table><thead><tr><th>State</th><th>Rule</th><th>URL</th><th>Reason</th></tr></thead>
          <tbody>{''.join(rows) or '<tr><td colspan="4">No comparable issue changes recorded.</td></tr>'}</tbody></table></div></section>'''
    page_rows = []
    for page in report["pages"]:
        status = "Not measured (snapshot)" if page.get("http_status") is None else page["http_status"]
        page_rows.append(f"<tr><td>{_link(page.get('url'))}</td><td>{_html(status)}</td><td>{_html(page.get('title', ''))}</td><td>{_html(page.get('canonical', ''))}</td></tr>")
    unchecked = report.get("checks_not_performed", [])
    return f'''<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>eWebCity SEO audit — {_html(report['target'])}</title>
<style>
:root{{color-scheme:light;--ink:#17283f;--muted:#526277;--teal:#007e75;--line:#dce4ec;--paper:#f4f7fa}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
header{{background:#102e44;color:white;padding:44px max(24px,calc((100vw - 1120px)/2)) 40px;border-top:7px solid #16b8a6}}
.brand{{font-size:13px;letter-spacing:.15em;text-transform:uppercase;color:#94e5da;font-weight:700}}h1{{font-size:clamp(27px,4vw,42px);line-height:1.18;margin:12px 0}}
header p{{margin:7px 0;color:#e2ebf2}}header a{{color:white}}main{{max-width:1168px;margin:auto;padding:28px 24px 64px}}section{{margin:28px 0}}
h2{{font-size:23px;margin:0 0 12px}}h3{{margin:12px 0 5px;font-size:19px}}h4{{margin:18px 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.04em}}
a{{color:#006c83;text-underline-offset:3px;overflow-wrap:anywhere}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.stat,.panel,.finding{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px}}.stat b{{display:block;font-size:32px;line-height:1.2}}.stat span{{color:var(--muted);font-size:13px}}
.note{{border-left:4px solid var(--teal);padding:15px 18px;background:#e6f4f1;margin:22px 0}}.note p{{margin:0}}
.finding{{margin:16px 0;break-inside:avoid}}.finding-meta{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;color:var(--muted);font-size:12px}}
.badge{{font-weight:700;padding:3px 9px;border-radius:5px;text-transform:uppercase;font-size:11px}}.fail{{background:#ffe5e5;color:#9c2020}}.warning{{background:#fff0ce;color:#7c5000}}.pass{{background:#dff2e9;color:#195b3c}}.not_checked,.not_applicable{{background:#edf0f5;color:#4a5769}}
.url,.rule,.source{{font-size:13px;color:var(--muted);margin:5px 0}}.source{{margin-top:18px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f9;border:1px solid var(--line);border-radius:7px;padding:14px;font:12px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:460px;overflow:auto}}
.table-scroll{{overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;vertical-align:top;padding:12px 14px;border-bottom:1px solid var(--line);overflow-wrap:anywhere;max-width:420px}}th{{background:#eaf0f5}}tr:last-child td{{border-bottom:0}}
details summary{{cursor:pointer;font-weight:650;padding:15px;background:#eaf0f5;border-radius:8px}}li{{margin:7px 0}}footer{{border-top:1px solid var(--line);margin-top:34px;padding-top:20px;color:var(--muted);font-size:12px}}
@media(max-width:650px){{.stats{{grid-template-columns:repeat(2,1fr)}}header{{padding:28px 22px}}main{{padding:22px 16px}}.finding{{padding:18px}}}}
@media print{{body{{background:white}}header{{padding:24px;color:#102e44;background:white}}header p,header a{{color:#102e44}}main{{padding:16px 0}}pre{{max-height:none;overflow:visible}}.table-scroll{{overflow:visible}}details{{display:block}}a{{color:#102e44}}}}
</style></head><body>
<header><div class="brand">eWebCity · Website evidence</div><h1>SEO, AEO &amp; GEO audit</h1><p>{_link(report['target'])}</p>
<p>{_html(report.get('collected_at'))} · {_html(report['mode'].replace('_', ' '))} · v{_html(report['tool_version'])}</p></header>
<main><div class="stats">
<div class="stat"><b>{len(report['pages'])}</b><span>Pages observed</span></div>
<div class="stat"><b>{len(issues)}</b><span>Findings to review</span></div>
<div class="stat"><b>{counts['pass']}</b><span>Explicit passing checks</span></div>
<div class="stat"><b>{counts['not_checked']}</b><span>Unavailable individual checks</span></div></div>
<div class="note"><p>This is a source-HTML diagnostic with bounded coverage. It does not establish Google indexing, ranking, AI citations, rendered content or real-user Core Web Vitals. Review intent before changing crawling or indexing policies.</p></div>
<section id="coverage"><h2>Scope and coverage</h2><details><summary>Collection limits, skipped URLs and stop reasons</summary><pre>{_html(coverage)}</pre></details></section>
<section id="priorities"><h2>Findings to review</h2>{''.join(_card(f) for f in issues) or '<div class="panel">No failing or warning checks were observed in this sample. Unchecked areas remain unverified.</div>'}</section>
{comparison_html}
<section id="pages"><h2>Observed pages</h2><div class="table-scroll"><table><thead><tr><th>URL</th><th>HTTP status</th><th>Title</th><th>Declared canonical</th></tr></thead><tbody>{''.join(page_rows) or '<tr><td colspan="4">No pages were analysed.</td></tr>'}</tbody></table></div></section>
<section><h2>Other recorded checks</h2><details><summary>{len(checks)} passing, not-applicable or unavailable checks</summary>{''.join(_card(f) for f in checks)}</details></section>
<section><h2>Checks not performed</h2><div class="panel"><ul>{''.join('<li>'+_html(item)+'</li>' for item in unchecked) or '<li>Consult scope and per-finding status; unspecified checks are unverified.</li>'}</ul></div></section>
<footer>Generated by eWebCity SEO Optimizer. Read audit.json for structured evidence and fixes.md for the prioritised action list. No changes were applied to the audited website by this report generator.</footer>
</main></body></html>'''


def _md(value) -> str:
    return escape(_plain(value), quote=False).replace("\\", "\\\\").replace("`", "\\`").replace("[", "\\[").replace("]", "\\]").replace("*", "\\*").replace("_", "\\_").replace("\n", " ")


def render_fixes(report: dict) -> str:
    lines = ["# eWebCity audit: prioritised actions", "", f"Target: {_md(report['target'])}",
             f"Collected: {_md(report.get('collected_at'))}", "",
             "These are recommendations derived from observed evidence. This audit did not edit the website.",
             "Confirm the page's intended visibility and apply changes within the existing authorisation. Recheck each changed rule and retain the baseline.", ""]
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
