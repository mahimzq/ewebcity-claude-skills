=== eWebCity SEO Bridge ===
Contributors: mahimzq
Tags: seo, audit, yoast, rank-math, metadata
Requires at least: 5.6
Requires PHP: 7.4
Stable tag: 2.2.0
License: MIT
License URI: https://opensource.org/license/mit/

Administrator-only, read-only SEO snapshots for eWebCity. Default auditor label: Mahim.

== Description ==

Tools > eWebCity SEO shows active Yoast SEO / Rank Math providers, an eligible public-post preview, existing post-editor and provider-control links, and a nonce-protected JSON download form.

The protected GET endpoint is /wp-json/ewebcity/v1/snapshot. It requires native WordPress authentication and the manage_options capability. Cookie authentication also needs the WordPress REST nonce. Remote clients should use native Application Passwords over HTTPS. The bridge does not implement a second login mechanism, store credentials, make outbound requests, or change SEO/content/settings.

Only published posts from post types with both public=true and publicly_queryable=true are eligible. Password-protected posts are excluded. Results are checked again after the query; an unexpected private/password-protected result fails the whole snapshot. Exports exclude post content, excerpts, author/user records, passwords, keys and unrelated plugin options. The only WordPress options read are blog_public and permalink_structure.

Yoast and Rank Math overrides are raw stored values. Empty or missing overrides, replacement variables, provider defaults, global templates, filters, caches and another active SEO plugin can make the rendered page different. Use an actual page audit to check the effective head, HTTP directives, indexing signals and accessibility. Nothing in the snapshot proves indexing, rankings, a certification or the quality of an audit. "Auditor: Mahim" identifies the intended report owner.

== Installation ==

1. Copy the complete ewebcity-seo-bridge folder into wp-content/plugins/ on an authorised WordPress site, or upload an archive containing that folder through Plugins > Add New.
2. Activate eWebCity SEO Bridge using WordPress's normal plugin controls.
3. Open Tools > eWebCity SEO as a user with manage_options.
4. Choose a page and page size, then download the JSON snapshot.
5. Supply the snapshot to the eWebCity audit workflow. Keep the original file as evidence of the collection time.

This repository directory is the installable plugin source. No automatic WordPress installation, account configuration or deployment is performed by the bridge.

== Endpoint and bounds ==

GET /wp-json/ewebcity/v1/snapshot?page=1&per_page=20

page: integer 1..100, default 1.
per_page: integer 1..100, default 20.
Posts are ordered by ID ascending. A page beyond the eligible total returns a fixed 400 error. An empty collection returns page=1, total_posts=0, total_pages=0. total_pages reports the true eligible count divided by page size; this bounded endpoint permits at most 100 requested pages. It does not promise complete coverage of larger sites or a transactionally frozen snapshot across requests.

Each metadata string is limited to 8192 UTF-8 bytes. Rank Math robots has at most 32 string entries, each under that same byte limit. Provider version identifiers are limited to 80 ASCII bytes; an empty version means it was not usable. Invalid UTF-8, NUL-containing or unexpected non-scalar metadata is omitted with a diagnostic, rather than serialised into an arbitrary object. Truncation preserves UTF-8 boundaries and records the affected field.

The shared builder rejects JSON above 10 MiB with status 413 and asks for a smaller per_page; the formatted download is checked separately. No partial snapshot is returned. Successful REST responses request private, no-store caching, and downloads use WordPress no-cache headers plus an attachment content type.

== Snapshot contract ==

format: ewebcity-wordpress-snapshot
schema_version: 1.0
bridge_version: 2.2.0
generated_at: UTC RFC3339 timestamp ending Z
auditor: Mahim
metadata_semantics: stored_provider_overrides_not_rendered_metadata
site: home_url, site_url, search_visibility (allow or discourage), permalink_structure
providers: active Yoast / Rank Math entries only, with id, active=true and version
pagination: page, per_page, total_posts, total_pages
posts: id, type, url, modified_gmt, metadata, truncated_fields, omitted_fields

modified_gmt is a UTC RFC3339 timestamp or null when the stored GMT value is unusable. url is the actual public permalink. Provider canonical fields are raw overrides and may be relative, templated or invalid; they are not promoted into a rendered canonical.

Yoast fields: title, description, canonical, robots_noindex, robots_nofollow, robots_advanced. Each is a stored scalar converted to a string, or null when absent/unusable. An explicitly stored empty string remains empty. Raw noindex values such as 0, 1 or 2 remain strings; no effective index policy is calculated.

Rank Math fields: title, description, canonical (string or null), robots (string array). An absent robots key yields []; an unusable value also yields [] with an omitted_fields diagnostic. Neither means that the final page is indexable.

Per-post diagnostics use names such as yoast.title, yoast.robots_advanced or rankmath.robots. A metadata provider key is absent when that provider is inactive. metadata is an empty JSON object when neither provider is active. The bridge does not export all provider settings or enable their optional headless APIs.

== Primary sources and verification ==

Metadata key mappings and API boundaries checked against vendor/core sources on 12 November 2026:

Yoast native metadata definitions and prefix:
https://github.com/Yoast/wordpress-seo/blob/trunk/inc/class-wpseo-meta.php

Rank Math native metadata keys:
https://github.com/rankmath/seo-by-rank-math/blob/master/wpml-config.xml
https://github.com/rankmath/seo-by-rank-math/blob/master/includes/modules/sitemap/providers/class-post-type.php

Public post-type filtering and password exclusion:
https://developer.wordpress.org/reference/functions/get_post_types/
https://developer.wordpress.org/reference/classes/wp_query/

Provider-rendered/headless output is a separate source of evidence:
https://developer.yoast.com/customization/apis/rest-api/
https://rankmath.com/kb/headless-cms-support/

WordPress authentication and permission callbacks:
https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/
https://developer.wordpress.org/rest-api/extending-the-rest-api/adding-custom-endpoints/

== Validation limits ==

Source-only checks and PHP stub contracts are included in the repository under tests/wordpress. The implementation environment lacked PHP, so it cannot establish a passing PHP lint/runtime result. The runner fails explicitly when PHP is missing. A successful PHP stub run still does not validate WordPress routing, the database, native authentication, actual provider versions, the admin UI or third-party hooks. Verify those in an authorised staging installation before deployment.

== Changelog ==

= 2.2.0 =
Initial bounded, administrator-only snapshot bridge. Read-only Yoast / Rank Math metadata export; no SEO/content mutation endpoints.
