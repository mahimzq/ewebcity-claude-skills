"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");
const INSTALLER = path.join(ROOT, "bin", "install.js");
const { destinationLayout } = require(INSTALLER);
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

const NATIVE_TARGETS = [
  { target: "claude", projectRoot: ".claude", personalRoot: ".claude" },
  { target: "codex", projectRoot: ".agents", personalRoot: ".agents" },
  { target: "cursor", projectRoot: ".cursor", personalRoot: ".cursor" },
  { target: "copilot", projectRoot: ".github", personalRoot: ".copilot" },
  { target: "antigravity", projectRoot: ".agents", personalRoot: path.join(".gemini", "config") },
];

for (const { target, projectRoot, personalRoot } of NATIVE_TARGETS) {
  test(`--target ${target} installs only in its documented project location`, (t) => {
    const directory = project(t);
    succeeds(run(directory, [SEO, "--target", target]));
    const destination = path.join(directory, projectRoot, "skills", SEO);
    assert.equal(fs.readFileSync(path.join(destination, "SKILL.md"), "utf8"),
      fs.readFileSync(path.join(ROOT, "skills", SEO, "SKILL.md"), "utf8"));
    assert.equal(fs.existsSync(path.join(destination, "scripts", "audit.py")), true);
    assert.equal(fs.existsSync(path.join(destination, "PORTABLE_PROMPT.md")), false);
    assert.deepEqual(fs.readdirSync(directory), [projectRoot]);
    assert.deepEqual(fs.readdirSync(path.join(directory, projectRoot, "skills")), [SEO]);
    assert.equal(fs.existsSync(path.join(directory, projectRoot, "ewebcity-staging")), false);
  });

  test(`${target} personal destination stays inside the supplied home anchor`, (t) => {
    // Exercise path selection with a temporary anchor; never install into a real
    // account or change HOME/CODEX_HOME to test personal configuration.
    const directory = project(t);
    const layout = destinationLayout(directory, { target, project: false });
    const expectedRoot = path.join(directory, personalRoot);
    assert.equal(layout.skillsRoot, path.join(expectedRoot, "skills"));
    assert.equal(layout.backupRoot, path.join(expectedRoot, "ewebcity-backups"));
    assert.equal(layout.stagingRoot, path.join(expectedRoot, "ewebcity-staging"));
    assert.deepEqual(fs.readdirSync(directory), []);
  });
}

for (const args of [
  ["--target"],
  ["--target", "--force"],
  ["--target="],
  ["--target", "unknown-platform"],
  ["--target", "../../escape"],
  ["--target", "__proto__"],
  ["--target", "cursor", "--target", "claude"],
]) {
  test(`invalid target arguments fail without writes: ${args.join(" ")}`, (t) => {
    const directory = project(t);
    fails(run(directory, [SEO, ...args]), /target/i);
    assert.deepEqual(fs.readdirSync(directory), []);
  });
}

test("--target=vscode selects Copilot and keeps unrelated settings", (t) => {
  const directory = project(t);
  fs.mkdirSync(path.join(directory, ".github"));
  fs.writeFileSync(path.join(directory, ".github", "copilot-instructions.md"), "My repository instructions");
  succeeds(run(directory, [SEO, "--target=vscode"]));
  assert.equal(fs.existsSync(path.join(directory, ".github", "skills", SEO, "SKILL.md")), true);
  assert.equal(fs.readFileSync(path.join(directory, ".github", "copilot-instructions.md"), "utf8"), "My repository instructions");
  assert.deepEqual(fs.readdirSync(directory), [".github"]);
});

test("updating Cursor leaves an existing Claude copy unchanged", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO]));
  const claudeSkill = path.join(installed(directory), "SKILL.md");
  fs.writeFileSync(claudeSkill, "Independent Claude customisation");
  succeeds(run(directory, [SEO, "--target", "cursor"]));
  const cursorSkill = path.join(directory, ".cursor", "skills", SEO, "SKILL.md");
  fs.writeFileSync(cursorSkill, "Previous Cursor customisation");
  succeeds(run(directory, [SEO, "--target", "cursor", "--force"]));
  assert.equal(fs.readFileSync(claudeSkill, "utf8"), "Independent Claude customisation");
  assert.equal(fs.existsSync(path.join(directory, ".claude", "ewebcity-backups")), false);
  const backupRoot = path.join(directory, ".cursor", "ewebcity-backups");
  const backups = fs.readdirSync(backupRoot);
  assert.equal(backups.length, 1);
  assert.equal(fs.readFileSync(path.join(backupRoot, backups[0], SEO, "SKILL.md"), "utf8"), "Previous Cursor customisation");
});

test("Codex and Antigravity share one protected project copy and backup root", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO, "--target", "codex"]));
  const shared = path.join(directory, ".agents", "skills", SEO);
  fs.writeFileSync(path.join(shared, "SKILL.md"), "Shared local instructions");
  fs.writeFileSync(path.join(shared, "stale.txt"), "Stale shared resource");
  fails(run(directory, [SEO, "--target", "antigravity"]), /already exists/);
  assert.equal(fs.readFileSync(path.join(shared, "SKILL.md"), "utf8"), "Shared local instructions");
  succeeds(run(directory, [SEO, "--target", "antigravity", "--force"]));
  assert.equal(fs.existsSync(path.join(shared, "stale.txt")), false);
  assert.deepEqual(fs.readdirSync(path.join(directory, ".agents", "skills")), [SEO]);
  assert.deepEqual(fs.readdirSync(directory), [".agents"]);
  const backupRoot = path.join(directory, ".agents", "ewebcity-backups");
  const backups = fs.readdirSync(backupRoot);
  assert.equal(backups.length, 1);
  assert.equal(fs.readFileSync(path.join(backupRoot, backups[0], SEO, "SKILL.md"), "utf8"), "Shared local instructions");
});

for (const { target, relative } of [
  { target: "codex", relative: ".agents" },
  { target: "cursor", relative: ".cursor/skills" },
  { target: "copilot", relative: `.github/skills/${SEO}` },
  { target: "antigravity", relative: ".agents/ewebcity-staging" },
  { target: "portable", relative: "ewebcity-portable" },
]) {
  test(`${target} rejects a redirected destination at ${relative}`, (t) => {
    const directory = project(t);
    const outside = path.join(directory, "outside");
    fs.mkdirSync(outside);
    fs.writeFileSync(path.join(outside, "keep.txt"), "Unrelated content");
    const link = path.join(directory, relative);
    fs.mkdirSync(path.dirname(link), { recursive: true });
    if (!makeLink(t, outside, link)) return;
    fails(run(directory, [SEO, "--target", target, "--force"]), /symbolic link/);
    assert.deepEqual(fs.readdirSync(outside), ["keep.txt"]);
    assert.equal(fs.readFileSync(path.join(outside, "keep.txt"), "utf8"), "Unrelated content");
  });
}

for (const target of ["codex", "cursor", "copilot", "antigravity", "portable"]) {
  test(`${target} dry run creates no directories`, (t) => {
    const directory = project(t);
    const result = run(directory, [SEO, "--target", target, "--dry-run"]);
    succeeds(result);
    assert.match(result.stdout, /Dry run: no files changed/);
    assert.deepEqual(fs.readdirSync(directory), []);
  });
}

for (const target of ["portable", "chatgpt", "deepseek"]) {
  test(`${target} exports a complete bundle and compact prompt in the current directory`, (t) => {
    const directory = project(t);
    // Deliberately omit --project: portable aliases must still use this temporary
    // working directory, never the user's personal application folders.
    const result = spawnSync(process.execPath, [INSTALLER, SEO, "--target", target], {
      cwd: directory, encoding: "utf8", timeout: 20000,
    });
    succeeds(result);
    assert.match(result.stdout, /Export only/);
    assert.deepEqual(fs.readdirSync(directory), ["ewebcity-portable"]);
    const bundle = path.join(directory, "ewebcity-portable", "skills", SEO);
    const source = path.join(ROOT, "skills", SEO);
    const prompt = fs.readFileSync(path.join(bundle, "PORTABLE_PROMPT.md"), "utf8");
    assert.ok(prompt.includes(fs.readFileSync(path.join(source, "SKILL.md"), "utf8")));
    assert.match(prompt, /does not register an application integration/);
    assert.match(prompt, /mark the affected checks not checked/);
    assert.match(prompt, /references\/technical-seo\.md/);
    assert.ok(!prompt.includes(fs.readFileSync(path.join(source, "references", "technical-seo.md"), "utf8")),
      "Reference corpus should remain in separate files, with a compact prompt index");
    assert.equal(fs.readFileSync(path.join(bundle, "references", "technical-seo.md"), "utf8"),
      fs.readFileSync(path.join(source, "references", "technical-seo.md"), "utf8"));
    assert.equal(fs.readFileSync(path.join(bundle, "scripts", "audit.py"), "utf8"),
      fs.readFileSync(path.join(source, "scripts", "audit.py"), "utf8"));
    const bootstrap = path.join(source, "assets", "portable-prompt.md");
    if (fs.existsSync(bootstrap)) assert.ok(prompt.includes(fs.readFileSync(bootstrap, "utf8")));
  });
}

test("portable aliases preserve prior exports and require --force for replacement", (t) => {
  const directory = project(t);
  succeeds(run(directory, [SEO, "--target", "chatgpt"]));
  const bundle = path.join(directory, "ewebcity-portable", "skills", SEO);
  fs.writeFileSync(path.join(bundle, "PORTABLE_PROMPT.md"), "My adapted prompt");
  fs.writeFileSync(path.join(bundle, "stale.txt"), "Local note");
  fails(run(directory, [SEO, "--target", "deepseek"]), /already exists/);
  assert.equal(fs.readFileSync(path.join(bundle, "PORTABLE_PROMPT.md"), "utf8"), "My adapted prompt");
  succeeds(run(directory, [SEO, "--target", "portable", "--force", "--dry-run"]));
  assert.equal(fs.readFileSync(path.join(bundle, "PORTABLE_PROMPT.md"), "utf8"), "My adapted prompt");
  succeeds(run(directory, [SEO, "--target", "deepseek", "--force"]));
  assert.equal(fs.existsSync(path.join(bundle, "stale.txt")), false);
  const backupRoot = path.join(directory, "ewebcity-portable", "ewebcity-backups");
  const backups = fs.readdirSync(backupRoot);
  assert.equal(backups.length, 1);
  assert.equal(fs.readFileSync(path.join(backupRoot, backups[0], SEO, "PORTABLE_PROMPT.md"), "utf8"), "My adapted prompt");
  assert.equal(fs.readFileSync(path.join(backupRoot, backups[0], SEO, "stale.txt"), "utf8"), "Local note");
});
