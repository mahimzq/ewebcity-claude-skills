# Use eWebCity across coding agents and chat applications

**Platform documentation checked: 12 November 2026.** This guide separates native skill discovery, local file installation and portable chat use. The installer has automated filesystem tests; discovery, invocation and tool execution inside the actual vendor applications have **not** been tested in this environment.

The native bundle uses `SKILL.md` with `name` and `description`, plus its references, scripts and assets. A supported host can load the instructions and choose relevant resources. File placement does not authenticate an account, enable tools or prove that an agent used the skill.

## Native target matrix

Each listed root contains `ewebcity-seo-optimizer/SKILL.md` and the rest of that skill's folder. Project paths are relative to the directory where you run the installer; `~` means the user's home directory.

| Product or host | Installer target | Project root with `--project` | Personal root without `--project` | Discovery and invocation | Primary documentation |
| --- | --- | --- | --- | --- | --- |
| Claude Code | `claude` (default) | `.claude/skills` | `~/.claude/skills` | Use `/ewebcity-seo-optimizer`; relevant requests can also trigger the skill. | [Claude Code skills](https://code.claude.com/docs/en/skills) |
| Codex CLI or IDE extension | `codex` | `.agents/skills` | `~/.agents/skills` | Inspect `/skills`, then mention `$ewebcity-seo-optimizer`. | [OpenAI skills](https://learn.chatgpt.com/docs/build-skills) |
| Cursor Agent | `cursor` | `.cursor/skills` | `~/.cursor/skills` | Start a fresh session; type `/` and select the skill. | [Cursor skills](https://cursor.com/docs/skills) |
| GitHub Copilot in VS Code | `copilot` or `vscode` | `.github/skills` | `~/.copilot/skills` | Select the Copilot harness/agent; type `/` and select the skill. | [VS Code agent skills](https://code.visualstudio.com/docs/agent-customization/agent-skills) |
| Google Antigravity App or CLI | `antigravity` | `.agents/skills` | `~/.gemini/config/skills` | App: `/ewebcity-seo-optimizer`; CLI: inspect `/skills` and request the skill. | [Skills](https://antigravity.google/docs/skills), [customisation discovery](https://antigravity.google/docs/customization-discovery) |

VS Code is the editor; the active agent determines its skill location. For the Codex or Claude agent inside an editor, select that agent's target rather than assuming the `vscode` alias applies to every extension. The alias deliberately means **Copilot**. [VS Code documents these harness-specific locations](https://code.visualstudio.com/docs/agent-customization/agent-skills).

GitHub Copilot also documents native skills for its CLI and other surfaces. Its CLI can reload skills with `/skills reload` and inspect this one with `/skills info ewebcity-seo-optimizer`. A local installation does not automatically make a personal skill available in a cloud session; use the relevant surface's setup. [GitHub skill locations](https://docs.github.com/en/copilot/concepts/customizations/agent-skills), [CLI setup](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills).

### Shared locations and duplicate names

Codex and Antigravity use the same project `.agents/skills` root. Install once there. Installing the same skill again through the other target requires `--force`; it updates that shared copy and keeps its previous version in the shared backup directory.

Cursor and Copilot also recognise `.agents/skills` in documented configurations. Check which copy your host loaded before adding another copy under `.cursor` or `.github`. Different hosts handle duplicate names differently; this installer neither deletes other targets' copies nor promises automatic deduplication. [Cursor locations](https://cursor.com/docs/skills), [Copilot locations](https://docs.github.com/en/copilot/concepts/customizations/agent-skills).

Current Antigravity documentation recommends `.agents` for new projects and `~/.gemini/config/skills` for personal skills shared by the App and CLI. Older `.agent` layouts and CLI-only directories are not this installer's default. [Antigravity discovery](https://antigravity.google/docs/customization-discovery).

## Install from this checkout

The installer requires Node.js 18 or later. Run project installs from the project you want the agent to work on; the installer uses the **current directory**, not a guessed repository root. Replace the example absolute path with your actual checkout path.

```bash
cd /path/to/your-website

# Choose one target: claude, codex, cursor, copilot or antigravity.
node /path/to/ewebcity-claude-skills/bin/install.js \
  ewebcity-seo-optimizer --target cursor --project --dry-run

node /path/to/ewebcity-claude-skills/bin/install.js \
  ewebcity-seo-optimizer --target cursor --project
```

Remove `--project` to use that target's personal location. Existing commands without `--target` retain their Claude Code destination. Both `--target cursor` and `--target=cursor` work. Supply one target per invocation.

```bash
# Read-only help and skill inventory.
node /path/to/ewebcity-claude-skills/bin/install.js --help
node /path/to/ewebcity-claude-skills/bin/install.js --list
```

Providing a skill name installs only that skill. Omitting all skill names installs every skill included in the package. Unknown options, targets and skill names fail before installation. The installer does not change vendor settings or honour custom vendor skill-directory overrides; use a host-supported manual location if your organisation changes those defaults.

### Updates, backups and dry runs

An existing destination is preserved unless you explicitly pass `--force`. A forced update replaces the whole skill tree, removes stale active files and moves the previous tree to a backup. Reapply intentional local customisations from that backup after reviewing the new version.

```bash
node /path/to/ewebcity-claude-skills/bin/install.js \
  ewebcity-seo-optimizer --target cursor --project --force --dry-run

node /path/to/ewebcity-claude-skills/bin/install.js \
  ewebcity-seo-optimizer --target cursor --project --force
```

Backups are outside the active `skills` directory, under its sibling `ewebcity-backups`:

```text
.cursor/ewebcity-backups/<skill>-<UTC timestamp>-<unique suffix>/<skill>/
.agents/ewebcity-backups/<skill>-<UTC timestamp>-<unique suffix>/<skill>/
```

Personal Antigravity backups, for example, live under `~/.gemini/config/ewebcity-backups`. Portable backups live under `./ewebcity-portable/ewebcity-backups`. The command prints the exact backup path. To restore, close sessions using the skill, preserve the current copy elsewhere if needed, then move the chosen backup's entire skill directory back to its original destination.

All requested skill names, source trees and relevant destination paths are checked before copying. Symbolic links in destination ancestry or at the target are rejected, even when a host itself permits them. Complete copies are staged before active replacements. A late filesystem failure can leave earlier skills in a multi-skill invocation updated; the operation is not a transaction across the whole batch. A dry run creates no directories or backups.

## ChatGPT, Claude chat and DeepSeek

Browser chat and a coding agent have different installation and execution contexts. These exports let you supply the workflow without claiming that a local directory has registered it in a web account.

| Chat surface | Route provided here | Native account installation |
| --- | --- | --- |
| ChatGPT | `--target chatgpt` exports a portable bundle. Paste/import its prompt and provide the required resources. | OpenAI documents native skills and plugin distribution; use the supported ChatGPT creator/plugin workflow when available in your workspace. This installer does not register it. |
| Claude in the browser or Cowork | `--target portable` exports the same bundle for manual use. | Claude account skills are managed separately from local Claude Code folders. This installer does not enable an account skill. |
| DeepSeek chat or a model hosted elsewhere | `--target deepseek` exports a portable bundle. | No DeepSeek account registration or filesystem discovery integration is implemented here. Use the host's supported prompt/file workflow. |

OpenAI describes standalone skills for its desktop app, Codex CLI and IDE extension, and plugins for wider ChatGPT distribution. Where available, `@skill-creator` is its supported creator workflow and `@` selects an installed skill. A successful `--target chatgpt` export alone does not complete that registration. [OpenAI skill creation and distribution](https://learn.chatgpt.com/docs/build-skills).

Claude's local `~/.claude/skills` folder does not automatically configure Cowork or cloud sessions. Manage account-enabled skills through the product's supported customisation interface, or use the portable prompt with supplied files. [Claude account and local skill scopes](https://code.claude.com/docs/en/skills).

DeepSeek's Chat Completions API accepts system and user messages, so an application can pass these instructions with the user's task. That application's tool implementation must supply any filesystem, browsing or execution capabilities; the prompt does not create them. This repository does not ship a DeepSeek API client. [DeepSeek message format](https://api-docs.deepseek.com/api/create-chat-completion/).

### Create and use a portable bundle

Run this from a directory where you want the export. Portable targets always use the current directory, with or without `--project`.

```bash
node /path/to/ewebcity-claude-skills/bin/install.js \
  ewebcity-seo-optimizer --target portable
```

`--target chatgpt` and `--target deepseek` are aliases for this same operation. Each exports to:

```text
./ewebcity-portable/skills/ewebcity-seo-optimizer/
```

The export keeps the complete native bundle and adds `PORTABLE_PROMPT.md`. That prompt includes the optional `assets/portable-prompt.md` bootstrap, the skill instructions and a compact index of reference Markdown. The full reference corpus and scripts remain separate files, keeping the initial prompt manageable.

1. Start a conversation in the chosen product and paste or attach `PORTABLE_PROMPT.md` using the available interface.
2. Attach relevant references and actual input files, or provide filesystem access to the exported bundle. A reference index does not give the model those files' contents.
3. State the real site/repository, objective and evidence available. Let the agent declare which tools it can use before treating any checks as measured.
4. If code execution is unavailable, run the bundled auditor locally and provide its JSON/Markdown output. Use the HTML report directly in a browser.
5. Keep uncollected checks marked **not checked**. Supplying a URL or a prompt does not establish that the model fetched the page.

Upload, context and tool limits depend on the chosen product. If the entire prompt or bundle does not fit, provide `SKILL.md` and the references relevant to the current task separately, and disclose the missing inputs. When a model is used inside another coding host, choose the host's supported native target; a model name alone does not identify a skill directory.

## Capability requirements and a practical verification

| Work requested | Capability required | Honest fallback |
| --- | --- | --- |
| Review provided source or evidence | Access to the actual HTML, repository files or report | Explain recommendations from the supplied material and identify missing inputs. |
| Run the bundled source auditor | Filesystem access and Python 3.10+; keep the helper modules beside `audit.py` | Run it locally and upload the outputs. No third-party Python packages are required. |
| Crawl an authorised public site | Auditor runtime plus permitted DNS/HTTP access | Audit supplied HTML; live HTTP and robots observations stay unverified. |
| Inspect rendered pages or measure browser performance | An available browser/performance tool and real observations | Separate source observations from unmeasured rendering and performance. |
| Review private search/analytics data | An authorised connection or a supplied provider export | Mark provider metrics and index state not checked. |

After native installation, start a fresh session in the intended host and workspace. Confirm the skill's name and source location in its selector/customisation panel, then invoke it explicitly with a small supplied HTML fixture. Ask it to use the actual bundled script if it has execution access, retain the generated evidence and explain the unmeasured checks. Confirm implicit selection separately if you want to rely on it. VS Code's [verification guidance](https://code.visualstudio.com/docs/agent-customization/agent-skills) similarly distinguishes discovery from actual use.

Example request after selecting the skill:

> Audit the attached saved HTML for metadata, canonical and indexing directives. Use the bundled source auditor if execution is available, produce the available report files, and explain coverage and checks that were not measured. Do not infer live HTTP responses from this saved file.

Installer tests cover the documented target mapping, destination isolation, shared Codex/Antigravity locations, unknown arguments, dry runs, backups, stale-file removal, symbolic-link rejection and portable bundle contents. They use temporary directories and do not install into real personal accounts. These tests validate the installer, not vendor UI behaviour or model quality.

```bash
node --test tests/installer.test.js
```

Recheck the linked primary documentation when upgrading host applications. Supported locations, product surfaces and workspace policies can change independently of this repository.
