# Completed host alignment — 2026-11-08

The actionable gaps are fixed within the confirmed scope: common defaults and already-present optional capabilities. The original [audit](README.md) remains the before snapshot. No notebook, Herdr, Caveman, Mihomo or Codex daemon restart was performed.

## Results

| Area | Verified after state |
| --- | --- |
| Common tools | All30 installed:24 exact and six newer accepted. Tailspin, less, Python/pip, Worktrunk and ty are available through managed commands. |
| Previously installed optional tools | All70 installed capabilities aligned:52 exact and18 newer accepted. Existing legacy commands and DuckDB's missing exposure were included; Firefox159 and DuckDB2.0 were preserved. |
| Optional capabilities left absent | doggo,fastfetch,git-cliff,jaq,ouch,tokei,xh, exactly as the scope decision requested. |
| Agents and managers | Eight agent/tool packages:three exact,five newer accepted. Allthree managers exact. Native Qoder1.1.82 verified. Existing agent processes were not restarted. |
| Command exposure |133 declared available aliases resolve correctly; the remaining seven belong to the absent optional capabilities. The obsolete uv ty launcher is retained outside PATH; its old package remains installed. |
| uutils | The existing migration removed obsolete system-name/resource exposures and retained only `coreutils`; package contents and unrelated/custom registry entries were preserved. |
| Skills | All91 skills and709 canonical resource files match reviewed source bytes/modes across shared, Claude and MiniMax adapters. Missing worktrunk/wt-switch-create added;28 Pi duplicates moved to recovery storage. |
| Qoder discovery | Native model-free discovery finds all91 catalog names exactly once, with no duplicate diagnostics. Qoder's shared-root aliases need no change. |
| Agent settings | All14 targets parse. All13 enforced fields match; three updater controls fixed. Device model/provider settings and unrelated plugin values preserved. All37 disabled names remain excluded, Serena remains disabled. |
| Worktrunk | Official CLI integrations installed for Claude,Codex,OpenCode,Pi; shared skills and Bash/Zsh/Nu integration prepared. |
| Shell startup | Current managed Nu modules and six generated shell/history resources installed. Legacy Nu environment preserved as a private hook with standalone JOEY/JSHELL bootstrap. Extra btm/curl imports retained. POSIX device environment preserved with a rendered managed block; Bash receives the additive Worktrunk hook. |
| Persistent files/helpers | All54 home links and allseven legacy-apply targets pass. New Zsh/logout links persist; source-matched nu-login/codex-herdr now have their required environment prerequisites. |
| Editor/history/defaults | Missing Atuin/Git defaults filled; VS Code's managed tool/proxy references and default fields aligned; missing global credential-exclusion patterns added. Existing Git identities, credential helpers, history/auth state, and unrelated settings preserved. |
| Previously reported byte drift | Cargo and Pixi values already agree semantically; uv differs only in equivalent URL spelling. Zellij's shell resolves to the same managed launcher. Existing Bash/profile customizations stay device-owned. |
| Source hygiene | Chezmoi inventory now has60 intended files and no bytecode artifacts. Existing generated files were excluded, not deleted. |
| Runtime | Final health check reports `host stack ready`; original Mihomo7649,Herdr8596,Caveman191413,Codex daemon3086251 remain present. Offline Graphify cache/settings codec remain available. |

Detailed tool/alias results: [tools-after.md](tools-after.md). Fresh sanitized evidence: [tools](evidence/tools-after.json), [settings](evidence/settings-after.json), [skills](evidence/skills-after.json), [Qoder](evidence/qoder-after.json), [runtime](evidence/runtime-after.json).

## Verification

- Broad deployment gate:427 tests run,74 skipped; passed. The final Bash-block/preservation refinement was followed by six focused migration tests, all passed.
- Both simulated T9K/Linux profile applications passed. Shell/history generation, standalone Nu with the preserved legacy environment, and native Nu startup passed.
- Native interactive Bash in a temporary PTY reports the Worktrunk function and managed Python/ty paths. Live shell migration reapplication changed zero files before the final additive Bash hook; managed-block preservation and idempotence are covered by the focused tests.
- All91 source-resource manifests equal allthree installed adapters. Native Qoder discovery validates91/91 names without model requests.
- All54 links, allseven legacy executable/config targets, global integration conformity and live dependency health passed. No repository indexing, history import, login-shell change or system service operation was performed.

The existing services remain running. Restart once unrelated active work has finished, then run `link-home.sh` and wait for `host stack ready` before remote laptop attachment. Actual notebook restart, fresh GPU allocation, remote-laptop forwarding, GUI/GPU execution and model/API calls were not exercised.

## Preservation and rollback

Private recovery copies are under `/t9k/mnt/.local/state/dotfiles/host-alignment/20261108-162631` for package registry, replaced skill trees, Pi duplicates, manager/old-launcher files, plugin configuration and preference changes. Shell recovery journals are under `~/.local/state/dotfiles/host-alignment/shell.*/restore.json`; updater/integration journals remain under `disabled-integrations/files.*/restore.tsv`. The uutils merger retains its private `pixi-global.toml.before-coreutils-namespacing.bak`.

Rollback is an explicit separate operation: review the journal, restore only that task's files/modes, and reconcile the affected package registry. `NEW` entries must be reviewed before removal. Source policies would otherwise reassert current settings at the next link-home. No recovery contents or credential values are committed here.

Intentional retained boundaries: the trusted legacy symlink layout and longstanding proxy supervisor remain; ordinary public bootstrap and history/shell preparation still reject symlink homes. Use the explicit rehearsed adapter for this tree. Foreign-shell helper scripts, unselected optional capabilities and setup-on-use account/project facilities are outside the requested alignment scope. Device overrides are preserved rather than replaced solely to make hashes equal.

Documentation and source fixes are staged for review; no new commit or push was requested in this alignment turn.
