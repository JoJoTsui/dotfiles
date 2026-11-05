# macOS deployment

The macOS profiles reuse the common package catalog, frozen Bun projects, shared
shell values, agent payload/settings adapters, and history setup. The supported
baseline is macOS 13 or newer, on Intel or Apple silicon. Bootstrap runs with
system Bash 3.2 and installs into user-scoped roots.

macOS runs **Zsh**, not Bash: the profile applies no Bash startup file, installs
no managed Bash runtime, and manages `~/.zprofile` as the Zsh login file.
`~/.zprofile` matters because Zsh never reads `~/.profile`: `/etc/zprofile`
runs `path_helper`, which rewrites PATH after `~/.zshenv` has set it, so the
login file re-applies the managed tool paths.

From a source checkout:

```bash
/bin/bash bootstrap.sh --platform macos --role workstation --plan
/bin/bash bootstrap.sh --role workstation
# For a Mac used for remote computation:
/bin/bash bootstrap.sh --role remote-compute
```

Darwin and its architecture are detected automatically. Explicit platform,
architecture, and profile flags also support foreign planning/rendering. Both
roles install all seven agents (six Bun-managed plus native Qoder) and CodeGraph
by default. Optional bundles retain
their target restrictions; the desktop bundle needs macOS 14.2 or newer. The
[common package evidence](verification/common-tools.md) records macOS solves
and the global-Pixi lock limitation.

## Native discovery

`deployment/macos-targets.tsv` maps rendered canonical files into native paths.
Bootstrap copies them after every source application, including `--apply-only`,
and refreshes generated startup resources after shell/history preparation.
Copies retain permissions and remain regular files. Owned source/destination
paths reject symlinks before source application; unrelated files, native history,
skills, and separate client credentials survive.

| Tool | Canonical source | Ordinary macOS discovery |
| --- | --- | --- |
| Nu startup and adjacent modules | `~/.config/nushell` | `~/Library/Application Support/nushell` |
| Nu prompt, Pixi completions, Atuin hooks | `~/.local/share/nushell/vendor/autoload` | `~/Library/Application Support/nushell/autoload` |
| pip TUNA config | `~/.config/pip/pip.conf` | `~/Library/Application Support/pip/pip.conf` |
| uv TUNA config | `~/.config/uv/uv.toml` | `~/.config/uv/uv.toml` |

Nu resolves startup directories before reading `env.nu`. Native copies let a
direct `nu` launch initialize managed values without inherited XDG or legacy
variables. A Nu launched from a managed shell inherits canonical XDG roots and
reads the same values. Nonempty device environment overrides retain precedence.
See [Nu startup paths](https://www.nushell.sh/book/configuration.html),
[uv storage](https://docs.astral.sh/uv/reference/storage/), and
[pip configuration](https://pip.pypa.io/en/stable/topics/configuration/).

`nu-login` prefers Nu for interactive managed terminals and retains Bash for
scripts and agent subprocesses. A terminal application can select
`~/.local/bin/nu-login` as its startup command. Bootstrap leaves account shell
selection unchanged by default; `--login-shell` opts in to registering the
launcher and selecting it with `chsh`. `--system-config` separately adds the
portable Bash defaults to `/etc/bashrc`, preserving a first-run backup.
Remote VS Code Machine settings emit `osx` keys, managed
micromamba paths, and selectable Bash/Nu profiles; Bash retains the secondary
shell guard for Claude. Rendering that payload does not execute VS Code Server.

History hooks deploy by default and report pending activation on a fresh device.
Use [explicit first-device/join setup](SHARED_HISTORY.md) for encrypted sync and
optional native-history import. Skill prerequisites remain on use. Installing
and registering CodeGraph leaves project indexing explicit.

## Installer tier and the terminal

macOS resolves common command groups before the Pixi merge. It adopts a
compatible device command group, then tries Homebrew, then the exact Pixi
fallback pins. `deployment/installer-tools.tsv` declares formula candidates and
minimum versions for all macOS common groups, plus the Ghostty cask selected
by `desktop`. An unavailable or incompatible formula uses Pixi. Homebrew is
adopted from the device.

Regular launchers under `~/.local/bin` expose the selected common provider.
Shell preparation, history, Micromamba, completions and agent installation use
these paths. Bun and Node accept the catalog floors on macOS. Existing Pixi
entries retain device aliases. A source-only upgrade keeps using Pixi until the
common launchers exist.

The Ghostty configuration is a managed file at
`~/.config/ghostty/config.ghostty`, the only path Ghostty reads. It sets the
Catppuccin Mocha theme, a font size, and the managed `nu-login` shell, and it
includes `~/.config/ghostty/config.local.ghostty`, which the deployment creates
once and never overwrites, so device tweaks stay out of the managed file.

A cask install writes an application bundle into `/Applications`, which is
outside the home. The tier therefore installs only on the real account home: a
simulated deployment may adopt installed commands but performs no Homebrew
installation. Accepted providers and observed versions are recorded in
`$XDG_STATE_HOME/dotfiles/installer-tools.lock.tsv`. See the
[installer order](adr/0008-installer-order.md).

## Native verification

### Existing-device verification and application

A full default deployment includes common tools, all selected coding agents,
CodeGraph, shared shell settings, instructions, and skills. Optional bundles,
account activation, history import, and system/login-shell changes remain
separate opt-ins. Real-home application requires explicit user authorization
and both verification layers below before it starts.

1. Pass the fresh native installation gate, including reapplication,
   preservation, ordinary configuration discovery, and every required behavior
   suite without skips. Record the source revision and any uncommitted changes.
   A cache-assisted run or existing-device adoption is a separate result from
   an empty-cache installation. Use a bounded installation timeout and record
   failed attempts without promoting them to passes.
2. Rehearse against a private copy of the existing device's managed settings.
   Preserve credentials, providers, trust, unrelated instructions and skills,
   shell integrations, and terminal preferences. Report changed setting paths
   without exposing their values. Rehearse backed-up replacement of conflicting
   launcher/skill symlinks while retaining the bootstrap's symlink guards.
3. When existing Atuin stores come from a different release, use SQLite backup
   snapshots that include committed WAL contents. Verify the pinned runtime's
   migration/schema compatibility and isolated read/write behavior against those
   snapshots before exposing it to live history. Keep hosted sync disabled for
   the rehearsal; account activation and history import remain explicit actions.
4. Preserve the active client transport. A gateway configuration with no semantic
   changes must retain its original bytes and modification time, avoiding a
   restart caused only by serialization. A genuine required route change is a
   separate interruption decision.
5. After both layers pass, create a protected backup of the actual affected
   configuration and symlinks, recheck for device drift, and run the full public
   bootstrap on the authorized account. Verify managed command versions, shell
   startup, client configuration/discovery, history compatibility, and gateway
   health on the live device. Keep the backup and a value-free result report.

macOS may adopt an exact matching existing Codex as specified in
[ADR 0009](adr/0009-adopt-matching-macos-codex.md). Other agents retain their
declared ownership; newer device versions are brought into the source pins and
frozen locks only through an explicit reviewed update.

### Fresh native installation

On a matching Mac:

```bash
python3 tests/native_macos.py --arch aarch64 --role workstation \
  --report /tmp/native-macos.json --install-timeout 7200 --keep-failed-home
```

The gate requires Darwin, the requested architecture, and the OS baseline. It
installs and reapplies all defaults in a temporary home containing spaces;
checks commands, pins, ordinary Nu/pip/uv discovery, idempotence, and device-state
preservation; then runs existing shell, skill, CodeGraph/MCP, and encrypted-history
suites. Diagnostics load rendered shared shell settings and explicit installed
tool paths. They use synthetic accounts/history and make no model request;
CodeGraph indexing is confined to its explicit temporary test fixture.

`--install-timeout` sets a positive bounded timeout for each full bootstrap
invocation; its default remains 2400 seconds for CI. `--keep-failed-home`
retains a failed private synthetic fixture for diagnosis; successful fixtures
are removed. Reports record the Git revision, working-source fingerprint,
dirty state, selected timeout, current phase, and completed checks. A source
change during the gate fails verification. Timeouts terminate the bootstrap's
process group, including download/lifecycle children.

Nu `-c` bypasses normal startup/autoload in the pinned release even with `-i`.
Discovery checks use `-e` to enter REPL startup before executing and exiting.
The shared shell suite separately checks actual controlling-terminal behavior.

`native-macos.yml` covers `macos-15-intel` and `macos-15` with both roles, pinned
Actions, read-only permissions, and no persisted checkout credentials. Jobs
upload only JSON results with runtime, image, CPU, commit, run URL, and check
metadata. Temporary homes/config/credentials/history are deleted after each
run. Foreign execution fails with an unavailable report; skipped required
behavior cannot count as a native pass. All four architecture/role cells have
since passed natively in run
[38524061897](https://github.com/JoJoTsui/dotfiles/actions/runs/38524061897);
[verification evidence](verification/macos.md) records both the distinct local
checks and that native result.
