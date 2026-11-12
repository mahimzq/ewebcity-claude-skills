#!/usr/bin/env python3
"""Build the uploadable WordPress companion ZIP from checked-out source."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import zipfile


def build(output: Path) -> tuple[int, Path]:
    root = Path(__file__).resolve().parents[1]
    source = root / "integrations" / "wordpress" / "ewebcity-seo-bridge"
    if not (source / "ewebcity-seo-bridge.php").is_file():
        raise ValueError("WordPress bridge source is missing. Run this script from the complete repository or npm package.")
    files = sorted(path for path in source.rglob("*") if path.is_file())
    if not files or any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("The bridge source must contain regular files and no symbolic links.")
    for path in files:
        relative = path.relative_to(source)
        if any(part.startswith(".") for part in relative.parts) or not (
            path.suffix in (".php", ".txt", ".md", ".css", ".js") or path.name == "LICENSE"
        ):
            raise ValueError("Unexpected file in the bridge directory; review the source before packaging.")
    output = output.absolute()
    if output.suffix.lower() != ".zip":
        raise ValueError("Output must be a .zip file.")
    if any(part.is_symlink() for part in (output, *output.parents)):
        raise ValueError("Output symbolic links are not supported.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves an earlier package; fixed archive metadata is reproducible.
    with output.open("xb") as stream:
        try:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in files:
                    entry = zipfile.ZipInfo("ewebcity-seo-bridge/" + path.relative_to(source).as_posix())
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    entry.external_attr = 0o100644 << 16
                    archive.writestr(entry, path.read_bytes())
        except Exception:
            stream.close()
            output.unlink(missing_ok=True)
            raise
    return len(files), output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New ZIP path; existing files are never replaced.")
    args = parser.parse_args()
    try:
        count, output = build(args.output)
        print(f"WordPress plugin ZIP: {output} ({count} source files)")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Could not build WordPress plugin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
