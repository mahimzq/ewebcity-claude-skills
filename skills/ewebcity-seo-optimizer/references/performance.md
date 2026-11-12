# Performance and Core Web Vitals

Guidance checked: **2026-11-12**. Measure before choosing fixes. Page weight and source inspection are diagnostic clues, not measurements of the user's loading, interaction or layout experience.

## Record the right measurement

| Metric | Good field threshold | What it describes |
| --- | --- | --- |
| LCP | ≤ 2.5 seconds | Largest-content loading experience. |
| INP | ≤ 200 milliseconds | Responsiveness to interactions. |
| CLS | ≤ 0.1 | Unexpected layout movement. |

Assess at the **75th percentile**, with mobile and desktop separate. A field pass requires the relevant metrics to meet their targets with sufficient data. Missing field data means unmeasured, not zero or passed.

- **Field:** use available CrUX, Search Console or authorised real-user measurements. Record URL versus origin scope, device group, collection window and source. Never present origin-level data as page-specific.
- **Lab:** use an available browser/Lighthouse run to diagnose a reproducible scenario. Record version, URL, date, device/viewport, throttling and run conditions. A Lighthouse score is not a ranking score or proof of field compliance.
- A navigation-only lab run does not measure representative real-user INP. Total Blocking Time may help diagnose interaction problems but is not INP and must not be relabelled.
- An HTTP fetch duration is not browser load time, TTFB decomposition or LCP. Counting tags in fetched HTML is not a complete network waterfall; scripts may load resources dynamically.
- For before/after comparisons, reuse comparable conditions and explain any variance. Field improvement needs a later collection window; a local patch cannot instantly change historical CrUX data.

## Choose fixes from observed bottlenecks

1. **Loading:** identify the actual LCP element and whether delay comes from the server, resource discovery, download or rendering. Resize/compress images and use responsive sources where useful. Avoid lazy-loading the LCP image; use priority/preload only for confirmed critical resources to avoid competing downloads.
2. **Interaction:** inspect long main-thread tasks, expensive handlers, hydration and third-party work. Split/yield work and reduce avoidable JavaScript. Check that delayed scripts still provide required features and consent behaviour.
3. **Layout:** reserve image, video, embed and ad space; inspect font swaps and inserted content. Dimensions help but do not guarantee a zero CLS score.
4. **Render blocking:** remove unused resources and preserve CSS order and loading semantics. Inline CSS or defer scripts only when the measured gain and rendering/functional checks justify it.
5. **Fonts:** subset and reduce variants where licensing/content allows. Choose `font-display` for the actual design and check layout effects. Preload only fonts needed immediately; excessive preload/preconnect can waste resources.
6. **Delivery:** inspect compression and cache headers. Use long-lived immutable caching for content-hashed public assets when appropriate. Do not cache personalised HTML or API responses publicly. Check updates, authentication and invalidation after any cache change.

## Framework-aware checks

- Inspect installed versions before using framework APIs. Reuse the project's bundler, image pipeline and font tooling rather than adding overlapping packages.
- For React/Next.js, investigate oversized client bundles, unnecessary hydration and route-level loading. SSR/SSG can improve discovery and speed, but do not switch architecture without evidence of the problem and compatibility checks.
- For a client-rendered SPA, compare source and rendered content, links and metadata. Rendering dependence is a limitation to evaluate; it does not alone prove Google indexing failure.
- For Laravel/Django or other server-rendered apps, profile server response, database queries and cache boundaries before changing infrastructure.
- Check production output and actual network transfers. Source maps are not inherently an SEO failure; assess their size, source exposure and project debugging policy. Import syntax alone does not prove a bundle is tree-shaken.
- Set transfer-size budgets from the site's measured baseline and audience. There is no universal 300 KB JavaScript limit, mandatory CDN, or automatic SEO failure for HTTP/1.1.

## Validate and report

Run focused rendering and functional checks for affected pages and the project's relevant build checks. Re-measure the bottleneck, describe the before/after evidence, and identify any unmeasured field outcome. Report a fix as applied only where the changed code/configuration was actually written and verified.

## Official sources

- [Core Web Vitals metrics, thresholds and field measurement](https://web.dev/articles/vitals)
- [Search Console Core Web Vitals report](https://support.google.com/webmasters/answer/9205520)
- [JavaScript rendering and search](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)
