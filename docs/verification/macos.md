# macOS verification

Ticket09 implements native discovery and runtime verification. The current
execution host is Linux x86-64; no macOS installer or binary was executed here.

| Target and role | Isolated plan/render/reapply | Native execution |
| --- | --- | --- |
| macOS Intel workstation | passed | pending CI |
| macOS Intel remote compute | passed | pending CI |
| macOS Apple silicon workstation | passed | pending CI |
| macOS Apple silicon remote compute | passed | pending CI |

Local public-boundary checks established canonical regular copies at native
Nu/pip paths, early source/destination symlink rejection, unrelated state/history/
credential preservation, role polling, exact desired dependencies, idempotent
application, and remote VS Code platform keys with literal JSON escaping.
The existing common gate already resolved Conda requirements for both macOS
targets; this ticket leaves those pins unchanged.

Real Linux Nu executed copied macOS resources with an explicit config directory,
including generated Starship, Pixi completions, and Atuin hooks. This establishes
copied syntax/resources, rather than ordinary native macOS discovery. The native
gate starts Nu without XDG/config overrides and checks native config/autoload
paths and effective values; it also checks ordinary pip and uv TUNA discovery.

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
Foreign execution fails with `native_execution: false` and `status: unavailable`.

The final public-boundary gate passed all 14 checks in 25.942 seconds, including
both legacy copy-mode/idempotent applies, the complete profile planning matrix,
failure boundaries, and actual exclusion of the newly committed workflow from
macOS source application.
