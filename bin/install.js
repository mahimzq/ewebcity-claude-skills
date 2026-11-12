#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const SKILLS_SRC = path.join(__dirname, "..", "skills");
const USAGE = `eWebCity Claude Skills

Usage: ewebcity-claude-skills [skill ...] [options]

Install all available skills, or only the names supplied.

Options:
  --project   Install in the current project's .claude/skills directory
  --force     Replace an existing skill and keep its previous version as a backup
  --dry-run   Validate and show the planned installation without changing files
  --list      List available skills without installing anything
  --help, -h  Show this help

Without --project, the destination is your home directory's .claude/skills.
Existing skills are preserved unless --force is supplied.
Backups are stored outside active skills, under .claude/ewebcity-backups.
`;

function parseArguments(args) {
  const options = { project: false, force: false, dryRun: false, list: false, help: false };
  const names = [];
  const flags = new Map([
    ["--project", "project"],
    ["--force", "force"],
    ["--dry-run", "dryRun"],
    ["--list", "list"],
    ["--help", "help"],
    ["-h", "help"],
  ]);
  let namesOnly = false;
  for (const arg of args) {
    if (!namesOnly && arg === "--") {
      namesOnly = true;
    } else if (!namesOnly && flags.has(arg)) {
      options[flags.get(arg)] = true;
    } else if (!namesOnly && arg.startsWith("-")) {
      throw new Error(`Unknown option: ${arg}. Run with --help for usage.`);
    } else {
      names.push(arg);
    }
  }
  if (options.list && names.length) throw new Error("Do not combine --list with skill names.");
  return { options, names: [...new Set(names)] };
}

function statIfPresent(target) {
  try {
    return fs.lstatSync(target);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

// Resolve the user's chosen home/project anchor once. Refuse symlinks anywhere
// below that anchor, including directories shared by multiple skill targets.
function checkDirectoryPath(anchor, target) {
  const relative = path.relative(anchor, target);
  if (path.isAbsolute(relative) || relative === ".." || relative.startsWith(`..${path.sep}`)) {
    throw new Error(`Destination is outside the chosen directory: ${target}`);
  }
  let current = anchor;
  for (const part of relative.split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    const stat = statIfPresent(current);
    if (!stat) continue;
    if (stat.isSymbolicLink()) throw new Error(`Refusing a symbolic link in the installation path: ${current}`);
    if (!stat.isDirectory()) throw new Error(`Expected a directory in the installation path: ${current}`);
  }
}

function excludeGeneratedFile(source) {
  const name = path.basename(source);
  return name === "__pycache__" || name === ".DS_Store" || /\.py[co]$/.test(name);
}

function checkSourceTree(source) {
  if (excludeGeneratedFile(source)) return;
  const stat = fs.lstatSync(source);
  if (stat.isSymbolicLink()) throw new Error(`Refusing a symbolic link in a packaged skill: ${source}`);
  if (stat.isDirectory()) {
    for (const entry of fs.readdirSync(source)) checkSourceTree(path.join(source, entry));
  } else if (!stat.isFile()) {
    throw new Error(`Unsupported file in a packaged skill: ${source}`);
  }
}

function availableSkills() {
  return fs.readdirSync(SKILLS_SRC, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && /^[a-z0-9][a-z0-9-]*$/.test(entry.name))
    .map((entry) => entry.name)
    .sort();
}

function preflight(anchor, names, options) {
  const claudeRoot = path.join(anchor, ".claude");
  const skillsRoot = path.join(claudeRoot, "skills");
  const stagingRoot = path.join(claudeRoot, "ewebcity-staging");
  const backupRoot = path.join(claudeRoot, "ewebcity-backups");
  checkDirectoryPath(anchor, skillsRoot);
  checkDirectoryPath(anchor, stagingRoot);
  const plans = names.map((name) => {
    const source = path.join(SKILLS_SRC, name);
    const destination = path.join(skillsRoot, name);
    const skillFile = statIfPresent(path.join(source, "SKILL.md"));
    if (!skillFile || !skillFile.isFile() || skillFile.isSymbolicLink()) {
      throw new Error(`The packaged skill has no regular SKILL.md file: ${name}`);
    }
    checkSourceTree(source);
    checkDirectoryPath(anchor, destination);
    const existing = statIfPresent(destination);
    if (existing && !options.force) {
      throw new Error(`Skill already exists: ${destination}. Use --force to replace it with a backup.`);
    }
    return { name, source, destination, existing };
  });
  if (plans.some((plan) => plan.existing)) checkDirectoryPath(anchor, backupRoot);
  return { plans, skillsRoot, stagingRoot, backupRoot };
}

function verifyDestinationsUnchanged(anchor, install) {
  checkDirectoryPath(anchor, install.skillsRoot);
  checkDirectoryPath(anchor, install.stagingRoot);
  if (install.plans.some((plan) => plan.existing)) checkDirectoryPath(anchor, install.backupRoot);
  for (const plan of install.plans) {
    checkDirectoryPath(anchor, plan.destination);
    const now = statIfPresent(plan.destination);
    if (Boolean(now) !== Boolean(plan.existing) ||
        (now && (now.dev !== plan.existing.dev || now.ino !== plan.existing.ino))) {
      throw new Error(`The destination changed during preparation; no replacement was attempted: ${plan.destination}`);
    }
  }
}

function installSkills(anchor, install) {
  const staged = [];
  fs.mkdirSync(install.stagingRoot, { recursive: true });
  try {
    // Prepare complete copies before replacing any active skill. Copying into a
    // fresh tree avoids following old nested links and removes stale files.
    for (const plan of install.plans) {
      const container = fs.mkdtempSync(path.join(install.stagingRoot, `${plan.name}-`));
      const stage = path.join(container, plan.name);
      staged.push({ ...plan, container, stage });
      fs.cpSync(plan.source, stage, {
        recursive: true,
        force: false,
        errorOnExist: true,
        dereference: false,
        filter: (source) => !excludeGeneratedFile(source),
      });
    }
    verifyDestinationsUnchanged(anchor, install);
    fs.mkdirSync(install.skillsRoot, { recursive: true });
    if (staged.some((plan) => plan.existing)) fs.mkdirSync(install.backupRoot, { recursive: true });

    for (const plan of staged) {
      checkDirectoryPath(anchor, plan.destination);
      checkDirectoryPath(anchor, install.stagingRoot);
      let backup = null;
      if (plan.existing) {
        checkDirectoryPath(anchor, install.backupRoot);
        const stamp = new Date().toISOString().replace(/[:.]/g, "-");
        const backupContainer = fs.mkdtempSync(path.join(install.backupRoot, `${plan.name}-${stamp}-`));
        backup = path.join(backupContainer, plan.name);
        fs.renameSync(plan.destination, backup);
      }
      try {
        fs.renameSync(plan.stage, plan.destination);
      } catch (error) {
        if (backup && !statIfPresent(plan.destination)) {
          try {
            fs.renameSync(backup, plan.destination);
          } catch (restoreError) {
            throw new Error(`Installation failed. The previous skill is preserved at ${backup}; restore it manually. ${restoreError.message}`);
          }
        }
        throw error;
      }
      console.log(`Installed ${plan.name} -> ${plan.destination}`);
      if (backup) console.log(`Backup: ${backup}`);
    }
  } finally {
    for (const plan of staged) {
      // Containers belong to this invocation and never contain active skills or backups.
      fs.rmSync(plan.container, { recursive: true, force: true });
    }
    try {
      fs.rmdirSync(install.stagingRoot);
    } catch (error) {
      if (error.code !== "ENOENT" && error.code !== "ENOTEMPTY") throw error;
    }
  }
}

function main() {
  const { options, names } = parseArguments(process.argv.slice(2));
  if (options.help) {
    console.log(USAGE);
    return;
  }
  const available = availableSkills();
  if (options.list) {
    console.log("Available eWebCity skills:\n");
    for (const name of available) {
      const skill = fs.readFileSync(path.join(SKILLS_SRC, name, "SKILL.md"), "utf8");
      const description = (skill.match(/^description:\s*(.+)$/m) || [])[1] || "";
      console.log(`  ${name}\n    ${description.slice(0, 140)}\n`);
    }
    return;
  }
  const requested = names.length ? names : available;
  if (!requested.length) throw new Error("No packaged skills are available.");
  const unknown = requested.filter((name) => !available.includes(name));
  if (unknown.length) throw new Error(`Unknown skill(s): ${unknown.join(", ")}. Run with --list to see available skills.`);

  const anchor = fs.realpathSync(options.project ? process.cwd() : os.homedir());
  const install = preflight(anchor, requested, options);
  if (options.dryRun) {
    for (const plan of install.plans) {
      console.log(`Would ${plan.existing ? "replace with backup" : "install"}: ${plan.name} -> ${plan.destination}`);
    }
    console.log("Dry run: no files changed.");
    return;
  }
  installSkills(anchor, install);
  console.log(`\nDone. ${options.project ? "Project" : "Personal"} skills saved for Claude Code.`);
}

try {
  main();
} catch (error) {
  console.error(`Installation failed: ${error.message}`);
  process.exitCode = 1;
}
