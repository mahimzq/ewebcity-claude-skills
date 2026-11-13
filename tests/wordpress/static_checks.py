#!/usr/bin/env python3
"""Source-only checks; these cannot establish PHP syntax or WordPress behaviour."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "integrations" / "wordpress" / "ewebcity-seo-bridge"
SOURCE = (PLUGIN / "ewebcity-seo-bridge.php").read_text(encoding="utf-8")


class SourceOnlyBridgeChecks(unittest.TestCase):
    def test_declared_compatibility_and_original_code_licence(self):
        for text in ("Requires at least: 5.6", "Requires PHP: 7.4", "Version: 2.2.0", "License: MIT"):
            self.assertIn(text, SOURCE)
        self.assertEqual((ROOT / "LICENSE").read_bytes(), (PLUGIN / "LICENSE").read_bytes())

    def test_no_mutation_or_outbound_calls_in_plugin(self):
        banned = r"\b(?:update_option|add_option|delete_option|update_post_meta|add_post_meta|delete_post_meta|wp_insert_post|wp_update_post|wp_delete_post|update_user_meta|wp_remote_get|wp_remote_post|wp_remote_request|file_put_contents|fopen|unlink|shell_exec|eval|unserialize)\s*\("
        self.assertIsNone(re.search(banned, SOURCE))
        self.assertNotIn("admin_post_nopriv_", SOURCE)
        self.assertNotIn("wp_ajax_nopriv_", SOURCE)

    def test_security_boundaries_are_explicit_in_source(self):
        for text in ("current_user_can( 'manage_options' )", "'permission_callback' => array( __CLASS__, 'can_read' )",
                     "WP_REST_Server::READABLE", "check_admin_referer( 'ewebcity_seo_snapshot', 'ewebcity_seo_nonce' )",
                     "'post_status' => 'publish'", "'has_password' => false", "'publicly_queryable' => true",
                     "'fields' => 'ids'", "MAX_SNAPSHOT_BYTES = 10485760", "private, no-store, max-age=0"):
            self.assertIn(text, SOURCE)

    def test_synthetic_contract_fixture_is_bounded_and_excludes_content(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "snapshot.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(data["format"], "ewebcity-wordpress-snapshot")
        self.assertEqual(data["metadata_semantics"], "stored_provider_overrides_not_rendered_metadata")
        self.assertEqual(data["auditor"], "Mahim")
        self.assertIs(data["_demonstration"], True)
        self.assertLessEqual(data["pagination"]["per_page"], 100)
        self.assertIsNone(data["posts"][0]["metadata"]["yoast"]["canonical"])
        for post in data["posts"]:
            self.assertEqual(set(post), {"id", "type", "url", "modified_gmt", "metadata", "truncated_fields", "omitted_fields"})


if __name__ == "__main__":
    print("SOURCE-ONLY checks: no PHP interpreter, WordPress runtime or live site is exercised.")
    unittest.main(verbosity=2)
