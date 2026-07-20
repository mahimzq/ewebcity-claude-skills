# AEO and GEO Optimization

AEO (Answer Engine Optimization) targets featured snippets, People Also Ask, and voice assistants. GEO (Generative Engine Optimization, sometimes called AI SEO) targets citation and visibility in ChatGPT, Perplexity, Google AI Overviews, and similar AI answer systems. Both reward the same underlying property: content structured so a machine can extract a direct, attributable answer.

## AEO — structure for direct answers

- **Question-shaped headings**: use the actual question users ask as an `<h2>`/`<h3>`, followed immediately by a 40–60 word direct answer, then elaboration. This is the featured-snippet format.
- **FAQ sections** with `FAQPage` JSON-LD on pages that genuinely answer questions.
- **Definition-first paragraphs**: for "what is X" topics, open with a one-sentence definition.
- **Lists and tables** for steps, comparisons, and specs — snippets frequently pull these verbatim.
- **HowTo content** structured as numbered steps with clear step headings.
- **Speakable-friendly writing**: short sentences, plain language in answer blocks (voice assistants read these aloud).

## GEO — visibility in AI answers

- **llms.txt** at the site root: a markdown file summarising what the site is, its key pages, and canonical facts about the business. Template in `required-files.md`. It is an emerging convention — cheap to add, increasingly consumed by AI crawlers.
- **Allow AI crawlers deliberately** in robots.txt: GPTBot, ClaudeBot, PerplexityBot, Google-Extended. Default to allowing them (visibility in AI answers is the goal of GEO); if the user objects to AI training on their content, present the trade-off and let them decide per bot.
- **Citable facts**: concrete, dated, specific statements ("founded in 2018", "processes 2M requests/day") get cited; vague marketing copy does not.
- **Entity clarity**: consistent naming of the business, people, and products across the site, backed by `Organization` structured data with `sameAs` links to official profiles — this is how AI systems disambiguate the entity.
- **Author and freshness signals**: visible author, published/updated dates in both content and `Article` schema.
- **Self-contained sections**: each section should make sense when extracted alone, since generative engines quote fragments, not pages.

## What to flag but not fabricate

Content depth, original data, and expertise signals (E-E-A-T) drive both AEO and GEO but cannot be generated truthfully by a tool. Recommend specifically — e.g. "add an author bio with credentials to blog posts", "publish the pricing data you mentioned as a comparison table" — rather than inventing credentials or statistics.
