# Shared shell settings

`.chezmoidata.toml` owns environment defaults, the TUNA Python endpoint and
preference, POSIX umask, and managed PATH priority. Chezmoi renders the values
into `.env_core` and `nushell/env.nu`; Bash and Zsh source `.env_core`, while
standalone Nu loads its own guarded adapter. Existing nonempty device values
win, and repeated initialization leaves each managed directory present once.
Legacy `JOEY`, `GIZMO`, `BIO_GIZMO`, `NUSHELL_PATH`, and `JSHELL` remain
compatibility variables; their directories never enter managed PATH.

PATH prefers Bun agent launchers, then local commands, Pixi exposures, and
Cargo. The agent installer invokes pinned Bun explicitly; PATH preference
does not authorize a retained device Bun binary to perform package installs.
`MAMBA_EXE` points to the managed Pixi exposure, and its explicit device
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

Nu config uses adjacent owned resources, including the pinned zoxide adapter;
no startup clone or external `nu_scripts` checkout is required. Missing tools
are guarded during `--apply-only` startup. After package installation,
`dotfiles-shell-prepare` generates Starship/Pixi resources under
`XDG_DATA_HOME/nushell/vendor/autoload`, validates them before replacement,
and rejects symlinked artifact/state directories. Bootstrap calls this command
in its required shell preparation stage. Generated resources and device state
are not imported into git. Nu vendor autoload is interactive: ordinary `-c`
execution omits it. See [Nu configuration](https://www.nushell.sh/book/configuration.html).

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
