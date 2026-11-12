# Execution modes and useful delivery

This workflow depends on the host's tools, not the model brand. A DeepSeek model in a coding agent can have different capabilities from DeepSeek chat; ChatGPT, Codex and Claude web/desktop/code surfaces also differ. Check the actual session and preserve the user's authorisation.

## Select a real execution mode

| Available capabilities | Useful work | Evidence that remains separate |
| --- | --- | --- |
| Files, Python and public HTTP | Run the bounded audit and generate all three reports. | Browser rendering, search indexing and private analytics. |
| Files and Python, no public HTTP | Run `--html` on a supplied saved page; import supplied performance JSON. | Live HTTP status, robots decisions and link destination availability. |
| Readable files, no execution | Inspect the actual HTML/code/export and provide evidence with precise proposed fixes. | Report generation and any command that was not run. |
| Rendered browser | Inspect representative templates, source/DOM differences and visible behaviour. | Whole-site claims and performance numbers without measurements. |
| Authorised repository editing | Apply scoped fixes, run the project's checks and verify affected pages. | Production deployment, recrawling and indexing until separately observed. |

Locate `scripts/audit.py` relative to the installed skill. Run `--help` first when the installed version is uncertain. Use `python3` on macOS/Linux or the available Python 3.10+ executable on Windows. The repository's Node launcher accepts `EWEBCITY_PYTHON` when Python has a custom executable path. Do not install an arbitrary package merely to satisfy a command that the environment cannot run.

Supply command arguments separately rather than interpolating URLs/paths into a shell string. Keep complete resource folders when copying or exporting a skill. Never guess which local project is the user's site or create fake credentials to unlock provider data.

## From evidence to a fix

For each consequential issue, establish:

1. **What was observed:** the page, source/header/DOM/export, date and relevant excerpt.
2. **Why it matters here:** separate confirmed defects from intentional behaviour and editorial suggestions.
3. **Where to change it:** the actual template, route, metadata component, CMS setting or hosting rule. For URL-only work, identify the required access instead of claiming a live edit.
4. **What to change:** a small patch using the site's real URLs, visible content and business facts.
5. **How to verify:** a specific output/assertion plus the relevant project check and repeat audit.
6. **How to reverse:** the exact changed file/diff or the installer's reported backup.

For AEO/GEO, review useful answer passages and attributable facts. A clear paragraph can be an editorial improvement without establishing AI citation likelihood. If the user supplies real answer-engine observations, retain prompt, engine/model/surface, locale, date, repetition count and cited URL. Report sample observations; do not extrapolate a population-wide probability.

## Visual report contract

The generated `report.html` is self-contained and works offline. It should make these distinctions visible:

- Findings and affected pages are different counts. Status charts count rule evaluations, not ranking performance.
- Source crawl coverage is separate from provider metrics. A high proportion of passing checks does not imply the whole site is healthy.
- Lab runs, field percentiles and URL/origin evidence occupy separate performance cards.
- `not_checked`, skipped pages, budgets, decoding limitations and collection failures stay visible.
- Comparisons require compatible checks and explicit re-observation; missing data does not mean resolved.

Use search and the status/severity/category/page filters to focus the interactive view. Keep a way to reset filters and expand evidence. With JavaScript disabled, all findings must remain readable. Use print preview to inspect page breaks and save a PDF through the browser when that output is requested; producing HTML alone is not proof of a good PDF layout.

For delivery, lead with the scope and most consequential supported findings, link the actual generated files and show a report preview when useful. Label example/demo data clearly. Do not present a demonstration report as an audit of the user's live site. Do not expose private evidence in public repositories without the user's authorisation.

## Reusable task prompts

**Audit and report:** “Use ewebcity-seo-optimizer to audit this URL within 30 pages. Give me an interactive visual report, prioritised fixes and explicit coverage limits. Use my attached performance exports where applicable.”

**Fix and prove:** “Use ewebcity-seo-optimizer on this repository. Save the baseline, fix the supported canonical and indexing defects, run project checks, then compare the after report. Preserve intentional private-page rules.”

**Limited chat environment:** “Use the portable eWebCity SEO instructions with these saved HTML/export files. Analyse only the supplied evidence. If you can execute Python, generate the visual report; otherwise give findings and exact local commands.”

**Evidence-led content review:** “Review these pages for direct answers, entity consistency and supported factual claims. Propose edits using only verified business information. Keep editorial suggestions separate from measured search or AI visibility.”
