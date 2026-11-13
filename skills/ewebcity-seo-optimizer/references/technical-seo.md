# Technical SEO Audit

Guidance checked: **2026-11-12**. Apply checks to the agreed crawl scope and representative page types. Use the evidence states in `evidence-and-measurement.md`; a missing observation is not a failed check.

## Discovery, access and indexing

- Record requested URL, final URL, HTTP status, redirects, response headers and fetch time. Check HTTPS and preferred-host consistency; permanent redirects can be 301 or 308. Preserve intentional alternate hosts and paths.
- Evaluate robots.txt rules for the relevant crawler and URL, including specific user-agent groups. A missing robots.txt file is not automatically a problem. Record 429, server errors and access challenges separately; do not interpret an unsuccessful fetch as unrestricted access.
- Inspect both robots metadata and `X-Robots-Tag`, including crawler-specific directives. Robots.txt controls fetching; `noindex` controls indexing when a crawler can read it. A blocked URL with `noindex` is a conflict to investigate, not proof of removal. Robots.txt is not access control for private data.
- Separate **crawlable**, **potentially indexable** and **confirmed indexed**. HTTP 200, a sitemap entry or a local parser cannot prove Google indexing. Use authorised URL Inspection evidence when available; otherwise mark actual indexing as not checked.
- Assess `nosnippet`, `max-snippet` and `data-nosnippet` against the owner's intended preview policy. Do not remove deliberate restrictions to increase an audit score.
- Inspect known sitemaps and declared indexes; compare with canonical public routes. Missing sitemap discovery is an opportunity or an unverified state, not by itself a critical indexing failure.
- Find broken internal links, redirect loops/chains and false success responses for missing content. Do not rename URLs or force lowercase merely for style: paths can be case-sensitive and migrations need mapped redirects.
- Report an orphan page only when there is a separate URL inventory to compare with the link graph. A bounded crawl alone cannot discover or disprove all orphans.

## Canonicals and rendering

- Resolve canonical links against the document URL and inspect HTTP `Link` canonicals where applicable. Prefer clear absolute canonical URLs, but do not reject a relative URL solely because it is relative.
- Flag multiple/conflicting declarations, canonical targets that fail, unintended cross-domain targets and disagreement with redirects, internal links or sitemap entries. A canonical is a signal, not a command; do not replace it with `noindex` as a deduplication shortcut.
- Where a browser is available, compare source HTML with rendered DOM for title, metadata, canonical, main text, links and structured data. Record which version each finding describes.
- Detect client-side routing, blocked resources, script failures and content requiring interaction. JavaScript is not automatically an indexing defect; source-only inspection is incomplete for client-rendered pages. Do not claim a browser run reproduces Google's rendering or proves indexing.

## Page identity and structure

- Check for a descriptive title reflecting the page's purpose; investigate missing, misleading or repetitive titles. A 50–60 character target is an editorial heuristic, not a Google limit or ranking requirement.
- Review descriptions for useful, page-specific summaries. A 150–160 character target is not a ranking rule; Google may derive a different snippet from the page. Length alone should not trigger a severe finding.
- Identify a clear main heading and understandable heading hierarchy. One H1 is a useful authoring convention; multiple H1s or a skipped level need contextual review, not an automatic ranking penalty.
- Check language, charset, viewport and readable mobile layout. Evaluate semantic landmarks, keyboard access, meaningful links and image alternatives as usability/accessibility concerns; do not invent numeric SEO penalties.
- Use descriptive alt text for meaningful images and empty alt text for decorative ones. Do not fabricate image content from filenames alone. Check responsive sizing and reserved image space with the performance checklist.
- Review Open Graph, social cards and icons for their actual sharing/branding use. Their absence is not a Google indexing blocker. Validate referenced assets before adding markup.
- For multilingual sites, inspect supported language/region values, reciprocal and self references, canonical consistency and equivalent destination content. Use `x-default` where there is an appropriate fallback; it is not mandatory on every multilingual page.

## Structured data

Inspect existing CMS/plugin output before adding another JSON-LD block. Validate syntax, applicable vocabulary, current feature requirements and consistency with visible content separately. Syntax success does not establish rich-result eligibility.

| Page/context | Candidate types and checks |
| --- | --- |
| Business identity | `Organization` or an accurate `LocalBusiness` subtype; real name, location, hours and official profiles only. |
| Site homepage | `WebSite` for site identity where appropriate. Do not add `SearchAction` to obtain the retired Google sitelinks search box. |
| Breadcrumb navigation | `BreadcrumbList` matching the page's real navigation hierarchy. |
| Editorial article | Applicable `Article`/`BlogPosting` type; truthful authorship, dates and images. |
| Product | Applicable product/offer properties supported by visible current prices and availability; ratings only when genuine and eligible. |
| Questions and answers | Useful visible Q&A may remain. Google FAQ rich results stopped on 7 May 2026; missing `FAQPage` is not a Google feature defect. |

Do not fabricate business facts, reviews, credentials, dates or relationships. Keep useful existing vocabulary unless it is incorrect; a retired Google feature does not make every instance of that schema invalid.

## Official sources

- [Robots.txt interpretation](https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec)
- [Noindex and crawler access](https://developers.google.com/search/docs/crawling-indexing/block-indexing)
- [Canonicalisation](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- [JavaScript SEO](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)
- [Titles](https://developers.google.com/search/docs/appearance/title-link) and [snippets](https://developers.google.com/search/docs/appearance/snippet)
- [Structured data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies)
- [FAQ retirement in the documentation updates](https://developers.google.com/search/updates)
- [Sitelinks search box retirement](https://developers.google.com/search/blog/2024/10/sitelinks-search-box)
