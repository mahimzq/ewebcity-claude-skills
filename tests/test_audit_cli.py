"""Command integration: attribution, guidance and isolated WordPress credentials."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ewebcity-seo-optimizer/scripts"))
from audit import audit_offline, main

TARGET = "https://example.com/page"
ENDPOINT = "https://example.com/wp-json/ewebcity/v1/snapshot"


class AuditCLIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.html = self.root / "page.html"
        self.html.write_text('<!doctype html><html lang="en"><head><title>Example</title>'
                             '<meta name="description" content="A real summary"></head>'
                             '<body><h1>Example</h1></body></html>', encoding="utf-8")

    def args(self, name="report"):
        return ["--url", TARGET, "--html", str(self.html), "--output", str(self.root / name)]

    def run_main(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(args)
        return status, out.getvalue(), err.getvalue()

    def test_new_offline_report_attributes_mahims_name_without_network(self):
        with patch("safe_http.socket.getaddrinfo", side_effect=AssertionError("offline DNS")):
            status, _out, err = self.run_main(self.args())
        self.assertEqual(status, 0, err)
        report = json.loads((self.root / "report/audit.json").read_text())
        self.assertEqual(report["auditor"], "Mahim")
        self.assertEqual(report["coverage"]["requests"], 0)
        self.assertEqual(report["implementation"]["basis"], "unspecified")
        self.assertIn("Mahim", (self.root / "report/report.html").read_text())
        self.assertIn("Mahim", (self.root / "report/fixes.md").read_text())

    def test_platform_is_explicit_guidance_and_does_not_change_observed_findings(self):
        observations = []
        for platform in ("generic", "wordpress", "laravel", "php", "javascript", "static"):
            status, _out, err = self.run_main(self.args(platform) + ["--platform", platform, "--auditor", "Review Team"])
            self.assertEqual(status, 0, err)
            report = json.loads((self.root / platform / "audit.json").read_text())
            self.assertEqual(report["auditor"], "Review Team")
            self.assertEqual(report["implementation"]["basis"], "user_selected")
            self.assertEqual(report["implementation"]["platform"], platform)
            observations.append([(f["rule_id"], f["status"], f["evidence"]["observation"]) for f in report["findings"]])
        self.assertTrue(all(item == observations[0] for item in observations))

    def test_invalid_auditor_rejected_before_any_collection(self):
        for auditor in (" ", "A" * 101, "Mahim\nForged label", "M\x00ahim"):
            with self.subTest(auditor=repr(auditor)), patch("audit.audit_offline") as collect:
                with self.assertRaises(SystemExit) as caught, redirect_stderr(io.StringIO()):
                    main(self.args() + ["--auditor", auditor])
                self.assertEqual(caught.exception.code, 2)
                collect.assert_not_called()
        self.assertFalse((self.root / "report").exists())

    def test_offline_mode_rejects_live_wordpress_connection_before_import(self):
        with patch("safe_http.socket.getaddrinfo", side_effect=AssertionError("offline DNS")):
            with self.assertRaises(SystemExit) as caught, redirect_stderr(io.StringIO()):
                main(self.args() + ["--wordpress-api", ENDPOINT])
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse((self.root / "report").exists())

    def test_snapshot_and_connection_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught, redirect_stderr(io.StringIO()):
            main(self.args() + ["--wordpress-json", "snapshot.json", "--wordpress-api", ENDPOINT])
        self.assertEqual(caught.exception.code, 2)

    def test_missing_connection_credentials_stop_before_crawling(self):
        stub = SimpleNamespace(fetch_wordpress_evidence=lambda *args, **kwargs: self.fail("fetch without credentials"))
        with patch.dict(sys.modules, {"wordpress": stub}), patch.dict(os.environ, {}, clear=True), patch("audit.audit_live") as crawl:
            status, _out, err = self.run_main(["--url", TARGET, "--output", str(self.root / "report"), "--wordpress-api", ENDPOINT])
        self.assertEqual(status, 1)
        self.assertIn("EWEBCITY_WP_APP_PASSWORD", err)
        crawl.assert_not_called()

    def test_connection_credentials_only_reach_the_dedicated_reader(self):
        source_report = audit_offline(self.html, TARGET)
        observed = {}
        def fetch(endpoint, target, username, password, **kwargs):
            observed.update(endpoint=endpoint, target=target, username=username, password=password, **kwargs)
            return {"mode": "authenticated_snapshot", "posts": []}
        def save(report, *args):
            observed["report"] = report
        stub = SimpleNamespace(fetch_wordpress_evidence=fetch)
        with patch.dict(sys.modules, {"wordpress": stub}), patch.dict(os.environ, {
            "EWEBCITY_WP_USER": "private-user-marker", "EWEBCITY_WP_APP_PASSWORD": "private-password-marker"
        }), patch("audit.audit_live", return_value=source_report) as crawl, patch("reporting.write_reports", side_effect=save):
            status, out, err = self.run_main(["--url", TARGET, "--output", str(self.root / "report"), "--wordpress-api", ENDPOINT])
        self.assertEqual(status, 0, err)
        self.assertEqual(observed["password"], "private-password-marker")
        self.assertEqual(observed["report"]["implementation"]["basis"], "wordpress_snapshot")
        self.assertEqual(observed["report"]["auditor"], "Mahim")
        visible = out + err + json.dumps(observed["report"]) + repr(crawl.call_args)
        self.assertNotIn("private-password-marker", visible)
        self.assertNotIn("private-user-marker", visible)

    def test_bad_export_is_rejected_before_source_collection(self):
        def fail(*args):
            raise ValueError("Invalid snapshot schema.")
        stub = SimpleNamespace(load_wordpress_evidence=fail)
        with patch.dict(sys.modules, {"wordpress": stub}), patch("audit.audit_offline") as collect:
            status, _out, err = self.run_main(self.args() + ["--wordpress-json", "bad.json"])
        self.assertEqual(status, 1)
        self.assertIn("Invalid snapshot schema", err)
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
