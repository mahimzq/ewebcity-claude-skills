"""Implementation guidance selected by the operator, never stack detection."""
from __future__ import annotations

from copy import deepcopy

CHECKED_AT = "2026-11-12"
PLATFORMS = ("generic", "wordpress", "laravel", "php", "javascript", "static")
_GOOGLE = {
    "label": "Google: developer SEO guidance",
    "url": "https://developers.google.com/search/docs/fundamentals/get-started-developers",
    "checked_at": CHECKED_AT,
}
_CONTEXTS = {
    "generic": {
        "label": "Any website / framework not specified",
        "guidance": [
            "Trace each confirmed issue to the actual CMS setting, template, route or hosting rule before editing.",
            "Use the site's real canonical URLs and visible content; preserve intentional private-page and staging restrictions.",
            "Recheck the affected public responses after a change and keep uncrawled pages marked as unverified.",
        ],
        "references": [_GOOGLE],
    },
    "wordpress": {
        "label": "WordPress / Yoast SEO / Rank Math",
        "guidance": [
            "Inspect the active SEO provider and the affected post's Yoast SEO or Rank Math editor controls. A stored empty override can inherit a valid template.",
            "Review Settings > Reading for intended search visibility, then the provider's title, description, canonical and robots settings. Do not change deliberate restrictions automatically.",
            "Use one responsible metadata implementation. If both providers are active, inspect duplicate output before deciding which plugin or theme setting to change.",
            "After an authorised edit in WordPress, clear the relevant page/CDN cache and repeat the public-source audit. A bridge snapshot does not prove what the front end served.",
        ],
        "references": [
            {"label": "Yoast SEO REST API (read-only)", "url": "https://developer.yoast.com/customization/apis/rest-api/", "checked_at": CHECKED_AT},
            {"label": "Rank Math headless metadata", "url": "https://rankmath.com/kb/headless-cms-support/", "checked_at": CHECKED_AT},
        ],
    },
    "laravel": {
        "label": "Laravel",
        "guidance": [
            "Locate the route, controller and actual Blade layout/component that produce the affected page; for Inertia or another JavaScript front end, inspect its rendering path too.",
            "Set page-specific metadata in the shared head layout and escape plain text with Blade's normal escaped output. Derive canonical URLs from the site's configured public origin and verified route.",
            "Verify response status, redirect destinations and any X-Robots-Tag middleware. Check the existing sitemap generator against public routes; do not invent routes or modification dates.",
            "Run the project's relevant HTTP/feature checks and repeat the public audit after deployment and relevant cache refresh. The source crawler does not inspect PHP, the database or private routes.",
        ],
        "references": [
            {"label": "Laravel Blade templates (match the installed version)", "url": "https://laravel.com/docs/13.x/blade", "checked_at": CHECKED_AT},
            _GOOGLE,
        ],
    },
    "php": {
        "label": "PHP / custom server application",
        "guidance": [
            "Trace the affected route to its PHP controller and shared head template; retain the application's existing routing and metadata conventions.",
            "Escape title and meta-attribute text for its HTML context with an explicit UTF-8 encoding. Validate canonical URLs separately; escaping does not establish a trustworthy destination.",
            "Review header/status handling before output, redirects and the actual rewrite configuration. Use verified public routes for sitemap changes.",
            "Lint changed PHP and run the existing project checks, then re-fetch the actual response. A successful syntax check alone does not establish SEO correctness.",
        ],
        "references": [
            {"label": "PHP htmlspecialchars", "url": "https://www.php.net/manual/en/function.htmlspecialchars.php", "checked_at": CHECKED_AT},
            _GOOGLE,
        ],
    },
    "javascript": {
        "label": "JavaScript / React / Next.js / Vue / Nuxt",
        "guidance": [
            "Identify the real framework, router and server/client rendering mode from the repository. This selection does not detect a framework or execute JavaScript.",
            "Compare response-source metadata and links with the rendered DOM on representative routes. A client-rendered shell needs browser evidence before conclusions about rendered content.",
            "Use the installed framework's metadata mechanism; in Next.js App Router inspect metadata/generateMetadata, while other routers need their own documented head implementation.",
            "Check direct deep-link responses, genuine 404 statuses, canonical consistency and crawlable links; run the project's build/checks and re-audit deployed output.",
        ],
        "references": [
            {"label": "Google JavaScript SEO basics", "url": "https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics", "checked_at": CHECKED_AT},
            {"label": "Next.js metadata (match the installed version)", "url": "https://nextjs.org/docs/app/getting-started/metadata-and-og-images", "checked_at": CHECKED_AT},
        ],
    },
    "static": {
        "label": "Static HTML / generated website",
        "guidance": [
            "Change the source template or generator responsible for the affected page, not only a build artefact that will be overwritten.",
            "Keep one intended title, description and canonical per public page; verify relative links, image alternatives and deployment base paths.",
            "Check hosting redirects and error status separately from saved HTML. Generate sitemap entries only from real public build routes.",
            "Rebuild using the existing toolchain, inspect the generated HTML and repeat the audit against the deployed site.",
        ],
        "references": [_GOOGLE],
    },
}


def implementation_context(platform: str | None = None, *, wordpress: bool = False) -> dict:
    """Keep user-selected guidance separate from observed audit findings."""
    if platform is not None and platform not in PLATFORMS:
        raise ValueError("Unsupported implementation platform.")
    selected = platform or ("wordpress" if wordpress else "generic")
    context = deepcopy(_CONTEXTS[selected])
    context.update({
        "platform": selected,
        "basis": "user_selected" if platform is not None else "wordpress_snapshot" if wordpress else "unspecified",
        "note": "Implementation guidance only. Platform selection does not change the source-HTML checks, prove the site's technology or validate a repository. JavaScript rendering and authenticated application routes require separate evidence.",
    })
    return context
