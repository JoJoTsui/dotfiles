# 04: dotfiles-magpie command and magpie launcher

**What to build:** Two managed executables:
- `dot_local/bin/executable_dotfiles-magpie` → `~/.local/bin/dotfiles-magpie` with `apply`, `status`, and `providers`.
- `dot_local/bin/executable_magpie` → `~/.local/bin/magpie`, which execs `/Applications/magpie.app/Contents/MacOS/magpie "$@"` and prints the cask command when the app is missing.

`status` is read-only: gateway (`magpie status --json`), proxy (`magpie settings get proxy`), provider presence, resolved group member order, agent wiring, and the last Codex guard verdict. It exits non-zero when a required piece is missing. `providers` prints the catalog and whether each source resolves, never a value. Both refuse to run on a non-macOS host with a one-line reason.

**Blocked by:** 02.

**Status:** done

- [x] `dotfiles-magpie apply` calls the same `magpie_apply` as the bootstrap step.
- [x] `dotfiles-magpie status` exits 0 on a healthy fake gateway and non-zero with a named missing piece.
- [x] No subcommand prints a credential.
- [x] `magpie --version` works through the launcher when the app exists, and the missing-app message is actionable.

## Comments

The engine is now the deployment's Magpie half in two places: the working tree
copy in `deployment/magpie.sh`, which the bootstrap step sources, and the
managed copy at `~/.local/share/dotfiles/magpie/engine.sh`, which the source
application renders from it. The four catalogs get the same treatment in
`~/.config/dotfiles/magpie/`, so the command reads the same intent the
deployment applies. Both stay out of the homes that cannot run Magpie.

`~/.local/bin/dotfiles-magpie` loads the engine and dispatches `apply`,
`status` and `providers`. `apply` calls the same `magpie_apply` the bootstrap
step calls, so the operator and the deployment cannot disagree. `status` is
read-only: it reports the gateway, the proxy, every provider with its
credential state, every group with its resolved member order, the agent
wiring, and the last Codex guard verdict from the recorded state; it exits
non-zero and names every missing piece. `providers` prints the catalog with
the state of each credential source and never a value. On a host that cannot
run Magpie the command says so in one line: `apply` reports the skip, the
other subcommands refuse.

`~/.local/bin/magpie` execs the binary the cask ships and prints
`brew install --cask magpie` when the app is missing. The app path can be
overridden with `MAGPIE_APP` for a device that installs the app elsewhere.

Tests run:

- `bash -n dot_local/bin/executable_dotfiles-magpie` — passes.
- `python3 -m unittest test_magpie -v` — 38 tests, all pass. The command tests
  drive the managed command against the fake gateway: `apply` runs the same
  engine, `status` exits 0 on a healthy gateway and non-zero with the missing
  piece named, no subcommand prints a credential value, `providers` names the
  source and not the value, the command refuses a non-macOS host, the
  launcher runs the app binary, and the missing app names the cask command.
- A simulated macOS apply (`--platform macos --apply-only`) places the engine,
  the catalogs, and both launchers with the right modes; a simulated Linux
  apply leaves the engine and the catalogs out and still places the commands.
