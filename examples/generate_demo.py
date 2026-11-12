"""Generate a clearly labelled report from saved HTML and synthetic metrics."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/ewebcity-seo-optimizer/scripts"))
from audit import audit_offline
from measurements import load_performance_evidence
from reporting import compare_reports, write_reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new report directory")
    args = parser.parse_args()
    example = ROOT / "examples"
    target = "https://example.com/studio"
    before = audit_offline(example / "sample-page.html", target)
    before["demonstration"] = True
    before["measurements"] = load_performance_evidence(
        [example / "sample-lighthouse.json", example / "sample-crux.json"], target)
    # Create a second actual snapshot, with two deliberate changes, for comparison.
    with tempfile.TemporaryDirectory(prefix="ewebcity-demo-") as tmp:
        changed = Path(tmp) / "after.html"
        source = (example / "sample-page.html").read_text(encoding="utf-8")
        changed.write_text(source.replace('content="noindex, follow"', 'content="index, follow"')
                          .replace('"name":"Demonstration page",}', '"name":"Demonstration page"}'), encoding="utf-8")
        after = audit_offline(changed, target)
    after["demonstration"] = True
    after["measurements"] = deepcopy(before["measurements"])
    # Keep the same imported evidence; this example does not claim a speed improvement.
    before["coverage"]["source_file"] = "sample-page.html"
    after["coverage"]["source_file"] = "sample-page.html with the documented example fixes"
    after["comparison"] = compare_reports(before, after)
    write_reports(after, args.output)
    print(f"Demonstration report: {args.output / 'report.html'}")


if __name__ == "__main__":
    main()
