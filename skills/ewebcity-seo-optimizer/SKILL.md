---
name: ewebcity-seo-optimizer
description: A complete audit-and-auto-fix workflow for website SEO, AEO (answer engine optimization), GEO (generative/AI engine optimization), and page-load performance. Use this skill whenever the user asks to improve SEO, rank higher on Google, optimize a website, check or fix page speed, audit a site, add robots.txt or sitemap.xml, add structured data or meta tags, or make their site faster — even if they only say "check my website", "why is my site slow", "my site isn't ranking", or give a URL or repo and ask to improve it. Trigger for any website health, ranking, discoverability, or load-time request.
---

# Website SEO + Performance Optimizer

A workflow that audits an entire website for SEO, AEO, GEO, and performance issues, then automatically fixes everything fixable and generates every missing standard file (robots.txt, sitemap.xml, structured data, meta tags, manifest, and more).

Honest framing to keep throughout: this skill implements every on-page, technical, and performance best practice that is within the site's control. Rankings also depend on content quality, backlinks, competition, and Google's algorithms — never promise a specific ranking position. Promise a technically flawless, fast, fully crawlable, AI-and-answer-engine-ready site, and deliver exactly that.

## Reference Files

Read after determining scope — each is the authoritative checklist for its area:

- `references/technical-seo.md` — full crawl/audit checklist: meta tags, headings, canonicals, indexability, structured data, images, links, internationalization.
- `references/aeo-geo.md` — answer engine (featured snippets, voice) and generative engine (ChatGPT, Perplexity, Google AI Overviews) optimization, including llms.txt.
- `references/performance.md` — Core Web Vitals and page-load fixes, by framework.
- `references/required-files.md` — templates and generation rules for robots.txt, sitemap.xml, manifest, favicons, security.txt, llms.txt, and verification files.

## Step 1 — Determine Access Mode

Two modes; confirm which applies before auditing:

1. **Live URL only** — the user gave a website address. Audit by fetching pages, robots.txt, sitemap.xml, and key resources. Fixes are delivered as ready-to-apply files and exact code snippets with instructions on where each goes.
2. **Repository / file access** — the user gave the codebase (upload, repo, or connected environment). Audit both the code and, if a live URL exists, the deployed site. Apply fixes directly in the code and generate missing files into the correct locations. This is the full auto-fix mode.

In repo mode, follow the safe-engineering discipline: inspect before editing, keep the diff minimal, never break working functionality, and validate with the project's own build after changes. If the `ewebcity-fullstack-engineer` skill is installed, apply its workflow for all code edits.

## Step 2 — Full Site Audit

Crawl the site systematically, not just the homepage. In live mode: fetch the homepage, parse internal links, and audit every discoverable page type (home, key landing pages, blog/product templates, contact). In repo mode: enumerate routes/pages from the framework (Next.js pages/app dir, React Router config, Laravel routes, Django urls, static HTML files).

For every page, check against all four reference checklists and record findings in three buckets:

- **Critical** — blocks indexing or badly hurts ranking/UX: noindex mistakes, missing/broken robots.txt or sitemap, missing titles, broken canonical, render-blocking failures, failing Core Web Vitals, mixed content, missing HTTPS redirect.
- **Important** — measurable ranking/performance impact: missing meta descriptions, missing structured data, unoptimized images, missing Open Graph/Twitter cards, no lazy loading, missing alt text, duplicate titles, missing llms.txt/AEO markup.
- **Improvement** — polish: heading hierarchy refinements, internal linking opportunities, content-structure suggestions for snippets.

Where tooling is available in the environment, run real measurements rather than eyeballing: Lighthouse (if installable), or at minimum measure response sizes, count render-blocking resources, and inspect the HTML head of each page type.

## Step 3 — Auto-Fix (repo mode) or Fix Pack (URL mode)

Fix everything in priority order — Critical first. Do not stop at a report; the user asked for fixes, not findings.

**Always generate missing standard files** using `references/required-files.md`:
robots.txt, sitemap.xml (auto-built from the discovered routes), site.webmanifest, favicon set references, llms.txt, and — where relevant — security.txt and a Google Search Console verification placeholder with instructions.

**Code fixes** (repo mode) — apply directly:
- Per-page unique `<title>` and meta description (framework-native: Next.js metadata API, react-helmet, Laravel Blade sections, Django templates).
- Canonical tags, Open Graph + Twitter Card tags, viewport and charset.
- JSON-LD structured data appropriate to page type (Organization, WebSite + SearchAction, Article, Product, FAQ, BreadcrumbList).
- Semantic heading hierarchy, image alt attributes, descriptive link text.
- Performance fixes per `references/performance.md`: image optimization/lazy loading, font loading strategy, code splitting, caching headers, compression config.

**URL-only mode** — produce a fix pack: each generated file ready to upload, plus exact HTML snippets labelled with the page and location (`<head>`, before `</body>`) they belong in, ordered by priority.

Never fabricate values the user must own: business name, real social profiles, verification codes, and analytics IDs are either taken from the site/repo or marked clearly as placeholders the user must fill — with instructions.

## Step 4 — Validate

- Repo mode: run the project's build; confirm it passes. Validate JSON-LD (structurally, or via a validator if network access allows). Re-check that fixed pages render the new tags.
- Confirm robots.txt does not block anything it shouldn't and the sitemap URLs match real routes.
- If Lighthouse or similar ran in the audit, run it again and report before/after scores.
- Never claim a check passed unless actually run.

## Step 5 — Deliver

Report in this structure:

1. **Audit summary** — issues found by severity, per area (SEO / AEO-GEO / performance / missing files).
2. **Fixes applied** — every change made and every file generated, with locations.
3. **Before/after measurements** — where real measurements were possible.
4. **User actions required** — Search Console submission steps (add property → verify → submit sitemap), placeholder values to fill, DNS/server items (HTTPS, redirects, caching headers) that cannot be fixed from code alone, with exact instructions for each.
5. **Ongoing recommendations** — content and authority work that code cannot do: publishing cadence, backlink strategy, keyword targeting — stated briefly and honestly as the part no tool can automate.

---

*Maintained by [eWebCity](https://eWebCity.co.uk) — eWebCity.co.uk*
