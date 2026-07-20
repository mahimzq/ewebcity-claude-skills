# Required Site Files — Generation Rules and Templates

Check for each file; generate any that are missing. Place at the site root (or the framework's static/public directory: `public/` in Next.js/Vite/Laravel, the static config in Django). Replace ALL_CAPS placeholders with real values from the site/repo — never ship placeholder text without flagging it.

## robots.txt

```
User-agent: *
Allow: /

# Block genuinely private/duplicate areas only — never block CSS/JS
Disallow: /admin/
Disallow: /cart/
Disallow: /*?sort=

# AI crawlers — allowed by default for GEO visibility (confirm with user)
User-agent: GPTBot
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: PerplexityBot
Allow: /

Sitemap: https://DOMAIN/sitemap.xml
```

Rules: never `Disallow: /` on a public site; never block asset directories (Google must render the page); only disallow paths that actually exist.

## sitemap.xml

Build from real discovered routes — only canonical, indexable, 200-status URLs. Exclude redirects, noindex pages, and parameter variants.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://DOMAIN/</loc>
    <lastmod>YYYY-MM-DD</lastmod>
  </url>
</urlset>
```

For frameworks, prefer a dynamic generator over a static file when the site has generated content: Next.js `app/sitemap.ts`, Django `django.contrib.sitemaps`, Laravel spatie/laravel-sitemap (only add the dependency if the project's conventions allow). Over 50,000 URLs → sitemap index.

## llms.txt

```
# SITE_NAME

> One-paragraph summary of what the site/business is and does.

## Key pages
- [Page name](https://DOMAIN/path): one-line description

## About
Canonical facts: founding year, location, what the product/service does, contact.
```

## site.webmanifest

```json
{
  "name": "SITE_NAME",
  "short_name": "SHORT_NAME",
  "icons": [
    { "src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png" }
  ],
  "theme_color": "#COLOR",
  "background_color": "#COLOR",
  "display": "standalone"
}
```

Link in `<head>`: `<link rel="manifest" href="/site.webmanifest">`. Favicons: favicon.ico, favicon-32x32.png, apple-touch-icon.png (180×180). Generate from an existing logo in the repo if image tooling is available; otherwise instruct the user.

## security.txt (optional, good practice)

At `/.well-known/security.txt`:
```
Contact: mailto:SECURITY_EMAIL
Expires: YYYY-12-31T23:59:59Z
Preferred-Languages: en
```

## Google Search Console verification

Cannot be completed for the user — provide instructions:
1. Go to search.google.com/search-console → Add property (domain or URL prefix).
2. Verify via DNS TXT record (domain property) or HTML file/meta tag (URL prefix). If they choose the meta-tag method, add the placeholder `<meta name="google-site-verification" content="PASTE_CODE_HERE">` to the head and tell them where to paste the code.
3. After verification: Sitemaps → submit `sitemap.xml`.
4. Repeat for Bing Webmaster Tools (can import from Search Console).

## humans.txt / ads.txt / app-ads.txt

Only if applicable: ads.txt is required when the site serves programmatic ads — ask rather than assume.
