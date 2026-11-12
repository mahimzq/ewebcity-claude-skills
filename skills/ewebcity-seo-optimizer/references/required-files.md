# Site Files: Applicability and Generation

Guidance checked: **2026-11-12**. The filename is retained for compatibility; these files are **conditional**, not a mandatory SEO bundle. Inspect existing generated routes, CMS/plugin output and hosting configuration before creating or replacing anything.

| File/configuration | When useful | Required inputs |
| --- | --- | --- |
| `robots.txt` | An intended crawler policy or sitemap discovery declaration. Absence alone is not an indexing failure. | Exact origin, current rules, relevant paths and known owner preferences. |
| XML sitemap/index | Discovery of canonical public URLs, particularly larger or changing sites. | Verified URL inventory, canonical decisions and trustworthy change dates if available. |
| `llms.txt` | Optional interoperability for an identified consumer or an explicitly requested experiment. | Verified public summary, real links and accurate descriptions. |
| Web app manifest | Product requirements for an installable web app; not a generic SEO repair. | Real app name, scope/start URL and existing usable icons. |
| Favicons/social images | Branding, browser UI and sharing previews. | Real image files and verified asset paths. |
| `security.txt` | An established vulnerability-reporting process. | A working reporting contact and a maintained expiry date. |
| Search verification files/tags | The chosen provider's actual ownership-verification step. | The exact provider-issued token or file and authority to make that change. |
| Advertising files | A real advertising integration requiring them. | The provider's actual authorised seller/app records. |

## Rules for every generated output

- Use the framework's existing mechanism and conventions. Do not add a dependency, duplicate a dynamic route with a static file, or overwrite plugin-managed output without understanding ownership.
- Write deployable files only with resolved values. Keep examples and unresolved questions in the report; never ship `DOMAIN`, `SITE_NAME`, `PASTE_CODE_HERE`, invented dates or links to nonexistent icons.
- Preserve the user's existing policy and unrelated content. Apply changes within the authorisation already given; prepare a focused diff and validation result. Publication and production configuration changes require matching scope, not a new blanket confirmation for every edit.
- Distinguish generated locally, validated locally, deployed and observed live. A local file's presence does not prove the live site serves it.

## robots.txt

Read and parse the existing file first. Test effective rules against representative public pages, assets and intentionally restricted paths for each relevant crawler. User-agent-specific groups can have a different outcome from the wildcard group.

Do not insert guessed `/admin/`, cart, query-string or asset blocks. Robots rules do not protect private content, implement `noindex` or choose canonical URLs. Authentication is required for private data; intentional exclusions need to remain intact.

Add a `Sitemap:` declaration only for a resolved sitemap URL. Do not add AI-specific allow rules by default: search and training controls are independent (see `aeo-geo.md`). Record an unspecified policy as a decision, then continue other authorised work.

## XML sitemaps

1. Combine discovered URLs with any authorised route/CMS inventory. Preserve case, significant query parameters and language variants; do not mechanically rewrite URLs.
2. Include intended public canonical URLs with observed successful responses and no conflicting exclusion. For undeployed routes, label live verification pending. Exclude redirects, known errors and unintended duplicate/noindex URLs.
3. Serialize XML using an XML library, UTF-8 and correct escaping. Validate namespace, absolute URLs, duplicates and host scope.
4. Use `lastmod` only when the underlying content's meaningful modification date is known. Do not stamp the audit date on every URL. Google ignores sitemap `priority` and `changefreq`; they are not score improvements.
5. Split at **50,000 URLs or 50 MB uncompressed**, whichever comes first, and generate a sitemap index when needed. Preserve existing image/video/news extensions when applicable.
6. Re-fetch deployed files if deployment is in scope. A submitted or valid sitemap does not guarantee indexing.

Prefer the site's established dynamic generator for changing content. Inspect framework versions and project dependencies before choosing an implementation.

## Optional supporting files

- **llms.txt:** use verified public site identity and canonical page links. Label its purpose; give it no Google-ranking weight. Do not assert that any provider consumes it without evidence.
- **Manifest/icons:** verify every referenced asset's existence, format and size. Do not manufacture icon references or change installability/display behaviour merely to satisfy an SEO checklist.
- **security.txt:** use `/.well-known/security.txt` only with a real maintained process. Omit the file when the contact or expiry cannot be established.
- **Advertising files:** take records from the actual advertising provider; do not invent seller IDs or assume an ad-supported site uses a particular supply chain.

## Verification and submission

Use authorised connected tools or the exact user-provided verification artifact when available. Otherwise explain the missing provider step. Do not create dummy Search Console/Bing tokens. DNS verification, property creation and sitemap submission may be completed only within the user's existing scope and available access.

If IndexNow is requested and supported, validate host/key scope, submit changed URLs only and respect response/rate-limit handling. HTTP 200 means receipt; 202 means key validation is pending, not that URLs are indexed. The Google Indexing API is limited to eligible job-posting/livestream pages; it is not a general SEO submission endpoint.

## Official sources

- [Robots.txt rules and response handling](https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec)
- [Sitemap generation and limits](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google's llms.txt guidance](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
- [IndexNow protocol](https://www.indexnow.org/documentation)
- [Google Indexing API scope](https://developers.google.com/search/apis/indexing-api/v3/using-api)
