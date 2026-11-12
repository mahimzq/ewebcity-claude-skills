# AEO and GEO: Discovery, Content and Evidence

Guidance checked: **2026-11-12**. AEO and GEO describe work on answer/search visibility. They do not provide a universal ranking formula, and a successful audit cannot guarantee a featured snippet or AI citation.

## Build on verified eligibility

1. Establish crawl access, potential indexability, rendering and snippet controls using `technical-seo.md`.
2. For Google generative features, inspect the site's **Search generative AI control** in Search Console when authorised account evidence is available. The current guide documents this control in addition to ordinary indexing/snippet requirements. An unauthenticated crawler cannot establish the setting; mark it not checked.
3. Check actual crawler/CDN behaviour where logs or verified provider tools are available. A robots declaration alone does not prove a bot can pass a firewall or fetch the page.
4. Keep provider-specific eligibility, user sampling and first-party performance data separate. Do not infer one provider's coverage from another's.

## Separate crawler purposes

| Crawler/control | Purpose and audit treatment |
| --- | --- |
| `OAI-SearchBot` | OpenAI search discovery. Inspect its effective robots policy and available access evidence. |
| `GPTBot` | OpenAI model-training crawling. Its policy is independent of search discovery; never automatically allow it as an SEO fix. |
| `ChatGPT-User` | User-triggered requests, not automatic search indexing. Robots rules may not apply to these requests; do not use it as the search eligibility test. |
| `Googlebot` | Google Search crawling. Preserve intentional access and snippet choices. |
| `Google-Extended` | A separate Google training/grounding control. Check its current documented scope; it does not replace Googlebot or the Search Console generative AI control. |
| Other providers | Verify the provider's current official bot names and purposes before proposing policy changes. Do not group every AI-named bot under a single allow rule. |

Read existing owner preferences before editing robots.txt. A request for better search visibility does not imply a request to change model-training preferences. If the policy is unspecified, report current behaviour and the specific decision needed without blocking unrelated authorised fixes.

## Improve content for the reader

- Identify the real question or task the page serves. Put a useful answer where readers can find it; use question headings, definitions, tables or steps when they suit the material.
- Treat answer length and paragraph structure as editorial choices. There is no guaranteed 40–60 word snippet recipe, mandatory chunk size or required keyword variant count.
- Prefer original experience, examples, supported data and clear limitations over generic restatements. Check claims against supplied evidence; mark missing facts for the owner rather than inventing them.
- Keep business, author and product identities consistent. Link only verified official profiles; add actual publication/update dates and credentials when supported.
- Improve navigation and topical coverage where the existing material supports it. Competitor comparisons require observed competitor pages or licensed/authorised data; distinguish suggestions from measured gaps.
- Retain useful FAQs and numbered instructions as content formats. Do not promise Google FAQ rich results or assume every question page needs FAQ schema.
- Flag unhelpful mass-generated pages, doorway/location variants and fabricated mentions. A content plan must add user value and follow applicable search policies.

## Optional llms.txt

Use `llms.txt` only for a requested or identified consumer that benefits from it, or an explicitly labelled interoperability experiment. Google Search says it ignores the file and that it neither improves nor harms Google visibility/ranking. Its absence is **not an SEO/AEO failure** and must not lower a Google diagnostic score.

If generated, use verified public facts and canonical links; omit private material, invented statistics and unsupported promises of crawler adoption. Keep it consistent with the site. It is not a replacement for crawl access, indexable content or a sitemap.

## Measure outcomes

Use `evidence-and-measurement.md` to import Google/Bing reports, compare like-for-like periods and record explicit AI-search samples. A mention, a linked citation, an impression, a visit and a conversion are different events. Report each using its source's definition; never label a checklist grade as observed AI visibility.

## Official sources

- [Google generative AI optimisation guidance](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
- [Search generative AI control](https://support.google.com/webmasters/answer/16908024)
- [OpenAI crawlers and independent controls](https://developers.openai.com/api/docs/bots)
- [Google common crawlers and Google-Extended](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers)
- [Google spam policies](https://developers.google.com/search/docs/essentials/spam-policies)
- [Google feature/documentation updates](https://developers.google.com/search/updates)
