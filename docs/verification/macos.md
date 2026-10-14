# macOS verification

Ticket09 implements native discovery and runtime verification. Native macOS
runners have now executed: workflow run
[38524061897](https://github.com/JoJoTsui/dotfiles/actions/runs/38524061897) at
commit `81857d6`, 2026-10-14. Each cell uploads only a JSON result report.

| Target and role | Isolated plan/render/reapply | Native execution |
| --- | --- | --- |
| macOS Intel workstation | passed | passed (427.872s) |
| macOS Intel remote compute | passed | passed (566.523s) |
| macOS Apple silicon workstation | passed | passed (211.753s) |
| macOS Apple silicon remote compute | passed | passed (292.463s) |

All four cells report `status: passed` and `native_execution: true`. Each passes
the same checks: native runtime and architecture, profile detection, two default
installations, pinned commands and pending history, ordinary native configuration
discovery, and native shell, instruction, CodeGraph and encrypted-history
behavior.

Local public-boundary checks established canonical regular copies at native
Nu/pip paths, early source/destination symlink rejection, unrelated state/history/
credential preservation, role polling, exact desired dependencies, idempotent
application, and remote VS Code platform keys with literal JSON escaping.
The existing common gate already resolved Conda requirements for both macOS
targets; this ticket leaves those pins unchanged.

Real Linux Nu executed copied macOS resources with an explicit config directory,
including generated Starship, Pixi completions, and Atuin hooks. This established
copied syntax/resources, rather than ordinary native macOS discovery. The native
gate has since started Nu without XDG/config overrides and checked native
config/autoload paths, effective values, and ordinary pip and uv TUNA discovery.

With `DOTFILES_TEST_PLATFORM=macos` and remote compute selected, 22 unaffected
shell/history/agent cases passed. The initial 37-case run exposed two Kimi
fixture failures: the current compute host had exhausted inotify watchers, while
minimal client environments bypassed the canonical remote polling setting.
After loading rendered `.env_core` and exposing the declared CodeGraph command,
all 15 affected payload/client/MCP cases passed in 71.071 seconds with no skips.
The shared fixture uses canonical values rather than duplicated role defaults.
No system watcher limit or live-host setting was changed.

The seven focused macOS cases passed across their relevant runs, including the
four architecture/role render combinations, corrected actual Nu REPL startup,
symlink guards, and native-verifier refusal on Linux. YAML parsing, Bash syntax,
Python compilation and ShellCheck error checks passed. Native CI runs
`tests/native_macos.py` per architecture/role and uploads only a result report.
An additional `desktop` job runs the same gate with `--bundles desktop` and
passed at commit `b64fedb` in run
[38566605510](https://github.com/JoJoTsui/dotfiles/actions/runs/38566605510),
covering Apple silicon workstation only; the Intel and role cells are not
claimed by it.
Foreign execution fails with `native_execution: false` and `status: unavailable`
rather than a pass.

The final public-boundary gate passed all 14 checks in 25.942 seconds, including
both legacy copy-mode/idempotent applies, the complete profile planning matrix,
failure boundaries, and actual exclusion of the newly committed workflow from
macOS source application.
