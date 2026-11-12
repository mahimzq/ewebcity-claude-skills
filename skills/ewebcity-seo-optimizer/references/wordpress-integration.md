# WordPress, Yoast SEO and Rank Math integration

Last checked: 12 November 2026. Use the installed plugin versions' current documentation before changing settings.

## What connects

The optional **eWebCity SEO Bridge** companion plugin supplies a bounded snapshot of published, non-password-protected content and stored SEO overrides. It supports active Yoast SEO and Rank Math providers. The audit accepts either a downloaded JSON snapshot or one explicitly requested authenticated HTTPS connection to the bridge. A normal public HTML audit needs no WordPress plugin.

The companion plugin lives in the repository at `integrations/wordpress/ewebcity-seo-bridge/`. It is a separate WordPress plugin; installing the agent skill does not activate it on a website. Build its upload ZIP with `python3 bin/build-wordpress.py --output ./dist/ewebcity-seo-bridge.zip`, or copy that plugin directory into an authorised site's `wp-content/plugins/` directory. Activate it through WordPress, then open **Tools → eWebCity SEO**. The complete repository includes the setup guide at `docs/wordpress.md`; the instructions below also work from an installed skill.

The bridge uses WordPress's `manage_options` capability for both its admin screen and REST snapshot. The admin download also requires the form nonce. It exports an allowlist of SEO fields and public URLs, excluding post content, authors, private posts, drafts, password-protected posts, arbitrary options and secrets. A snapshot contains at most 100 posts from one pagination page. Taxonomies, author archives and other pages remain outside this snapshot's coverage.

## Preferred portable workflow: export, audit, edit, retest

1. In **Tools → eWebCity SEO**, inspect the reported active provider and download the JSON snapshot for the desired page of results.
2. Supply that snapshot alongside the target website or saved HTML. Do not put a private export into a public repository or chat without checking its contents.
3. Run the installed skill's audit script:

```bash
python3 /path/to/ewebcity-seo-optimizer/scripts/audit.py \
  --html ./page.html --url https://example.com/service \
  --wordpress-json ./ewebcity-wordpress-snapshot.json \
  --platform wordpress --auditor Mahim --output ./seo-audit/wordpress
```

4. Read the **WordPress evidence** section alongside actual page findings. Make authorised changes through the existing Yoast/Rank Math controls or a reviewed repository patch.
5. Refresh the relevant page/CDN cache, export a fresh snapshot if needed and repeat the source audit into a new output directory. Compare actual frontend findings with `--compare`; imports do not turn those findings into passes.

`--html` remains strictly offline and cannot be combined with `--wordpress-api`. `--wordpress-json` reads one exported snapshot, not an arbitrary Yoast or Rank Math API response. Direct vendor head APIs have different schemas and are not silently treated as bridge exports.

## Authenticated connection

Use the **exact snapshot endpoint shown by the bridge**, which accommodates WordPress subdirectory installations and plain-permalink REST URLs. It must use HTTPS and match the audited site's exact origin. An ordinary pretty-permalink example is:

```text
https://example.com/wp-json/ewebcity/v1/snapshot?page=1&per_page=100
```

Create a separate WordPress **Application Password** for an authorised user who has `manage_options`. Configure `EWEBCITY_WP_USER` and `EWEBCITY_WP_APP_PASSWORD` in the local execution environment or secret manager. Do not place their values in command arguments, prompts, reports or committed files. Use the dedicated application credential, not the interactive account password.

```bash
python3 /path/to/ewebcity-seo-optimizer/scripts/audit.py \
  --url https://example.com \
  --wordpress-api 'https://example.com/wp-json/ewebcity/v1/snapshot?page=1&per_page=100' \
  --platform wordpress --auditor Mahim --output ./seo-audit/connected
```

The connector makes one bounded GET request with verified public-address resolution and a pinned TLS connection. It does not follow redirects, use environment proxies, retry authentication, traverse pagination or pass credentials into the public crawler. HTTP, private networks and cross-origin CMS backends are rejected. `--allow-localhost` applies only to the unauthenticated source crawler. If an endpoint is unavailable, use an authorised export rather than weakening access controls. Revoke the application credential when it is no longer required.

The bridge request has its own ten-MiB response cap and uses `--timeout`; it is separate from the source crawl's request/byte/time budget. Its request count and byte count belong to WordPress provenance, not page crawl coverage. A file's hash records what was supplied; it does not independently authenticate its author or contents.

## Interpret the data accurately

| Data | What it establishes | What it does not establish |
| --- | --- | --- |
| Provider entry | The snapshot reports that provider as active when exported. | Installed-but-inactive inventory, compatibility certification or present-day state. |
| Stored title/description | The explicit per-post override, including template placeholders. | The resolved frontend title/snippet; blank overrides can inherit defaults. |
| Stored canonical/robots | A provider setting requiring its own precedence and inheritance logic. | Effective HTML/HTTP directives, index status or canonical selection by a search engine. |
| Search visibility | The exported WordPress Reading preference. | Whether staging/privacy intent is wrong or every response contains `noindex`. |
| Pagination totals | Eligible posts counted by this snapshot. | Complete website coverage, including archives or uncrawled routes. |
| `Auditor: Mahim` | The report's requested author attribution. | Independent human review, certification or a completed live edit. |

Both providers being reported active is a reason to inspect duplicate/conflicting output, not permission to deactivate a plugin automatically. Preserve `null` (no stored override) and explicit empty values. Keep truncated or omitted fields and snapshot timestamps visible. Never derive an overall SEO or AI visibility score from the provider settings.

## Official APIs and write boundaries

- [Yoast REST API](https://developer.yoast.com/customization/apis/rest-api/): `yoast_head`/`yoast_head_json` on native REST objects and `/yoast/v1/get_head?url=...` expose rendered metadata. The documented API is read-only; it does not support updating data with POST/PUT.
- [Rank Math headless support](https://rankmath.com/kb/headless-cms-support/): enabling Headless CMS Support exposes `/rankmath/v1/getHead?url=...`, returning the generated head HTML. This is separate from the bridge's stored-value export.
- [WordPress Application Passwords](https://developer.wordpress.org/advanced-administration/security/application-passwords/): revocable per-application credentials used over HTTPS.
- [WordPress REST permissions](https://developer.wordpress.org/rest-api/extending-the-rest-api/adding-custom-endpoints/): check capabilities after authentication with a `permission_callback`.

The bridge implements no SEO-setting write endpoint. Editing remains in the installed provider's UI or a separately reviewed, authorised project change. Never guess a vendor write API or expose all protected post meta through REST to make an integration appear to work.
