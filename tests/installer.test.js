"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");
const INSTALLER = path.join(ROOT, "bin", "install.js");
const SEO = "ewebcity-seo-optimizer";
const FULLSTACK = "ewebcity-fullstack-engineer";

function project(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "ewebcity-installer-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function run(directory, args) {
  return spawnSync(process.execPath, [INSTALLER, "--project", ...args], {
    cwd: directory,
    encoding: "utf8",
    timeout: 20000,
  });
}

function installed(directory, name = SEO) {
  return path.join(directory, ".claude", "skills", name);
}

function succeeds(result) {
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stderr);
}

function fails(result, pattern) {
  assert.equal(result.error, undefined);
  assert.equal(result.status, 1, result.stdout);
  assert.match(result.stderr, pattern);
}

function noInstallation(directory) {
  assert.equal(fs.existsSync(path.join(directory, ".claude")), false);
}

function makeLink(t, target, link) {
  try {
    fs.symlinkSync(target, link, "dir");
  } catch (error) {
    if (error.code === "EPERM" || error.code === "ENOSYS") {
      t.skip("Directory symlinks are unavailable on this system");
      return false;
    }
    throw error;
  }
  return true;
}

for (const flag of ["--help", "-h", "--list"]) {
  test(`${flag} is read-only`, (t) => {
    const directory = project(t);
    const result = run(directory, [flag]);
    succeeds(result);
    assert.match(result.stdout, flag === "--list" ? /ewebcity-seo-optimizer/ : /Usage:/);
    noInstallation(directory);
  });
}

test("unknown options fail before installation", (t) => {
  const directory = project(t);
  fails(run(directory, ["--unknown-option"]), /Unknown option/);
  noInstallation(directory);
});

for (const names of [[SEO, "unknown-skill"], ["unknown-skill", SEO], ["../../escape"]]) {
  test(`all skill names are validated before writes: ${names.join(" ")}`, (t) => {
    const directory = project(t);
    fails(run(directory, names), /Unknown skill/);
    noInstallation(directory);
  });
}

test("installs only the selected skill", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO]));
  assert.equal(fs.readFileSync(path.join(installed(directory), "SKILL.md"), "utf8"),
    fs.readFileSync(path.join(ROOT, "skills", SEO, "SKILL.md"), "utf8"));
  assert.equal(fs.existsSync(installed(directory, FULLSTACK)), false);
  assert.equal(fs.existsSync(path.join(directory, ".claude", "ewebcity-staging")), false);
});

test("all destinations are checked before any skill is installed", (t) => {
  const directory = project(t);
  fs.mkdirSync(installed(directory, FULLSTACK), { recursive: true });
  fs.writeFileSync(path.join(installed(directory, FULLSTACK), "SKILL.md"), "Custom full-stack skill");
  fails(run(directory, [SEO, FULLSTACK]), /already exists/);
  assert.equal(fs.existsSync(installed(directory)), false);
  assert.equal(fs.readFileSync(path.join(installed(directory, FULLSTACK), "SKILL.md"), "utf8"), "Custom full-stack skill");
  assert.equal(fs.existsSync(path.join(directory, ".claude", "ewebcity-staging")), false);
});

test("an existing skill is unchanged without --force", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO]));
  const skill = path.join(installed(directory), "SKILL.md");
  fs.writeFileSync(skill, "My custom skill instructions");
  fs.writeFileSync(path.join(installed(directory), "local-file.txt"), "Keep this file");
  fails(run(directory, [SEO]), /already exists/);
  assert.equal(fs.readFileSync(skill, "utf8"), "My custom skill instructions");
  assert.equal(fs.readFileSync(path.join(installed(directory), "local-file.txt"), "utf8"), "Keep this file");
  assert.equal(fs.existsSync(path.join(directory, ".claude", "ewebcity-backups")), false);
});

test("--force keeps the previous tree as a backup and removes stale active files", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO]));
  fs.writeFileSync(path.join(installed(directory), "SKILL.md"), "Custom old version");
  fs.writeFileSync(path.join(installed(directory), "stale.txt"), "Old resource");
  const result = run(directory, [SEO, "--force"]);
  succeeds(result);
  assert.match(result.stdout, /Backup:/);
  assert.equal(fs.existsSync(path.join(installed(directory), "stale.txt")), false);
  assert.equal(fs.readFileSync(path.join(installed(directory), "SKILL.md"), "utf8"),
    fs.readFileSync(path.join(ROOT, "skills", SEO, "SKILL.md"), "utf8"));
  const backups = path.join(directory, ".claude", "ewebcity-backups");
  const entries = fs.readdirSync(backups);
  assert.equal(entries.length, 1);
  const backup = path.join(backups, entries[0], SEO);
  assert.equal(fs.readFileSync(path.join(backup, "SKILL.md"), "utf8"), "Custom old version");
  assert.equal(fs.readFileSync(path.join(backup, "stale.txt"), "utf8"), "Old resource");
  assert.deepEqual(fs.readdirSync(path.join(directory, ".claude", "skills")), [SEO]);
});

test("--dry-run validates a new installation without writes", (t) => {
  const directory = project(t);
  const result = run(directory, [SEO, "--dry-run"]);
  succeeds(result);
  assert.match(result.stdout, /Would install/);
  noInstallation(directory);
});

test("--dry-run --force preserves the active tree and creates no backup", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO]));
  fs.writeFileSync(path.join(installed(directory), "SKILL.md"), "Keep my instructions");
  const result = run(directory, [SEO, "--force", "--dry-run"]);
  succeeds(result);
  assert.match(result.stdout, /Would replace with backup/);
  assert.equal(fs.readFileSync(path.join(installed(directory), "SKILL.md"), "utf8"), "Keep my instructions");
  assert.equal(fs.existsSync(path.join(directory, ".claude", "ewebcity-backups")), false);
});

for (const relative of [".claude", ".claude/skills", `.claude/skills/${SEO}`, ".claude/ewebcity-staging"]) {
  test(`rejects destination symlinks at ${relative}`, (t) => {
    const directory = project(t);
    const outside = path.join(directory, "outside");
    fs.mkdirSync(outside);
    fs.writeFileSync(path.join(outside, "keep.txt"), "Unrelated content");
    const link = path.join(directory, relative);
    fs.mkdirSync(path.dirname(link), { recursive: true });
    if (!makeLink(t, outside, link)) return;
    fails(run(directory, [SEO, "--force"]), /symbolic link/);
    assert.deepEqual(fs.readdirSync(outside), ["keep.txt"]);
  });
}

test("rejects a symlink used as the backup directory", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO]));
  const before = fs.readFileSync(path.join(installed(directory), "SKILL.md"), "utf8");
  const outside = path.join(directory, "outside");
  fs.mkdirSync(outside);
  if (!makeLink(t, outside, path.join(directory, ".claude", "ewebcity-backups"))) return;
  fails(run(directory, [SEO, "--force"]), /symbolic link/);
  assert.equal(fs.readFileSync(path.join(installed(directory), "SKILL.md"), "utf8"), before);
  assert.deepEqual(fs.readdirSync(outside), []);
});

test("refuses a file in destination ancestry without altering it", (t) => {
  const directory = project(t);
  fs.writeFileSync(path.join(directory, ".claude"), "Unrelated file");
  fails(run(directory, [SEO]), /Expected a directory/);
  assert.equal(fs.readFileSync(path.join(directory, ".claude"), "utf8"), "Unrelated file");
});
