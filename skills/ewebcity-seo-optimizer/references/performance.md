# Page-Load Performance and Core Web Vitals

Targets: LCP < 2.5s, INP < 200ms, CLS < 0.1, plus small transfer sizes (initial JS well under 300KB gzipped for most sites). Fix in impact order: images → render-blocking resources → JS payload → fonts → caching/compression.

## Images (usually the biggest win)
- Convert to WebP/AVIF; compress; serve responsive sizes (`srcset`/`sizes` or the framework image component).
- `loading="lazy"` on below-the-fold images; **never** lazy-load the LCP image — give it `fetchpriority="high"` and consider `<link rel="preload">`.
- Explicit `width`/`height` (or CSS aspect-ratio) on every image to eliminate CLS.

## Render-blocking resources
- CSS: inline critical CSS for above-the-fold; load the rest non-blocking; remove unused CSS.
- JS: `defer` scripts (or `type="module"`); move non-essential third-party scripts to load after interaction or on idle; audit every third-party tag — analytics, chat widgets, and trackers are frequent LCP killers.
- Preconnect to required third-party origins: `<link rel="preconnect">` for fonts/CDN/API hosts actually used at load.

## JavaScript payload
- Code splitting per route (framework-native: Next.js automatic, React `lazy()` + `Suspense`, Vite dynamic imports).
- Tree-shakeable imports (`import { x } from 'lib'`, not whole-library imports; replace heavy libs where a small alternative exists — flag, don't swap silently).
- Production build verified: minification on, source maps not shipped to users, no development mode React in production.

## Fonts
- `font-display: swap`; preload the primary text font; self-host where licensing allows; subset to used character sets; limit families/weights.

## Caching and delivery
- Compression enabled (Brotli preferred, gzip fallback) — server/Nginx/CDN config.
- Long-lived `Cache-Control` with content-hashed filenames for static assets; sensible caching for HTML.
- HTTP/2 or HTTP/3 via the host/CDN; flag if the server responds over HTTP/1.1.
- CDN recommended for global audiences — instruct, since this is a hosting decision.

## Framework-specific quick checks
- **Next.js**: use `next/image`, `next/font`, metadata API; check for accidental client components pulling server-only pages into the client bundle; prefer static generation/ISR over SSR where content allows.
- **Vite/React SPA**: route-level code splitting; prerender or SSG critical pages if SEO matters (an SPA with client-only rendering is an SEO risk in itself — flag it and recommend prerendering/SSR).
- **Laravel/Django (server-rendered)**: enable template/view caching per framework, database query optimization on slow pages, asset bundling with hashing (Vite/Mix, collectstatic + WhiteNoise or CDN).

## Measuring
Prefer real measurements over assertions: run Lighthouse if installable in the environment; otherwise measure page weight, request count, and render-blocking resources from fetched HTML, and direct the user to PageSpeed Insights (pagespeed.web.dev) for field data. Always report what was measured vs. what is a recommendation.
