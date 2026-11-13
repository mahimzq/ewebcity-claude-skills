# Auditing WordPress, Laravel, PHP, JavaScript and other websites

Last checked: 12 November 2026.

The source-HTML auditor is independent of the server framework. A public HTTP(S) page can be analysed whether it comes from WordPress, Laravel, PHP, a JavaScript framework or a static build. A saved HTML document can be analysed offline. Access controls, robots rules and crawl limits still apply; this is not a promise to inspect every route of every website.

`--platform wordpress|laravel|php|javascript|static|generic` selects implementation guidance for the report and action list. It does not fingerprint the website or change the source checks. If a WordPress snapshot is supplied and the option is omitted, the report explains that the snapshot supplied the WordPress context. A specified JavaScript context can still accompany a WordPress export.

```bash
python3 /path/to/ewebcity-seo-optimizer/scripts/audit.py \
  --url https://example.com --platform laravel --auditor Mahim \
  --output ./seo-audit/laravel --max-pages 30
```

## Locate the real implementation before fixing it

| Website | Inspect in the actual repository/admin | Verify after the change |
| --- | --- | --- |
| WordPress | Active SEO provider, post editor SEO controls, Settings → Reading, theme head hooks, sitemap and cache settings. Import a bridge snapshot when useful. | Actual public HTML/headers after the relevant cache refresh; inherited provider templates and duplicate output. |
| Laravel | `composer.json`, routes, controllers, Blade layouts/components and middleware. Check Inertia/SPA rendering separately if present. | Project HTTP/feature checks, canonical and redirect targets, status/headers and deployed public HTML. |
| Custom PHP | Entry point, router, shared head template, header calls and server rewrite configuration. | PHP lint and existing tests, actual HTTP status/redirects and context-appropriate output escaping. |
| JavaScript | Framework/version/router, server or client rendering, metadata components, build output and data-loading paths. | Representative direct-route responses, rendered DOM, genuine error responses, source/DOM consistency and the existing build. |
| Static HTML/generator | Source layout, page front matter, canonical base URL, generated route list and hosting configuration. | Generated HTML, deployment base paths, redirects/status and actual public responses. |
| Other stack | Real route/template/CMS ownership and the project's existing tooling. | Its native checks plus the observed public response. |

These are inspection starting points, not claims that a named file or setting exists in a supplied project. Inspect framework versions and repository instructions first. Do not add a second SEO mechanism that fights the existing one or overwrite generated outputs without fixing their source.

## JavaScript needs separate rendered evidence

A server response can contain a shell while the browser later creates titles, text or links. A source-only warning describes the saved or received source; it does not prove that the rendered DOM lacks the same content. When browser access is available, compare source and rendered output for representative templates and record the actual tool, URL and time. If rendering is unavailable, keep that check unverified and request the relevant saved output when it would change the conclusion.

Use the framework's documented metadata facilities for its installed version. For example, Next.js App Router supports metadata exports and `generateMetadata` in server components. Other frameworks and routers have their own behaviour. Do not infer indexing, search snippets or AI citations from a successful browser render.

## Evidence and author attribution

Each new report defaults to `Auditor: Mahim`; `--auditor 'Another auditor'` changes the author label. The audit records machine observations and explicit limitations, so attribution never implies an independent manual review. Live results retain HTTP evidence; saved HTML does not invent it. Provider exports, source findings, rendered evidence and repository checks remain distinct.

## Primary references

- [Google developer SEO guidance](https://developers.google.com/search/docs/fundamentals/get-started-developers)
- [Google JavaScript SEO basics](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)
- [Laravel Blade templates](https://laravel.com/docs/13.x/blade) — use the documentation version that matches the project.
- [PHP htmlspecialchars](https://www.php.net/manual/en/function.htmlspecialchars.php) — HTML escaping is distinct from URL validation.
- [Next.js metadata and OG images](https://nextjs.org/docs/app/getting-started/metadata-and-og-images)
- [WordPress integration](wordpress-integration.md) — bridge setup, metadata interpretation and official vendor API boundaries.
