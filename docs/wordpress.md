# Connect WordPress, Yoast SEO and Rank Math

The **eWebCity SEO Bridge** is an optional companion plugin. It makes existing SEO configuration available to the audit report. The source audit itself works on WordPress and other websites without installing anything on the target.

## 1. Build and install the bridge

From the complete checked-out repository:

```bash
python3 bin/build-wordpress.py --output ./dist/ewebcity-seo-bridge.zip
```

In the authorised WordPress admin, open **Plugins → Add New Plugin → Upload Plugin**, choose that ZIP, install and activate it. Alternatively, copy `integrations/wordpress/ewebcity-seo-bridge/` into `wp-content/plugins/`, then activate it. The bridge requires WordPress 5.6+ and PHP 7.4+; use a currently supported WordPress/PHP release for your site.

Open **Tools → eWebCity SEO**. The screen shows **Auditor: Mahim**, active Yoast/Rank Math provider information, eligible post coverage, links to existing editing controls and the protected REST endpoint. Installing the agent skill alone does not install or activate this WordPress plugin.

## 2. Use an export without sharing credentials

Choose the pagination page and page size in **Tools → eWebCity SEO**, then download the snapshot JSON. The bridge covers one page of up to 100 published, non-password-protected posts/pages or other eligible public post types. Each pagination request is explicit; it does not imply that archives, private content or every website URL were covered.

```bash
node bin/audit.js \
  --url https://example.com \
  --wordpress-json ./ewebcity-wordpress-snapshot.json \
  --platform wordpress --auditor Mahim \
  --output ./seo-audit/wordpress
```

For a completely offline run, add `--html ./saved-page.html` and use that page's real URL. The HTML, JSON and Markdown outputs contain the same auditor attribution, with WordPress evidence separate from the public page checks.

This workflow also works in Claude, ChatGPT, DeepSeek or another host that can read the files and run Python. A host without code execution can review the supplied evidence and give the local command; it cannot truthfully claim to have executed the audit.

## 3. Optional direct connection

Create a dedicated **Application Password** for an authorised WordPress user with `manage_options`. Use the exact HTTPS snapshot URL displayed by the plugin. The website and endpoint must have the same scheme, host and port. WordPress installations in subdirectories and `?rest_route=/ewebcity/v1/snapshot` URLs are supported; a separate headless CMS origin is not.

In Bash, credentials can be entered without putting their values in command history:

```bash
read -r -p 'WordPress username: ' EWEBCITY_WP_USER
read -r -s -p 'WordPress Application Password: ' EWEBCITY_WP_APP_PASSWORD
export EWEBCITY_WP_USER EWEBCITY_WP_APP_PASSWORD

node bin/audit.js \
  --url https://example.com \
  --wordpress-api 'https://example.com/wp-json/ewebcity/v1/snapshot?page=1&per_page=100' \
  --platform wordpress --output ./seo-audit/connected

unset EWEBCITY_WP_USER EWEBCITY_WP_APP_PASSWORD
```

Use your secret manager or session environment on other shells. Do not paste passwords into chat, command arguments or committed files. The connector makes one GET with bounded response size; it never follows a redirect or passes the credentials into the public crawler. The credential authenticates only the requested read. The bridge has no SEO write endpoint.

`--wordpress-api` cannot be combined with `--html`; use a downloaded snapshot for offline work. Private-address and HTTP endpoints are rejected even if `--allow-localhost` is set for a public-source development audit. No access to a real WordPress installation is implied by installing the package.

## 4. Read the report and apply fixes

| Report evidence | How to use it |
| --- | --- |
| Active provider/version | Identify which existing controls to inspect; if both are active, investigate duplicate output. |
| Stored title/description | Review explicit overrides and template placeholders; empty values may inherit provider defaults. |
| Stored canonical/robots | Inspect intended settings, then confirm the actual frontend HTML and HTTP headers. |
| WordPress search visibility | Review the Reading preference in the context of public/staging/privacy intent. |
| Snapshot time, hash and pagination | Understand when and how much configuration was supplied; treat a local export as supplied evidence. |
| Auditor | Defaults to Mahim; `--auditor` can set another explicitly requested name. |

Apply authorised changes in the existing Yoast or Rank Math editor/settings, or through a reviewed project patch. Refresh the relevant cache, export fresh data if needed and repeat the source audit with a new output directory. The comparison only resolves findings that were actually rechecked. Reading settings cannot prove that the front end was fixed.

## Vendor API boundaries

Yoast's documented REST API returns generated metadata and is read-only. Rank Math's documented `getHead` route returns generated head HTML after Headless CMS Support is enabled. The bridge reads stored per-post values through WordPress and does not require those headless features to be enabled. Its snapshot format is intentionally different from either vendor's REST response.

See the packaged [WordPress integration reference](../skills/ewebcity-seo-optimizer/references/wordpress-integration.md) for data semantics, transport limits and primary sources. See [framework workflows](../skills/ewebcity-seo-optimizer/references/framework-workflows.md) for Laravel, PHP, JavaScript and static sites.

## Validation and removal

With PHP available, run the bridge's lint and stub contract runner documented in `tests/wordpress/`. These tests exercise permission checks, pagination, metadata allowlists and export shape; they do not replace an activation/export check on a real WordPress staging site with the installed Yoast/Rank Math versions.

For a staging check, verify that a logged-out request and an account without `manage_options` cannot read the bridge, an authorised export succeeds, drafts/password-protected posts are omitted, the snapshot imports, and public metadata remains unchanged. Keep real credentials and private exports outside the repository.

Deactivate and delete the bridge through WordPress when no longer needed, and revoke the dedicated Application Password. The bridge does not create SEO settings that need to be migrated back.
