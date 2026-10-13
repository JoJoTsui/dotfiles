# Public deployment boundary

`bash bootstrap.sh --help` documents selectors and the CLI. The implementation
uses system Bash 3.2-compatible syntax so a fresh macOS host does not require
Python, Node, Bun, or managed Bash before bootstrap can start. Native Windows
gets a PowerShell entry point in ticket 11.

Planning supports the complete accepted platform/role/architecture matrix but
is selection evidence only. The ticket-01 actual execution checks cover Linux
workstation and remote compute file application; foreign native execution and
tool/agent installers are separate downstream tickets.

## Extending installers

`deployment/profile.sh` resolves canonical `DEPLOY_PLATFORM`, `DEPLOY_ROLE`,
`DEPLOY_ARCH`, `DEPLOY_PROFILE`, and compatibility `DEPLOY_CLASS`. Public
flags override environment selections. Preset/component conflicts at the
explicit-flag tier fail. `DOTFILES_CLASS=t9k` remains a Linux remote compute
compatibility input. Detected platform never supplies a compute role.

`deployment/installers.sh` is sourced after selection. It may declare plan
metadata (`DEPLOY_TOOLS`, `DEPLOY_ACTIONS`) and define the following functions;
sourcing it must never change files, call installers, authenticate, or index:

- `install_managers`: provision managers under the target home. Set
  `DEPLOY_CHEZMOI` to the actual chezmoi executable. A deliberate
  `DOTFILES_CHEZMOI_BIN` override can supply an existing binary for isolated
  validation; it changes neither config nor destination roots.
- `install_common`: install and expose selected common tools and bundles.
- `install_agents`: install selected coding agents and default CodeGraph.
- `prepare_shell`: create user-scoped startup artifacts after managed tools
  exist. Account activation/import/indexing remain explicit separate actions.

The boundary runs these stages in order, applying source between managers and
common tools. It exports HOME, XDG roots, Pixi/Bun/Cargo/Rustup roots, uv/pip/npm
cache roots, Atuin directories, and agent config directories under the selected
home. Required command failures propagate with their step and nonzero status.
No adapter may silently turn a required failure into a completion message.

`--apply-only` still provisions or uses chezmoi, applies the working source, and
bypasses common-tool/agent/startup installation. `--plan` does neither and emits
JSON with profile selectors, source/home, tools/actions, state roots, and target
settings. Secret values never enter this output. Extend this metadata when a
new installer becomes available; do not invoke installers to compute a plan.

At this integration midpoint, common/agent adapters deliberately fail as
pending tickets 02/04. They are not successful no-ops or released installers.

## Isolated acceptance checks

Run `DOTFILES_TEST_CHEZMOI=/path/to/chezmoi python3 -m unittest discover -s tests -v`.
The standard-library test runner is a development dependency, not a bootstrap
prerequisite. Actual file-application checks require a real chezmoi binary;
the suite reports those checks as skipped if none is supplied or on PATH.

The tests create disposable homes and a temporary working-source copy. They
clear inherited credential/manager variables, guard external network/account
commands, and use a synthetic marker to prove uncommitted source is applied.
Linux role targets are reapplied and compared (excluding chezmoi operation
state), checked for regular executable files, credential placeholders, and
bookkeeping exclusion. Plans cover all 14 supported profile/architecture
combinations. Controlled failing executables test only failure propagation;
they do not establish successful package/native execution.

A designated home whose pre-existing state directories are symlinks is rejected
before state creation. `/etc` and account login-shell changes are absent from
this boundary. Provider environment values explicitly supplied by the device
owner are rendered only into the selected target; existing real-home auth files
are never loaded by bootstrap.

Chezmoi references: [global path flags](https://www.chezmoi.io/reference/command-line-flags/global/)
and [initialization behavior](https://www.chezmoi.io/reference/commands/init/).
