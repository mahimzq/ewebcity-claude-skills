#!/usr/bin/env node
"use strict";

const path = require("node:path");
const { spawnSync } = require("node:child_process");

const script = path.join(__dirname, "..", "skills", "ewebcity-seo-optimizer", "scripts", "audit.py");
const configured = process.env.EWEBCITY_PYTHON;
const candidates = configured ? [configured] : process.platform === "win32" ? ["python", "python3"] : ["python3"];

let result;
for (const executable of candidates) {
  result = spawnSync(executable, ["-B", script, ...process.argv.slice(2)], {
    stdio: "inherit",
    shell: false,
  });
  if (!result.error || result.error.code !== "ENOENT") break;
}

if (result.error) {
  console.error("Unable to start the SEO audit. Python 3.10+ is required. Set EWEBCITY_PYTHON to the Python executable path if it is not named python3.");
  console.error(result.error.code || result.error.message);
  process.exitCode = 1;
} else if (result.signal) {
  console.error(`Audit stopped by ${result.signal}.`);
  process.exitCode = result.signal === "SIGINT" ? 130 : 1;
} else {
  process.exitCode = result.status === null ? 1 : result.status;
}
