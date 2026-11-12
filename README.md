# eWebCity Agent Skills

Practical skills by [eWebCity](https://eWebCity.co.uk) for working on real repositories and investigating website search visibility. Use the same resource bundle in supported coding agents or export portable instructions for a chat environment. The existing npm package name, `ewebcity-claude-skills`, remains supported.

| Skill | Purpose |
| --- | --- |
| **ewebcity-fullstack-engineer** | Inspect, implement and validate focused full-stack changes with an honest delivery report. |
| **ewebcity-seo-optimizer** | Investigate technical SEO, AEO, GEO and performance using evidence, prepare authorised fixes and verify their effects. Includes a bounded source-HTML audit tool. |

## What changes in version 2.2

- **WordPress companion plugin:** eWebCity SEO Bridge reads active Yoast SEO/Rank Math overrides, search visibility and public-post coverage. Use a protected JSON export or an explicit authenticated HTTPS connection.
- **Auditor attribution:** every new audit defaults to **Auditor: Mahim** in JSON, HTML and the action list; `--auditor` can change it.
- **Framework guidance:** `--platform` supplies practical fix locations for WordPress, Laravel, PHP, JavaScript, static HTML or another stack. Public source checks remain independent of the framework.
- **Configuration with provenance:** WordPress provider data retains its snapshot date, source hash, pagination and raw-value limitations. It remains separate from observed frontend checks.

See [WordPress setup](docs/wordpress.md) and the [framework workflow reference](skills/ewebcity-seo-optimizer/references/framework-workflows.md).

### Included from version 2.1

- **Visual audit dashboard:** responsive report with status/category charts, searchable findings, impact/page filters, expandable evidence, page drill-down, baseline comparison, light/dark appearance and a complete-report print layout. Works offline without external assets; evidence remains readable without JavaScript.
- **More accurate interpretation:** crawler-scoped indexing directives, preserved repeated headers, HTML/HTTP canonical evidence, bounded hreflang checks and explicit character-decoding provenance. Ambiguous evidence remains visible.
- **Measured performance imports:** accept supplied Lighthouse, PageSpeed Insights and CrUX API JSON. Preserve lab/field, URL/origin, device, dates and source-file hashes; no provider API call is made.
- **Multiple agent targets:** choose the documented skill directory for Claude Code, Codex, Cursor, VS Code/Copilot or Antigravity. Export a prompt and complete resources for ChatGPT, DeepSeek or another host.
- **Practical agent workflow:** choose available tools, collect a baseline, prepare/apply authorised fixes, verify the result and deliver the report with clear remaining limits.

### Included from version 2.0

- **Executable audits:** a Python standard-library crawler and saved-HTML analyser produce structured evidence instead of relying only on a written checklist.
- **Useful outputs:** `audit.json`, a self-contained `report.html`, and a prioritised `fixes.md` action list.
- **Honest comparisons:** `--compare` distinguishes new, persistent, resolved and not-rechecked findings. An uncrawled page is never silently marked fixed.
- **Bounded collection:** exact-origin scope, robots handling, request/page/depth/time/byte limits and no automatic visits to private networks. DNS is checked and pinned to each connection; redirects remain within the selected origin.
- **Current guidance:** `llms.txt` is optional, search and model-training permissions are separate, retired rich-result features are not promised, and missing evidence remains visible.
- **Safer installation:** existing skills require an explicit `--force` update, which keeps a backup. Invalid options or skill names fail before installation.

## Requirements

- **Install skills:** Node.js 18 or newer.
- **Run the bundled audit:** Python 3.10 or newer. No third-party Python or npm dependencies are required.
- **Browser, analytics or provider checks:** use the relevant authorised tools or supplied exports through the skill workflow. Those integrations are not simulated by the crawler.

## Install from this repository

```bash
git clone https://github.com/mahimzq/ewebcity-claude-skills.git
cd ewebcity-claude-skills

# Inspect available skills and options.
node bin/install.js --list
node bin/install.js --help

# Install only the SEO skill into your personal Claude Code skill directory.
node bin/install.js ewebcity-seo-optimizer
```

To install into another project, run the installer from that project's directory:

```bash
node /absolute/path/to/ewebcity-claude-skills/bin/install.js \
  ewebcity-seo-optimizer --project
```

The default destination is `~/.claude/skills/`; `--project` uses the selected target's project directory. Installing with no skill names selects both skills. Confirm discovery in the agent session you intend to use; installing files does not establish runtime discovery.

### Claude, Codex, Cursor, VS Code, Antigravity and chat exports

```bash
node bin/install.js ewebcity-seo-optimizer --target codex --project
node bin/install.js ewebcity-seo-optimizer --target cursor --project
node bin/install.js ewebcity-seo-optimizer --target vscode --project
node bin/install.js ewebcity-seo-optimizer --target antigravity --project

# Export instructions and resources for a chat or another agent host.
node bin/install.js ewebcity-seo-optimizer --target portable
```

Run each project command from the project to receive the skill. `--target chatgpt` and `--target deepseek` are portable-export aliases, not native web-chat installation. Attach the exported instructions and relevant files, or expose the folder to a host with file access. The chat's available tools determine whether it can execute the audit, inspect saved evidence or only provide instructions.

See the [platform compatibility and setup guide](docs/platforms.md) for verified paths, shared-directory behaviour, discovery checks, capability limits and official sources. The installer tests file placement; actual application discovery must be verified in the chosen application.

### Updating an existing installation

```bash
# Preview the update without writing anything.
node bin/install.js ewebcity-seo-optimizer --force --dry-run

# Replace the selected skill and keep the previous version.
node bin/install.js ewebcity-seo-optimizer --force
```

Backups are outside active skills, under the selected target's `ewebcity-backups/<skill>-<timestamp>-<unique>/<skill>/` directory. For the default Claude target this is `.claude/ewebcity-backups/`. The installer reports the exact path. A replacement uses a fresh directory, so removed scripts do not linger in the active skill. Symlink destinations beneath the selected home/project directory are rejected. Each selected replacement is separate; a later filesystem failure can leave an earlier skill updated with its own backup intact.

For rollback, preserve any new local edits, move the current skill directory aside, and restore the reported backup directory to its former location. Do not run another forced update as a substitute for restoring the selected backup.

### npm distribution

This repository does not automatically publish an npm release. **Use the checked-out source unless version 2.2.0 has actually been published.** After that release exists, the equivalent commands are:

```bash
npx --yes --package ewebcity-claude-skills@2.2.0 ewebcity-skills --list
npx --yes --package ewebcity-claude-skills@2.2.0 ewebcity-skills ewebcity-seo-optimizer --target codex --project
npx --yes --package ewebcity-claude-skills@2.2.0 ewebcity-seo-audit --help
```

The packaged skill follows the `SKILL.md` directory format. Automatic compatibility/discovery in other agents or web apps must be verified in that environment; no unproduced `.skill` release downloads are advertised.

## Run an audit

### Live source-HTML crawl

```bash
node bin/audit.js \
  --url https://example.com \
  --output ./seo-audit/baseline \
  --max-pages 30
```

Or run the installed skill's standalone script:

```bash
python3 ~/.claude/skills/ewebcity-seo-optimizer/scripts/audit.py \
  --url https://example.com --output ./seo-audit/baseline
```

The Node launcher uses `python3` on macOS/Linux and tries `python` then `python3` on Windows. Set `EWEBCITY_PYTHON` to an executable path when your interpreter has a different location. The launcher never invokes a shell for audit arguments.

### Saved HTML with no network requests

```bash
node bin/audit.js \
  --html ./saved-page.html \
  --url https://example.com/service \
  --output ./seo-audit/snapshot
```

The URL supplies the document identity and relative-link base. Offline mode does not invent a response status, server headers, robots policy, link-destination status or indexing result.

### WordPress, Laravel, PHP, JavaScript and static websites

```bash
# Any public HTTP(S) website; platform selects where-to-fix guidance.
node bin/audit.js --url https://example.com --platform laravel \
  --auditor Mahim --output ./seo-audit/laravel

# Add a WordPress companion export from Yoast/Rank Math configuration.
node bin/audit.js --url https://example.com --wordpress-json ./wordpress-snapshot.json \
  --platform wordpress --output ./seo-audit/wordpress

# Build the optional WordPress upload plugin from source.
npm run build:wordpress -- --output ./dist/ewebcity-seo-bridge.zip
```

`--platform` accepts `generic`, `wordpress`, `laravel`, `php`, `javascript` and `static`. It selects guidance, not stack detection, PHP code execution or browser rendering. JavaScript-generated content needs separate rendered evidence. Reports default to **Auditor: Mahim**; author attribution does not certify an independent human review.

[WordPress setup](docs/wordpress.md) explains plugin installation, export/import and direct `--wordpress-api` connections using environment-held Application Passwords. The connector reads one same-origin HTTPS snapshot and never writes SEO settings. A WordPress plugin is not required for ordinary public-source auditing.

### Before and after

```bash
node bin/audit.js \
  --url https://example.com \
  --output ./seo-audit/after \
  --compare ./seo-audit/baseline/audit.json
```

Use matching tool/schema versions, collection mode and target origin. A previous issue resolves only when an explicit comparable check now passes or is explicitly not applicable. Duplicate checks also require their previous comparison scope to be re-observed. Missing or incompatible evidence is **not rechecked**. Reports never overwrite an earlier run's output files; choose a new directory.

### Import Lighthouse / PageSpeed / CrUX evidence

```bash
node bin/audit.js \
  --html ./saved-page.html --url https://example.com/service \
  --performance-json ./lighthouse.json \
  --performance-json ./crux.json \
  --output ./seo-audit/measured
```

Accept up to eight supplied JSON exports. The importer checks the schema and target origin, keeps separate measurement records, and reports missing or unusable values. The original file name and hash make each record traceable. Lab results never become field Core Web Vitals results; origin evidence never becomes a page measurement. Invalid inputs are rejected before crawling.

The tool does not automatically call PageSpeed or CrUX, authenticate a supplied file, run a browser or infer an overall field pass. Collection dates, device conditions and any PSI CLS scale ambiguity stay visible. See the [performance reference](skills/ewebcity-seo-optimizer/references/performance.md) for supported measurements and bounds.

### Use the visual report

Open `report.html` in a browser. Search findings or filter by status, impact, category and URL; select a page row to inspect that page's checks. Expand evidence for the source observation, recommended action and official reference. The dashboard counts observed rule evaluations and affected pages, not search ranking scores.

Use **Print / PDF** to print the complete report, including evidence hidden by interactive filters. Browser print output is a separate export; the CLI produces HTML, JSON and Markdown. No external fonts, scripts, trackers or chart libraries are loaded. See [examples](examples/README.md) for a clearly labelled demonstration and reproducible sample inputs.

### Collection limits

| Option | Default | Meaning |
| --- | ---: | --- |
| `--max-pages` | 30 | Maximum fetched page responses in the crawl. |
| `--max-depth` | 3 | Link-following depth from seeds. |
| `--max-requests` | 100 | All HTTP requests, including robots, sitemaps and redirects. |
| `--timeout` | 10 seconds | Per-request deadline, including name resolution and response reading. |
| `--max-seconds` | 120 seconds | Total collection deadline. |
| `--delay` | 0.25 seconds | Minimum spacing between requests; applicable crawl-delay can increase it. |
| `--max-bytes` | 2,000,000 | Maximum response or offline snapshot body size. |
| `--max-total-bytes` | 20,000,000 | Total received response-body budget. |

Use `--help` for accepted ranges. The crawler inspects at most three sitemap documents and 1,000 sitemap locations and follows at most five redirects per fetch. Query parameters remain distinct; all discovered variants share the same crawl budgets. HTML extraction also has explicit limits, recorded in coverage.

Only the selected origin is followed. A redirect to another host, port or scheme is recorded as outside scope; rerun against the intended canonical origin. Public HTTP(S) targets are the default. `--allow-localhost` explicitly enables local development on `localhost` or a literal loopback address; it does not enable private LANs or cloud metadata endpoints. Public crawl requests do not use cookies, credentials or environment proxies. The separately requested WordPress bridge connection uses a dedicated authenticated HTTPS request and its own recorded bounds; credentials never enter the crawler.

Observed robots 404/410 responses mean no published rules were found. Unavailable robots and access/rate-limit responses stop collection conservatively. Compressed responses are not decoded by this deliberately small reader; servers are asked for identity encoding, and unsupported responses are recorded as unavailable. A partial run remains visibly partial.

### Exit status

- `0`: an audit produced page observations; review its findings and coverage. This does **not** mean every check passed or the crawl was exhaustive.
- `1`: collection/output could not complete or no page could be analysed. Available evidence may still be written.
- `2`: invalid command-line arguments.

## What the bundled tool checks

It records source titles, descriptions, HTML/HTTP canonical declarations, crawler-scoped indexing directives, hreflang declarations, headings, language, viewport, links, image alternatives, mixed-content references and JSON-LD syntax. Live runs add HTTP/redirect observations, sampled sitemap consistency, effective robots decisions at the requested path and comparisons across observed pages. Cross-page checks only establish facts for the observed sample; uncrawled alternate/canonical/link destinations remain unverified. Every result includes evidence, a status, severity/confidence, a recommendation and an official reference where relevant.

Statuses are `pass`, `fail`, `warning`, `not_applicable` and `not_checked`. A warning often needs the site's intended behaviour before a fix is appropriate—for example, `noindex` on a private page may be deliberate. No overall Google, GEO or AI-citation score is fabricated.

The script creates diagnostic reports and recommendations. It **does not apply changes to the audited website**. The agent skill can inspect a supplied codebase, prepare/apply the requested fixes and run its checks within the user's existing authorisation.

## Additional checks through the skill workflow

The following need additional evidence/tooling and are explicitly unverified in a source-only run:

- JavaScript rendering, visual layout, interaction and accessibility.
- Fresh Lighthouse/lab measurements and real-user LCP, INP and CLS. Supplied exports can be imported separately.
- Google/Bing indexing, Search Console settings and provider performance reports.
- Analytics, conversion attribution, keyword demand and competitor research.
- Actual AI mentions/citations or repeated monitoring.
- Structured-data truth and feature eligibility, content quality and business facts.
- Unlinked pages, external destinations and exhaustive site coverage.

The references explain how to collect and interpret these when authorised tools or exports are available. Creating this skill does not schedule recurring work or connect private accounts.

## Examples for an agent

- “Audit this site and give me evidence, priorities and the checks you could not perform.”
- “Inspect this Next.js repository, fix the incorrect canonicals and verify the resulting pages.”
- “Compare this saved audit with a new run; keep uncrawled pages marked as not rechecked.”
- “Use my Search Console export to prioritise the observed technical and content issues.”

## Development

```bash
npm run check
npm test
npm pack --dry-run
```

Tests use temporary project directories, offline documents, mocked DNS and explicit loopback HTTP servers. They do not modify a personal skill installation, contact production sites or require provider credentials. Keep the Python helper files together when copying a skill. Generated Python caches are excluded from installation and packaging. The optional WordPress plugin has a separate PHP lint/contract runner under `tests/wordpress/`; a real WordPress activation test remains a staging check.

The normal suite includes report interaction logic with a small DOM test double. It checks filtering, disclosure state, page drill-down, appearance fallback and complete-report print events; these are not browser layout tests.

An optional real-browser gate is available for an environment with Playwright and Chromium installed:

```bash
npm run test:report -- /absolute/path/to/report.html
```

The gate checks desktop/mobile layout, browser interactions, no-JavaScript fallback, CSP/runtime errors and PDF generation. Set `EWEBCITY_PLAYWRIGHT_MODULE` to a local Playwright module path and `EWEBCITY_CHROMIUM` to an existing Chromium executable when needed. `EWEBCITY_REPORT_ARTIFACTS` selects its screenshot/result directory. Browser dependencies are development-only and are not required by the skill, installer or report.

## License

MIT © [eWebCity](https://eWebCity.co.uk).
