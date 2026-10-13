# macOS deployment

The macOS profiles reuse the common package catalog, frozen Bun projects, shared
shell values, agent payload/settings adapters, and history setup. The supported
baseline is macOS 13 or newer, on Intel or Apple silicon. Bootstrap runs with
system Bash 3.2 and installs into user-scoped roots.

From a source checkout:

```bash
/bin/bash bootstrap.sh --platform macos --role workstation --plan
/bin/bash bootstrap.sh --role workstation
# For a Mac used for remote computation:
/bin/bash bootstrap.sh --role remote-compute
```

Darwin and its architecture are detected automatically. Explicit platform,
architecture, and profile flags also support foreign planning/rendering. Both
roles install all five agents and CodeGraph by default. Optional bundles retain
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

## Native verification

On a matching Mac:

```bash
python3 tests/native_macos.py --arch aarch64 --role workstation \
  --report /tmp/native-macos.json
```

The gate requires Darwin, the requested architecture, and the OS baseline. It
installs and reapplies all defaults in a temporary home containing spaces;
checks commands, pins, ordinary Nu/pip/uv discovery, idempotence, and device-state
preservation; then runs existing shell, skill, CodeGraph/MCP, and encrypted-history
suites. Diagnostics load rendered shared shell settings and explicit installed
tool paths. They use synthetic accounts/history and make no model request;
CodeGraph indexing is confined to its explicit temporary test fixture.

Nu `-c` bypasses normal startup/autoload in the pinned release even with `-i`.
Discovery checks use `-e` to enter REPL startup before executing and exiting.
The shared shell suite separately checks actual controlling-terminal behavior.

`native-macos.yml` covers `macos-15-intel` and `macos-15` with both roles, pinned
Actions, read-only permissions, and no persisted checkout credentials. Jobs
upload only JSON results with runtime, image, CPU, commit, run URL, and check
metadata. Temporary homes/config/credentials/history are deleted after each
run. Foreign execution fails with an unavailable report; skipped required
behavior cannot count as a native pass. Native runs remain pending until CI
executes; [local evidence](verification/macos.md) records the distinct Linux checks.
