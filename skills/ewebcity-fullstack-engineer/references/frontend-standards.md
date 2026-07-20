# Frontend and UX Standards

## General frontend work

Match the current design system — visual consistency with the existing app matters more than personal preference. Reuse existing components before creating new ones, and keep new components reasonably small and type-safe.

Every data-driven view needs its full set of states: loading, error, success, and empty. Missing states are the most common gap in otherwise-complete features.

Also maintain:
- Responsive behaviour consistent with the rest of the app; no layout shifts.
- Semantic HTML with accessible labels; keyboard accessibility; preserved focus behaviour (especially in modals, menus, and dynamic content).
- Performance hygiene: avoid unnecessary re-renders (memoisation where the project already uses it, stable references, correct dependency arrays).

## Three.js / WebGL / WebGPU / TSL work

GPU work leaks silently — the browser will not warn you. On any component or scene teardown:

- Dispose of geometries, materials, textures, and render targets.
- Remove event listeners and cancel animation loops (`cancelAnimationFrame`).
- Handle resize correctly (renderer size + camera aspect + projection matrix update).

Performance rules:
- Cap device pixel ratio (typically `Math.min(window.devicePixelRatio, 2)`).
- Pause or reduce work in hidden tabs (visibility API).
- Avoid per-frame allocations — reuse vectors, matrices, and arrays.
- Avoid unnecessary shader recompilation (stable material definitions, avoid toggling defines per frame).
- Consider mobile GPU limits: texture sizes, draw calls, fill rate.

Robustness:
- Provide a graceful fallback or clear message when WebGL/WebGPU is unsupported or context creation fails.
- Handle context loss where the project's usage warrants it.
