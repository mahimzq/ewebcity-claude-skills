# eWebCity Claude Skills

Practical skills by [eWebCity](https://eWebCity.co.uk) for working on real repositories and investigating website search visibility.

| Skill | Purpose |
| --- | --- |
| **ewebcity-fullstack-engineer** | Inspect, implement and validate focused full-stack changes with an honest delivery report. |
| **ewebcity-seo-optimizer** | Investigate technical SEO, AEO, GEO and performance using evidence, prepare authorised fixes and verify their effects. Includes a bounded source-HTML audit tool. |

## What changes in version 2.0

- **Executable audits:** a Python standard-library crawler and saved-HTML analyser produce structured evidence instead of relying only on a written checklist.
- **Useful outputs:** `audit.json`, a self-contained `report.html`, and a prioritised `fixes.md` action list.
- **Honest comparisons:** `--compare` distinguishes new, persistent, resolved and not-rechecked findings. An uncrawled page is never silently marked fixed.
- **Bounded collection:** exact-origin scope, robots handling, request/page/depth/time/byte limits and no automatic visits to private networks. DNS is checked and pinned to each connection; redirects remain within the selected origin.
- **Current guidance:** `llms.txt` is optional, search and model-training permissions are separate, retired rich-result features are not promised, and missing evidence remains visible.
- **Safer installation:** existing skills require an explicit `--force` update, which keeps a backup. Invalid options or skill names fail before installation.

The full-stack skill's contents are unchanged by the SEO upgrade.

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

The default destination is `~/.claude/skills/`; `--project` uses `./.claude/skills/`. Installing with no skill names selects both skills. Confirm discovery in the agent session you intend to use; installing files does not establish runtime discovery.

### Updating an existing installation

```bash
# Preview the update without writing anything.
node bin/install.js ewebcity-seo-optimizer --force --dry-run

# Replace the selected skill and keep the previous version.
node bin/install.js ewebcity-seo-optimizer --force
```

Backups are outside active skills, under `.claude/ewebcity-backups/<skill>-<timestamp>-<unique>/<skill>/`. The installer reports the exact path. A replacement uses a fresh directory, so removed scripts do not linger in the active skill. Symlink destinations beneath the selected home/project directory are rejected. Each selected replacement is separate; a later filesystem failure can leave an earlier skill updated with its own backup intact.

For rollback, preserve any new local edits, move the current skill directory aside, and restore the reported backup directory to its former location. Do not run another forced update as a substitute for restoring the selected backup.

### npm distribution

This repository does not automatically publish an npm release. **Use the checked-out source unless version 2.0.0 has actually been published.** After that release exists, the equivalent commands are:

```bash
npx --yes --package ewebcity-claude-skills@2.0.0 ewebcity-claude-skills --list
npx --yes --package ewebcity-claude-skills@2.0.0 ewebcity-claude-skills ewebcity-seo-optimizer
npx --yes --package ewebcity-claude-skills@2.0.0 ewebcity-seo-audit --help
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

### Before and after

```bash
node bin/audit.js \
  --url https://example.com \
  --output ./seo-audit/after \
  --compare ./seo-audit/baseline/audit.json
```

Use matching tool/schema versions, collection mode and target origin. A previous issue resolves only when an explicit comparable check now passes or is explicitly not applicable. Duplicate checks also require their previous comparison scope to be re-observed. Missing or incompatible evidence is **not rechecked**. Reports never overwrite an earlier run's output files; choose a new directory.

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

Only the selected origin is followed. A redirect to another host, port or scheme is recorded as outside scope; rerun against the intended canonical origin. Public HTTP(S) targets are the default. `--allow-localhost` explicitly enables local development on `localhost` or a literal loopback address; it does not enable private LANs or cloud metadata endpoints. Requests do not use cookies, credentials or environment proxies.

Observed robots 404/410 responses mean no published rules were found. Unavailable robots and access/rate-limit responses stop collection conservatively. Compressed responses are not decoded by this deliberately small reader; servers are asked for identity encoding, and unsupported responses are recorded as unavailable. A partial run remains visibly partial.

### Exit status

- `0`: an audit produced page observations; review its findings and coverage. This does **not** mean every check passed or the crawl was exhaustive.
- `1`: collection/output could not complete or no page could be analysed. Available evidence may still be written.
- `2`: invalid command-line arguments.

## What the bundled tool checks

It records source titles, descriptions, canonical declarations, metadata/indexing directives, headings, language, viewport, links, image alternatives, mixed-content references and JSON-LD syntax. Live runs add HTTP/redirect observations, sampled sitemap consistency, effective robots decisions at the requested path, and comparisons across observed pages. Every result includes evidence, a status, severity/confidence, a recommendation and an official reference where relevant.

Statuses are `pass`, `fail`, `warning`, `not_applicable` and `not_checked`. A warning often needs the site's intended behaviour before a fix is appropriate—for example, `noindex` on a private page may be deliberate. No overall Google, GEO or AI-citation score is fabricated.

The script creates diagnostic reports and recommendations. It **does not apply changes to the audited website**. The agent skill can inspect a supplied codebase, prepare/apply the requested fixes and run its checks within the user's existing authorisation.

## Additional checks through the skill workflow

The following need additional evidence/tooling and are explicitly unverified in a source-only run:

- JavaScript rendering, visual layout, interaction and accessibility.
- Lighthouse/lab measurements and real-user LCP, INP and CLS.
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

Tests use temporary project directories, offline documents, mocked DNS and explicit loopback HTTP servers. They do not modify a personal skill installation, contact production sites or require provider credentials. Keep the Python helper files together when copying a skill. Generated Python caches are excluded from installation and packaging.

## License

MIT © [eWebCity](https://eWebCity.co.uk).
