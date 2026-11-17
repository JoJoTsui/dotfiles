# 03: Bootstrap switch and action wiring

**What to build:** `bootstrap.sh` gains `--no-magpie` and `DOTFILES_MAGPIE`, with the step on by default on macOS and off elsewhere. `--plan` reports `"magpie": true|false`. `magpie-apply` joins the default action list after `install-agents`, is skipped under `--apply-only` and `--agents-only` with a stated reason, and gets a `deployment/proxy-policy.tsv` row (`magpie-apply|yes|provider requests leave through the device proxy`). Update `bootstrap.sh --help`.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] `bash bootstrap.sh --plan` on macOS contains `"magpie": true` and the `magpie-apply` action.
- [ ] `--no-magpie` and `DOTFILES_MAGPIE=false` remove both, and the run says why.
- [ ] A Linux plan reports `"magpie": false` with no action and no failure.
- [ ] `deploy_proxy_policy_complete` passes with the new row.
- [ ] Existing bootstrap/plan tests pass.

## Comments
