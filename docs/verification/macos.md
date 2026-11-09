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

## Caveman retirement corrective verification

The 2026-11-09 Caveman review found that the live Mac repair had not run the
required native deployment gate. The corrective run used macOS 15.8.1,
Apple silicon (`aarch64`), the workstation role, no optional bundles, and
private synthetic homes containing spaces. No real-home apply, history import,
account activation, or model request was performed. The original ordering
omission remains part of the record; these results establish current coverage.

| Attempt | Cache | Result | Elapsed |
| --- | --- | --- | --- |
| [Initial](caveman-macos-2026-11-09-empty-cache.json) | empty | Both installations, preservation, pins, and discovery passed; agent discovery tests still expected a disabled skill | 829.226 s |
| [Recheck](caveman-macos-2026-11-09-recheck.json) | public packages only | Reached history; a Linux-only adapter test ran on macOS and the picker fixture raced background history completion | 357.540 s |
| [Final](caveman-macos-2026-11-09-final.json) | public packages only | Full native gate passed, 44 required behavior tests, zero skips | 363.517 s |

Each installation had a 900-second bound. The cache-assisted runs installed
into fresh homes and seeded only the verifier's allowlisted public caches,
without installed environments, launchers, or credentials. They do not claim
an empty-cache full-gate pass. Both failed reports are retained; their private
synthetic fixtures were removed after the successful run.

The final gate tested commit `751d354fe520e88ab2e7707e1af8386f36e80ac3` with
only the following uncommitted verification changes. Its working-source SHA-256
was `539a032dba02614368cd7907aef0f97299718d05f12cc44e6235460908319078`.
The evidence reports and this documentation were added after that run.

| Tested file | SHA-256 |
| --- | --- |
| `tests/native_linux.py` | `f1cc9bf402a53089d5cfd3d4d516dcf8d0585f8597bf60e4f376e92e4f6e5238` |
| `tests/test_agent_payload.py` | `6fe2b440174977f31f00c4cfebab0124dcb59d29ea7bc0ec477780729f58fc3d` |
| `tests/test_history_behavior.py` | `164fea000d08997188ca8a08ff663a6d24a25dc32eeb776e5643074fca04066d` |
| `tests/test_local_history_behavior.py` | `a653748e949f72af5b9963c6a759b1b2fae0b806e01617ed5ac324b8c970516a` |

Discovery expectations now derive from the existing disabled-skills policy
and verify that excluded skills remain absent. The Linux-only legacy storage
integration moved to `test_local_history_behavior.py`, required by the native
Linux gate; it is outside the Mac gate's applicable suite. The picker fixture
waits until its command is searchable before pressing Up/Ctrl-R, retaining the
original four-second UI deadline. Five repeated native picker checks passed.
The Linux integration itself was not executed on this Mac; 21 Linux-verifier
unit checks and five Mac-verifier unit checks passed.

The final report records 13 shell, 13 agent-payload, nine CodeGraph, and nine
shared-history tests, all passing without skips. These results cover the
Apple silicon workstation cell only; Intel and remote-compute native gates
were not rerun for this repair.
