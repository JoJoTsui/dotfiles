# 03: Bootstrap switch and action wiring

**What to build:** `bootstrap.sh` gains `--no-magpie` and `DOTFILES_MAGPIE`, with the step on by default on macOS and off elsewhere. `--plan` reports `"magpie": true|false`. `magpie-apply` joins the default action list after `install-agents`, is skipped under `--apply-only` and `--agents-only` with a stated reason, and gets a `deployment/proxy-policy.tsv` row (`magpie-apply|yes|provider requests leave through the device proxy`). Update `bootstrap.sh --help`.

**Blocked by:** 02.

**Status:** done

- [x] `bash bootstrap.sh --plan` on macOS contains `"magpie": true` and the `magpie-apply` action.
- [x] `--no-magpie` and `DOTFILES_MAGPIE=false` remove both, and the run says why.
- [x] A Linux plan reports `"magpie": false` with no action and no failure.
- [x] `deploy_proxy_policy_complete` passes with the new row.
- [x] Existing bootstrap/plan tests pass.

## Comments

`bootstrap.sh` resolves the switch after the profile: the step is on for
macOS, and `--no-magpie` or `DOTFILES_MAGPIE=false` turns it off everywhere.
`DOTFILES_MAGPIE=true` does not turn it on elsewhere, because the catalog and
the gateway are macOS-only today. The reason the step is off is kept in one
variable, so every run prints the same line: the platform does not have
Magpie, the step is disabled, or `--apply-only`/`--agents-only` applies files
and installs agents without the gateway.

`magpie-apply` is inserted right after `install-agents`, so the cask, the
agents, and the client settings exist before the gateway is wired, and it
still runs before `prepare-shell`. The restricted modes keep their own action
list and say why the gateway is skipped. `--plan` reports `"magpie": true` or
`false` next to `"proxy"`.

`deployment/proxy-policy.tsv` gains `magpie-apply|yes|provider requests leave
through the device proxy`. The section reaches the providers through the
proxy while the loopback gateway stays direct, because the policy keeps
`no_proxy` on the local addresses.

Tests run:

- `bash -n bootstrap.sh` — passes.
- `python3 -m unittest test_magpie -v` — 23 tests, all pass. The switch tests
  read the plan on macOS and Linux, with the flag and with the environment
  variable, and a Linux `--apply-only` apply reports the skip.
- `python3 -m unittest test_proxy` — passes, including the check that every
  `run_step` in `bootstrap.sh` has a proxy policy row.
- `python3 -m unittest test_deployment` — 2 failures, both pre-existing on
  this macOS host and unchanged by this work: the Windows ARM matrix is
  reported before the native-Windows message, and the simulated-home check
  reports the native-platform mismatch before the account-home message. They
  fail the same way on `main`.
- The simulated-home apply from `AGENTS.md` (`--class t9k --apply-only`)
  succeeds and prints `dotfiles: magpie: skipped; --apply-only applies files
  without the gateway`.
