# Host bring-up

`~/.local/bin/dotfiles-host-up` chains the post-reboot stack instead of starting
each daemon by hand:

```bash
dotfiles-host-up status      # read-only report
dotfiles-host-up up          # repair links, start what is down, run health
dotfiles-host-up up --restore
```

`status` checks the link manifest, Mihomo `9090`, Caveman `8787`, the Codex
app-server daemon, Herdr, and the health preflight. `up` repairs links through
`link-home`, starts Mihomo, starts Caveman under `with-proxy` (record mode by
default; `--compress` selects compress mode), starts the Codex daemon under
`with-proxy` when absent, and starts the Herdr server when absent.

`--restore` starts Herdr and lets `session.json` restore the workspace, panes,
and agents. It does not restart a running Herdr server; that would tear down
every pane and agent. Attach afterwards with `herdr`. The repo Herdr config sets
`[session] resume_agents_on_restore = true`; apply it to a live host only with
the owner's permission.

`--restart` recycles Mihomo, Caveman, and the Codex daemon. It never restarts
Herdr. Use it when the daemon lacks `HTTPS_PROXY` or a mode change is required.

There is no systemd unit and no login-shell hook. Run the command once after a
reboot; it is deliberately manual because starting or restoring agents is
disruptive. The legacy live host does not receive this command until a permitted
legacy apply.
