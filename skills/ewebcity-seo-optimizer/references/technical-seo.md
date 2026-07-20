# Technical SEO Audit Checklist

Check every item per page type. Record pass/fail with the exact evidence (the tag found, or its absence).

## Indexability and crawlability
- HTTPS enforced; HTTP redirects to HTTPS (301).
- One canonical host (www vs non-www) with 301 from the other.
- robots.txt exists, is valid, allows crawling of public content, and links the sitemap.
- XML sitemap exists, is referenced in robots.txt, contains only canonical, indexable, 200-status URLs.
- No accidental `noindex` meta tags or `X-Robots-Tag` headers on public pages.
- No orphan pages — every important page reachable via internal links.
- Clean URL structure: lowercase, hyphens, no session IDs or unnecessary parameters.
- Custom 404 page returning actual 404 status (not a 200 "soft 404").
- Redirect chains eliminated (max one hop).

## Head / meta per page
- Unique `<title>`, ~50–60 characters, primary keyword near the front.
- Unique meta description, ~150–160 characters, written to earn the click.
- `<link rel="canonical">` pointing to the correct absolute URL.
- `<meta name="viewport" content="width=device-width, initial-scale=1">`.
- `<html lang="…">` set correctly.
- Open Graph tags: og:title, og:description, og:image (1200×630), og:url, og:type.
- Twitter Card tags: twitter:card, twitter:title, twitter:description, twitter:image.
- Charset declared; favicon and apple-touch-icon linked.

## Content structure
- Exactly one `<h1>` per page containing the page's primary topic.
- Logical heading hierarchy (no skipped levels).
- Semantic HTML: `<main>`, `<nav>`, `<header>`, `<footer>`, `<article>` where appropriate.
- Descriptive anchor text (no "click here").
- No thin/duplicate pages competing for the same keyword (flag for the user; content decisions are theirs).

## Structured data (JSON-LD, in `<head>` or end of `<body>`)
Add the types that match the site:
- `Organization` (or `LocalBusiness` with address/hours for local sites) — sitewide.
- `WebSite` with `SearchAction` (sitelinks search box) — homepage.
- `BreadcrumbList` — any page with breadcrumbs.
- `Article` / `BlogPosting` — blog posts (headline, author, datePublished, dateModified, image).
- `Product` with offers/price/availability — product pages; `AggregateRating` only if real reviews exist.
- `FAQPage` — pages with genuine Q&A content.
Never mark up content that is not visible on the page — that violates Google's guidelines and risks manual action.

## Images
- Descriptive `alt` on every meaningful image; empty `alt=""` on decorative ones.
- Modern formats (WebP/AVIF) with fallbacks; explicit width/height to prevent layout shift.
- Descriptive filenames.

## Internationalization (if multi-language)
- `hreflang` tags including `x-default`, reciprocal across all language versions.

## Mobile
- Responsive layout, tap targets ≥ 48px, no horizontal scroll, font size ≥ 16px base.
