# eWebCity Claude Skills

Professional Claude skills by [eWebCity](https://eWebCity.co.uk).

| Skill | What it does |
|---|---|
| **ewebcity-fullstack-engineer** | Disciplined workflow for implementing features and fixing bugs in real repositories: inspect first, minimal diffs, full-stack end-to-end implementation, security review, honest validation, structured delivery report. |
| **ewebcity-seo-optimizer** | Full-site audit and auto-fix for SEO, AEO (answer engines), GEO (AI engines like ChatGPT/Perplexity/AI Overviews), and page-load performance (Core Web Vitals). Generates missing files: robots.txt, sitemap.xml, llms.txt, manifest, structured data. |

## Install

### Claude Code (via npx — no clone needed, once published to npm)

```bash
# Install all skills for your user account (~/.claude/skills)
npx ewebcity-claude-skills

# Or install into the current project only (./.claude/skills)
npx ewebcity-claude-skills --project

# Install one skill
npx ewebcity-claude-skills ewebcity-seo-optimizer

# See what's available
npx ewebcity-claude-skills --list
```

Restart your Claude Code session and the skills are active — they trigger automatically when relevant.

### Claude Code (from GitHub, without npm)

```bash
git clone https://github.com/mahimzq/ewebcity-claude-skills.git
cp -r ewebcity-claude-skills/skills/* ~/.claude/skills/
```

### Claude.ai (web app)

Upload the `.skill` files from [Releases](../../releases) in a chat and click **Save skill**, or attach the skill folder contents to a Project.

## Usage examples

- "Add a payment history page to my Laravel app" → *ewebcity-fullstack-engineer*
- "Audit eWebCity.co.uk and fix everything that hurts SEO and page speed" → *ewebcity-seo-optimizer*
- "My site has no robots.txt or sitemap, add all the Google files" → *ewebcity-seo-optimizer*

## Structure

```
skills/
├── ewebcity-fullstack-engineer/
│   ├── SKILL.md
│   └── references/  (security checklist, frontend/backend standards, delivery template)
└── ewebcity-seo-optimizer/
    ├── SKILL.md
    └── references/  (technical SEO, AEO/GEO, performance, required files)
```

## License

MIT © [eWebCity](https://eWebCity.co.uk)
