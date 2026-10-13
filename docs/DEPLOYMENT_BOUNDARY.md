# Public deployment boundary

`bash bootstrap.sh --help` documents selectors and the CLI. The implementation
uses system Bash 3.2-compatible syntax so a fresh macOS host does not require
Python, Node, Bun, or managed Bash before bootstrap can start. Native Windows
gets a PowerShell entry point in ticket 11.

Planning supports the complete accepted platform/role/architecture matrix but
is selection evidence only. The ticket-01 actual execution checks cover Linux
workstation and remote compute file application; foreign native execution and
foreign execution is separate downstream work. Ticket 02 adds actual Linux
common-tool installation and separately records foreign package resolution.

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

At this integration midpoint, the agent adapter deliberately fails as pending
ticket 04. A successful common stage is not full bootstrap completion.

## Common tools and registry ownership

`deployment/common-tools.tsv` is the canonical common catalog. Each row names
an environment, exact package specifications, explicit exposed commands, and
`all` or `unix` conda targets. `deployment/common.sh` reads that catalog for
plan metadata; the chezmoi template renders the same rows into the desired
`~/.config/dotfiles/pixi-global.toml`, including the selected native subdir.
Extend optional inventories through separate desired manifests or merge their
selected entries into that desired manifest before the common installer runs.

`deployment/managers.sh` provisions checksum-verified upstream Pixi and
Chezmoi assets. Chezmoi's one intended owner is the bootstrap binary under
`~/.local/bin`; it is absent from the Pixi catalog. `DOTFILES_PIXI_BIN` can
explicitly supply Pixi at its required pin for isolated boundary checks.
`--apply-only` provisions/uses Chezmoi without provisioning Pixi.

The common installer uses `pixi exec` with the catalog's exact Python pin to
run `deployment/merge_pixi.py`, then runs `pixi global sync`. The merge keeps
unrelated environments and extra dependency/exposure entries/channels. An
exposure collision across environments fails before writing the registry.
The source state never applies over Pixi or Bun runtime registries. Pixi global
has no lockfile: exact direct versions leave build/transitive solver drift;
workspace resolution locks used for verification are evidence, not global
installation locks. See [Pixi's global manifest](https://pixi.prefix.dev/latest/global_tools/manifest/)
and [its CI lockfile limitation](https://pixi.prefix.dev/latest/integration/ci/github_actions/).

Rustup is a checksum-verified pinned common manager installed with
`--default-toolchain none --no-modify-path`. It preserves existing toolchains;
a fresh common install does not claim usable Cargo/Rust compiler tooling.
Those toolchains belong to the developer inventory or explicit on-use setup.
Required errors identify their manager, merge, sync, Rustup, or exposure step.

Use separate feature modules for the later shell, agent, and bundle adapters;
their top-level functions remain in `installers.sh`. Agent selection must
preserve local Bun state. Shell preparation must leave account activation,
history import, and repository indexing to their explicit boundaries.

`deployment/shell.sh` calls the managed `dotfiles-shell-prepare` command during
required shell preparation. That command validates new Nu prompt/completion
resources before replacing working files and rejects symlinked startup state.
The shared shell model and actual interactive/non-interactive Nu distinction
are documented in [shared shell settings](SHARED_SHELL_SETTINGS.md).

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

`DOTFILES_TEST_INSTALL=1 python3 -m unittest discover -s tests -p test_common_install.py -v`
runs real Linux network installation and harmless CLI diagnostics twice. Its
PATH contains only selected managed roots and system prerequisites. Pip and uv
must discover TUNA configuration, and an unrelated declared Pixi environment
must remain exposed after reapplication. An optional retained test home uses
`DOTFILES_TEST_INSTALL_HOME=/tmp/...`; downstream checks can use its binaries
read-only while writing to their own separate home/state roots. Do not copy or
share writable installed prefixes. Native macOS/Windows/ARM and shell behavior
remain separate checks; package-resolution success does not establish them.

A designated home whose pre-existing state directories are symlinks is rejected
before state creation. `/etc` and account login-shell changes are absent from
this boundary. Provider environment values explicitly supplied by the device
owner are rendered only into the selected target; existing real-home auth files
are never loaded by bootstrap.

Chezmoi references: [global path flags](https://www.chezmoi.io/reference/command-line-flags/global/)
and [initialization behavior](https://www.chezmoi.io/reference/commands/init/).
