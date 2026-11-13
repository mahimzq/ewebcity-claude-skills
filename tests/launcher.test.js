"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const launcher = path.resolve(__dirname, "../bin/audit.js");

function run(args, options = {}) {
  return spawnSync(process.execPath, [launcher, ...args], {
    encoding: "utf8", timeout: 10000, ...options,
  });
}

test("audit launcher exposes the real Python help", () => {
  const result = run(["--help"]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /--max-total-bytes/);
  assert.match(result.stdout, /--compare/);
});

test("audit launcher propagates argument errors", () => {
  const result = run(["--unknown-argument"]);
  assert.equal(result.status, 2, result.stderr);
});

test("missing configured Python gives an actionable failure", () => {
  const result = run(["--help"], {
    env: { ...process.env, EWEBCITY_PYTHON: path.join(os.tmpdir(), "ewebcity-no-such-python-7f4b3d") },
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Python 3\.10\+/);
  assert.match(result.stderr, /EWEBCITY_PYTHON/);
});

test("offline launcher handles literal paths and writes honest snapshot outputs", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "ewebcity-launcher-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const input = path.join(root, "page $(literal) with spaces.html");
  const output = path.join(root, "report with spaces");
  fs.writeFileSync(input, '<!doctype html><html lang="en"><head><title>Example</title></head><body><h1>Example</h1></body></html>');
  const result = run(["--html", input, "--url", "https://example.com/", "--output", output]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(fs.readFileSync(path.join(output, "audit.json"), "utf8"));
  assert.equal(report.mode, "offline_source_html");
  assert.equal(report.coverage.requests, 0);
  assert.equal(report.pages[0].http_status, null);
  assert.ok(report.findings.some((finding) => finding.rule_id === "http_status" && finding.status === "not_checked"));
  assert.ok(fs.existsSync(path.join(output, "report.html")));
  assert.ok(fs.existsSync(path.join(output, "fixes.md")));
});
