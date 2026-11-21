# Shared shell settings

`.chezmoidata.toml` owns environment defaults, regional mirror endpoints and
preference, POSIX umask, and managed PATH priority. Chezmoi renders the values
into `.env_core` and `nushell/env.nu`; Bash and Zsh source `.env_core`, while
standalone Nu loads its own guarded adapter. Existing nonempty device values
win, and repeated initialization leaves each managed directory present once.
Legacy `JOEY`, `GIZMO`, `BIO_GIZMO`, `NUSHELL_PATH`, and `JSHELL` remain
compatibility variables; their directories never enter managed PATH.

Set `DOTFILES_MIRROR=tuna` (default) or `DOTFILES_MIRROR=upstream` when running
bootstrap. The selection is persisted in Chezmoi data and covers pip, uv,
Cargo, Rustup, conda, Micromamba, and Pixi channels through one model. The
conda/micromamba config maps conda-forge, bioconda, pytorch, and nvidia to TUNA
(nvidia via ZJU) with an upstream fallback, and omits `defaults` so the
Anaconda official repository is never fetched implicitly. Pixi's global config
mirrors conda-forge, bioconda, and pytorch; it leaves nvidia upstream because
ZJU returns 403 for non-mirrored subdirectories when Pixi enumerates all
platforms. Environment overrides still win. Pinned release and skill download
URLs are not rewritten.

Conda/micromamba still use ZJU for nvidia, and mamba/micromamba fall back to
upstream when a mirror lacks a package. Conda itself does not implement
`mirrored_channels`, so its fallback is limited to the channels in its list;
use micromamba or Pixi when a just-published package is missing from the mirror.

## Device-local overrides

These files are optional, unmanaged, and preserved on reapply:

| File under `~/.config` | Loaded when |
| --- | --- |
| `dotfiles/env.local.sh` | Before shared POSIX defaults; keep POSIX-safe and idempotent |
| `dotfiles/env.local.nu` | Before shared Nu defaults |
| `dotfiles/bash.local.sh` | After interactive Bash hooks |
| `dotfiles/zprofile.local.zsh` | In Zsh login startup, before the shared profile can enter Nu |
| `dotfiles/zsh.local.zsh` | After interactive Zsh hooks |
| `dotfiles/nu.local.nu` | After managed Nu commands, including ordinary `-c` startup |
| `git/local.conf` | At the end of the managed Git configuration |

For example, set `export EDITOR=vim` in `env.local.sh` and `$env.EDITOR = "vim"`
in `env.local.nu`. Use the shell-specific config files for aliases/functions.
Nu also supports its native user autoload directory for interactive resources.
The local hooks use `~/.config/dotfiles` consistently across platforms, including
native Windows. They are deliberately absent from the source tree.

Git local settings can include `[includeIf "gitdir:~/work/"]` with a private
identity file. Git ownership protection remains enabled; add specific
`safe.directory` entries locally only for repositories whose owners you trust.

## Micromamba in Nushell

`activate <name>` applies package `etc/conda/env_vars.d/*.json` defaults and
`conda-meta/state` environment variables, with state values taking precedence.
It restores previous values and PATH on `deactivate`, and includes native
Windows DLL/tool directories. It supports one active environment at a time.

Nu cannot source Bash or cmd activation scripts. Environments containing
`activate.d` or `deactivate.d` hooks are rejected before changing shell state.
Use `micromamba run -n <name> <command>` or activate in Bash/Zsh for those
environments. PATH overrides in environment metadata are also rejected; a
partial activation is never reported as success.

PATH priority is per platform. macOS resolves the managed launcher directory
(`~/.local/bin`) before the Bun directory, so a launcher for an adopted
Homebrew agent wins in an interactive shell. Linux, WSL, and native Windows
keep the Bun directory first, because Bun is the agent provider there, and
follow it with the managed launcher directory, the Pixi exposures, and Cargo.
The shared path model in `.chezmoidata.toml` owns the order, and both shell
adapters render it. `DOTFILES_COMMON_BIN` selects Pixi exposures on
Linux/WSL/Windows and the regular common launchers on macOS. A source-only
macOS upgrade retains Pixi discovery until those launchers exist. The agent
installer invokes its
selected Bun/Node explicitly, enforcing exact pins on other platforms and
catalog floors on macOS. `MAMBA_EXE` follows the selected common directory,
and its explicit device
override is used by both shell adapters. Workstations default to normal
watcher behavior (`CHOKIDAR_USEPOLLING=0`); remote compute defaults to polling.

`noproxy` enables the configured URL in all four HTTP/HTTPS proxy variables;
`unproxy` removes those variables. Nu retains `nuproxy` as a compatibility
alias. Ordinary initialization preserves existing proxy variables and does not
enable a proxy implicitly. Values are escaped for each shell's syntax.

Direct interactive Bash/Zsh keep their shell and initialize the same applicable
Pixi, micromamba, Starship, zoxide, direnv, and fzf integrations. `.profile` and
`.bash_profile` share one preferred-launcher guard. `nu-login` chooses Nu only
for a real terminal without script arguments or a coding-agent/secondary-shell
marker. `DOTFILES_SECONDARY_SHELL=1` provides an explicit opt-out. Scripts and
non-TTY calls use Bash; neither account login-shell state nor `SHELL` is changed.
Non-interactive Bash follows its normal startup rules: source `.env_core` when
starting from a deliberately minimal environment, or inherit the parent shell's
managed environment. Standalone Nu inherits the process umask because it has no
POSIX umask builtin.

## Nushell completions and fuzzy finding

Nu config uses adjacent owned resources, including the pinned zoxide adapter.
Standalone startup works before package installation. After packages exist,
`dotfiles-shell-prepare` generates native Starship/Pixi/fzf resources and
prepares command completions under
`XDG_DATA_HOME/nushell/vendor/autoload`. New resources are validated before
replacement, and symlinked startup state is rejected. A startup path is inside
the home when it is spelled under the home or under its canonical spelling; an
alias outside the home that resolves into it is refused, because the alias is
not part of the home. Startup reads prepared
files; fetching and generation belong to bootstrap, never shell startup.

`deployment/nu-completions.json` pins the `nu_scripts` revision, each module's
SHA-256, and an optional offline archive checksum. It maps allowlisted command
names to completion modules. Its rendered
configuration is `~/.config/dotfiles/nu-completions.json`. The preparer intersects
that allowlist with desired common/selected-bundle exposures and actual managed
executables. It copies only matching module resources, leaving unrelated
upstream scripts outside the deployed home. Native completion generators take
precedence over community modules: uv and selected Just installations use
their own Nu generators. Normal preparation downloads only selected community
module files and caches their verified bytes; a changed selection replaces the
owned loader. Native output and community imports share the same validation
and publication boundary. Validation fails on a parse error but only reports a
deprecation warning: a device may run a Nu newer than the pinned revision, and
that warning belongs in the preparation output rather than in every
interactive startup. Each published content directory carries the revision and
a digest of its bytes, so a selection or catalog change publishes a new one.
A loader is the file a Nushell startup imports: the canonical one lives in the
vendor autoload directory of the XDG data home, and a platform adds its native
discovery copies. The completion module owns that lifecycle. It validates a
new generation with the installed Nu before any loader switches, replaces
every managed loader atomically, and retires a generation only after no
managed loader imports it any more. A loader stores each import as a JSON
string, so the retirement check decodes that reference instead of matching raw
text: a Windows path spells every separator twice and a quoted home name
escapes its quote, and both keep the generation they name. A loader that
refuses the replacement keeps the generation it imports, so an interrupted
publication leaves every loader usable and a failed publication leaves the
working loader and its generation alone. A generation is retired only when its
bytes prove this deployment published it: the published name carries the digest
of the module files, so the cleanup recomputes that digest from the exact
regular files the directory holds. A device-created directory that carries the
published shape, a directory with an added or a foreign entry, and a symlink
are left alone.

Ownership decides which loader a publication may write. A canonical loader is
owned by declaration: the XDG loader the deployment writes, plus the native
copy the platform's catalog names, such as the macOS user autoload directory
`~/Library/Application Support/nushell/autoload`. The catalog names that
directory for the other startup resources; it does not copy the pinned loader,
so the deployment's discovery adapter is not a second publisher for it. A
legacy loader is a path an
earlier publication may have written, such as the macOS vendor autoload
directory `~/Library/Application Support/nushell/vendor/autoload`, which an
earlier preparation mirrored into. The publication takes a legacy loader over
only when the file on disk carries the managed marker. A device file of the
same name is preserved, and an existing native directory is no reason to
create a duplicate loader in it. A preserved loader keeps the generation it
names, so the cleanup never removes a generation under a live loader. The macOS
preparation selects the native paths from the Nu discovery command and falls
back to the documented macOS directories when that command fails, so a
required loader path is never omitted and the generation that loader imports
stays published.

For an air-gapped preparation, supply `DOTFILES_NU_SCRIPTS_ARCHIVE` with a local
copy of the pinned archive; checksum verification still applies. Updating the
revision or allowlist requires reviewing the upstream changes, updating the
checksum, and validating the selected modules against the pinned Nu version.
An empty installed selection needs no download. `--apply-only` deploys the
configuration and helper without provisioning completion resources.

fzf supplies file/directory picking in Bash, Zsh, and Nu. Its Nu adapter leaves
Ctrl-R to Atuin, preserving the configured shared-history search. eza remains
the managed directory-listing alternative. Skim and lsd are retained only in
the historical inventory; omitting their active catalog entries preserves
existing device installations.

Nu vendor autoload is interactive: ordinary `-c` execution omits it. macOS and
native Windows receive regular discovery copies of the same prepared loaders.
The discovery adapter remains the deployment's only catalog writer. A
preparation run outside a deployment additionally mirrors the artifacts it
generated into the directory Nu resolves without an XDG override, which on
macOS is `~/Library/Application Support/nushell/vendor/autoload`, so a launch
from outside the managed environment never reads an older startup. That mirror
writes only existing entries, keeps a device file, and refuses a symlinked
target. The pinned loader is neither mirrored nor copied: the completion
module publishes it to the canonical native loader path and takes over a
mirrored copy only when
that file is demonstrably managed, so the deployment's own discovery copy
never outlives the generation it imports and a device loader of the same name
is preserved. Generated resources and device state are not imported into git. See
[Nu configuration](https://www.nushell.sh/book/configuration.html).

History preparation follows shell preparation. `dotfiles-history-prepare`
generates and validates the pinned Atuin Nu resource in that same vendor
autoload directory; Bash/Zsh initialize their bundled hooks after fzf. Both
adapters share canonical `ATUIN_CONFIG_DIR`/`ATUIN_DATA_DIR` values. See
[history setup](SHARED_HISTORY.md) for explicit activation/import and the
limitations of each shell's separate native history.

`logs` forwards files, flags and piped input to `tspin`. The shared default
`TAILSPIN_PAGER='less -R [FILE]'` satisfies Tailspin's pager placeholder and
keeps ANSI highlighting visible; existing pager overrides win. `logs --print
application.log` prints without a pager. See [Tailspin usage](https://github.com/bensadeh/tailspin).

## Pane and agent shells

The account shell is `/bin/bash` on Linux and WSL and `/bin/zsh` on macOS;
`.profile`/`.bash_profile` and `.zprofile` exec Nu for an interactive login.
macOS applies no Bash startup file, so its login path runs through
`~/.zprofile`. Pane shells are separate:

- Herdr: `terminal.default_shell = "nu-login"` with `shell_mode = "non_login"`.
- Zellij: `default_shell` points at `nu-login`.
- tmux: not configured; tmux is unused on this host.

`nu-login` starts Nu only for an interactive TTY and falls back to Bash for
non-TTY calls, arguments, or agent-marked environments. Agent tool shells are
client-owned and remain Bash/Zsh; Codex uses `bash -lc`, Claude honors
`CLAUDE_CODE_SHELL`, and OpenCode uses a compatible `$SHELL` or Bash/Zsh. Do not
export `SHELL=nu` from the login guard: keep `SHELL` as the account shell so
`$SHELL`-based tools still find Bash. A legacy profile that exports it should be
corrected on its next permitted apply.

## Checks and evidence

```bash
DOTFILES_TEST_CHEZMOI=/path/to/chezmoi \
DOTFILES_TEST_TOOL_HOME=/path/to/isolated-installed-home \
python3 -m unittest discover -s tests -p test_shell_behavior.py -v
```

The Linux checks borrow pinned real executables read-only through declared
fixture links/adapters and write only to separate temporary homes. This proves
rendered environment behavior and actual execution; it does not claim to install
the tools. `test_common_install.py` separately verifies selected-prefix package
ownership. The shell suite covers role parity, overrides, idempotence, proxy
escaping/unset, zoxide navigation, RTK, Tailspin plus actual less paging, script
guards, real controlling-TTY Nu preference, ordinary interactive Nu discovery,
repeatable resource generation, generator failure preservation, and startup
before package installation. Native macOS/WSL/Windows execution was established
by the corresponding platform/matrix tickets, and only WSL2 ARM64 is now
unscheduled.
