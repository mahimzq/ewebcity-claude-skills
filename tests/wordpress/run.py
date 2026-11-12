#!/usr/bin/env python3
"""Run PHP syntax and stub contracts. Missing PHP is a failed validation gate."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent
PLUGIN = ROOT / "integrations" / "wordpress" / "ewebcity-seo-bridge"
sys.path.insert(0, str(ROOT / "skills" / "ewebcity-seo-optimizer" / "scripts"))
from wordpress import load_wordpress_evidence


def run() -> int:
    php = shutil.which("php")
    if not php:
        print("ERROR: PHP is unavailable. PHP lint and bridge contracts have NOT run. "
              "Run this command in CI or a development environment with PHP 7.4+ on PATH: "
              "python3 -B tests/wordpress/run.py", file=sys.stderr)
        return 1
    version = subprocess.run([php, "-r", "echo PHP_VERSION_ID;"], text=True, capture_output=True, timeout=20)
    if version.returncode or not version.stdout.strip().isdigit() or int(version.stdout) < 70400:
        print("ERROR: A working PHP 7.4+ runtime is required; validation did not run.", file=sys.stderr)
        return 1
    for source in sorted([*PLUGIN.rglob("*.php"), *TESTS.glob("*.php")]):
        result = subprocess.run([php, "-l", str(source)], cwd=ROOT, timeout=30)
        if result.returncode:
            return result.returncode
    result = subprocess.run([php, str(TESTS / "contract.php")], cwd=ROOT, timeout=120)
    if result.returncode:
        return result.returncode
    for mode in ("--snapshot", "--download"):
        result = subprocess.run([php, str(TESTS / "contract.php"), mode], cwd=ROOT,
                                text=True, capture_output=True, timeout=30)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            return result.returncode
        try:
            snapshot = json.loads(result.stdout)
            assert snapshot["format"] == "ewebcity-wordpress-snapshot"
            assert snapshot["metadata_semantics"] == "stored_provider_overrides_not_rendered_metadata"
            assert [post["id"] for post in snapshot["posts"]] == [1, 7]
            assert snapshot["posts"][0]["metadata"]["yoast"]["canonical"] is None
            assert len(result.stdout.encode("utf-8")) <= 10 * 1024 * 1024
            with tempfile.TemporaryDirectory(prefix="ewebcity-wp-contract-") as directory:
                exported = Path(directory) / "snapshot.json"
                exported.write_text(result.stdout, encoding="utf-8")
                imported = load_wordpress_evidence(exported, snapshot["site"]["home_url"])
                assert [post["id"] for post in imported["posts"]] == [1, 7]
                assert imported["snapshot_auditor"] == "Mahim"
        except (ValueError, KeyError, TypeError, AssertionError) as exc:
            print(f"ERROR: {mode} produced an invalid fixture snapshot: {exc}", file=sys.stderr)
            return 1
        print(f"PASS {mode}: bridge output under WordPress API stubs passes the Python importer")
    print("PHP lint/contracts passed. A real WordPress installation, authentication stack, "
          "database, Yoast/Rank Math and HTTP server remain untested by these stubs.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: PHP validation could not complete: {exc}", file=sys.stderr)
        raise SystemExit(1)
