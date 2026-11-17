# 04: dotfiles-magpie command and magpie launcher

**What to build:** Two managed executables:
- `dot_local/bin/executable_dotfiles-magpie` → `~/.local/bin/dotfiles-magpie` with `apply`, `status`, and `providers`.
- `dot_local/bin/executable_magpie` → `~/.local/bin/magpie`, which execs `/Applications/magpie.app/Contents/MacOS/magpie "$@"` and prints the cask command when the app is missing.

`status` is read-only: gateway (`magpie status --json`), proxy (`magpie settings get proxy`), provider presence, resolved group member order, agent wiring, and the last Codex guard verdict. It exits non-zero when a required piece is missing. `providers` prints the catalog and whether each source resolves, never a value. Both refuse to run on a non-macOS host with a one-line reason.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] `dotfiles-magpie apply` calls the same `magpie_apply` as the bootstrap step.
- [ ] `dotfiles-magpie status` exits 0 on a healthy fake gateway and non-zero with a named missing piece.
- [ ] No subcommand prints a credential.
- [ ] `magpie --version` works through the launcher when the app exists, and the missing-app message is actionable.

## Comments
