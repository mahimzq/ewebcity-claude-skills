# Demonstration report

Open `demo-report.html` in a browser to explore the report design. **The report uses a fictional saved page, a synthetic WordPress snapshot and synthetic performance exports. It is not an assessment of a live website, a real WordPress connection, eWebCity's own performance or real Chrome user data.** The dashboard displays this distinction prominently.

The example fixes the fixture's deliberate `noindex` and malformed JSON-LD, then compares the two snapshots. Other findings remain visible. The exact same synthetic performance inputs are used in both snapshots; the example does not claim a performance improvement.

The report includes **Auditor: Mahim**, WordPress implementation guidance and raw Yoast overrides. The empty description and absent canonical override demonstrate inheritance uncertainty; the report does not turn either into a confirmed frontend problem. `sample-rankmath.json` is a separate synthetic alternative, not a recommendation to activate both SEO plugins.

To regenerate all three normal output files in a new directory:

```bash
python3 examples/generate_demo.py --output ./seo-audit/demo
```

Open `./seo-audit/demo/report.html`. Try search, status/impact/category/URL filters, page drill-down, expandable evidence, appearance controls and **Print / PDF**. Printing includes the complete report, even when interactive filters hide some findings.

To exercise Rank Math import instead:

```bash
node bin/audit.js --html examples/sample-page.html --url https://example.com/studio \
  --wordpress-json examples/sample-rankmath.json --platform wordpress \
  --output ./seo-audit/rankmath-demo
```

Each synthetic snapshot has an explicit `_demonstration: true` marker. Its import notes remain labelled even when used outside the demo generator.

For a real audit, use your actual site or saved HTML and genuine exports. See the root README and the skill's WordPress/performance references. Do not use these synthetic JSON files as client evidence.
