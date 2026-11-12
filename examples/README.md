# Demonstration report

Open `demo-report.html` in a browser to explore the report design. **The report uses a fictional saved page and synthetic performance exports. It is not an assessment of a live website, eWebCity's own performance or real Chrome user data.** The dashboard displays this distinction prominently.

The example fixes the fixture's deliberate `noindex` and malformed JSON-LD, then compares the two snapshots. Other findings remain visible. The exact same synthetic performance inputs are used in both snapshots; the example does not claim a performance improvement.

To regenerate all three normal output files in a new directory:

```bash
python3 examples/generate_demo.py --output ./seo-audit/demo
```

Open `./seo-audit/demo/report.html`. Try search, status/impact/category/URL filters, page drill-down, expandable evidence, appearance controls and **Print / PDF**. Printing includes the complete report, even when interactive filters hide some findings.

For a real audit, use your actual site or saved HTML and genuine exports. See the root README and the skill's performance reference. Do not use these synthetic JSON files as client evidence.
