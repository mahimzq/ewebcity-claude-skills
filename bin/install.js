#!/usr/bin/env node
/**
 * eWebCity Claude Skills installer — eWebCity.co.uk
 *
 * Usage:
 *   npx ewebcity-claude-skills            Install all skills for the current user (~/.claude/skills)
 *   npx ewebcity-claude-skills --project  Install into the current project (./.claude/skills)
 *   npx ewebcity-claude-skills --list     List available skills
 *   npx ewebcity-claude-skills <name>     Install a single skill by name
 */

const fs = require("fs");
const path = require("path");
const os = require("os");

const SKILLS_SRC = path.join(__dirname, "..", "skills");
const args = process.argv.slice(2);

const flags = new Set(args.filter((a) => a.startsWith("--")));
const requested = args.filter((a) => !a.startsWith("--"));

const available = fs
  .readdirSync(SKILLS_SRC, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => d.name);

if (flags.has("--help") || flags.has("-h")) {
  console.log(fs.readFileSync(__filename, "utf8").split("*/")[0].replace("/**", ""));
  process.exit(0);
}

if (flags.has("--list")) {
  console.log("Available eWebCity skills:\n");
  for (const name of available) {
    const skillMd = fs.readFileSync(path.join(SKILLS_SRC, name, "SKILL.md"), "utf8");
    const desc = (skillMd.match(/^description:\s*(.+)$/m) || [])[1] || "";
    console.log(`  ${name}`);
    console.log(`    ${desc.slice(0, 100)}...\n`);
  }
  process.exit(0);
}

const destRoot = flags.has("--project")
  ? path.join(process.cwd(), ".claude", "skills")
  : path.join(os.homedir(), ".claude", "skills");

const toInstall = requested.length ? requested : available;

for (const name of toInstall) {
  if (!available.includes(name)) {
    console.error(`✗ Unknown skill: ${name}. Run with --list to see available skills.`);
    process.exitCode = 1;
    continue;
  }
  const src = path.join(SKILLS_SRC, name);
  const dest = path.join(destRoot, name);
  fs.mkdirSync(dest, { recursive: true });
  fs.cpSync(src, dest, { recursive: true });
  console.log(`✓ Installed ${name} → ${dest}`);
}

if (process.exitCode !== 1) {
  console.log(
    `\nDone. ${flags.has("--project") ? "Project" : "Personal"} skills installed.` +
      `\nClaude Code will pick them up automatically in your next session.` +
      `\n\nMaintained by eWebCity — https://eWebCity.co.uk`
  );
}
