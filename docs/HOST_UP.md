# Host bring-up

`~/.local/bin/dotfiles-host-up` chains the post-reboot stack instead of starting
each daemon by hand:

```bash
dotfiles-host-up status      # check dependencies without starting services
dotfiles-host-up up          # repair links, start what is down, run health
dotfiles-host-up up --restore # optional local Herdr startup; not the T9K laptop flow
```

`status` checks the link manifest, Mihomo `9090`, Caveman `8787`, the Codex
app-server daemon, Herdr, and the health preflight. `up` repairs links through
`link-home` (or reports a non-legacy home without failing), starts Mihomo,
starts Caveman under `with-proxy` (record mode by default; `--compress` selects
compress mode), starts the Codex daemon under `with-proxy` when absent, and
runs the dependency health preflight with `--before-restore` (skipping only
the Herdr server check). Any failed dependency or missing/failing preflight
stops bring-up before Herdr starts.

On the legacy home, history checks run before agent preparation. `up` can
recover a restart-stale Atuin WAL index after backing up and validating the
history; `status` reports this condition without requesting recovery. Both
use SQLite integrity checks, which can perform ordinary engine checkpointing.
A failed history check stops preparation before agent restore. See
[shared history recovery](SHARED_HISTORY.md#legacy-restart-recovery).

`--restore` additionally starts Herdr and lets `session.json` restore the
workspace, panes, and agents, only after the dependency preflight passes and
the saved configuration enables agent restore. A full health check runs after
Herdr starts. It does not restart a running Herdr server; that
would tear down every pane and agent. Attach afterwards with `herdr`. The repo
Herdr config sets `[session] resume_agents_on_restore = true`; apply it to a live
host only with the owner's permission.

During `up`, with Herdr stopped, the helper validates the saved session and removes
duplicate native session references, preferring panes with explicit resume
commands. It backs up the original snapshot before an atomic replacement.
This handles stale shell references left by the shared Codex daemon: Herdr
0.9.4 uses different deduplication keys for native references and custom resume
commands. A running server's snapshot is never edited by this helper.

`--restart` recycles Mihomo, Caveman, and the Codex daemon. It never restarts
Herdr. Use it when the daemon lacks `HTTPS_PROXY` or a mode change is required.

There is no systemd unit and no login-shell hook. Run the command once after a
reboot; it is deliberately manual because starting or restoring agents is
disruptive. The legacy live host does not receive this command until a permitted
legacy apply.

On the legacy T9K notebook, run this in Bash over SSH **before attaching to Herdr**:

```bash
bash /t9k/mnt/joey/SHELL/dotfiles/deployment/legacy/link-home.sh
```

The approved legacy apply must already have installed the helper and health
script into the persistent live tree and enabled Herdr agent restore. This
sequence restores the links, loads `.env_core` inside the preparation process,
starts the longstanding Mihomo supervisor if absent, starts Caveman and the
Codex daemon, checks CodeGraph and Graphify, and prepares the saved Herdr session.
Between Mihomo and the agent daemons, the offline global integration adapter
deploys the official Graphify skill/guidance and excludes Serena and the disabled
DeepMind skill group. Its pinned resources must be fetched once before reboot;
see [the legacy integration adapter](LEGACY_APPLY.md#global-agent-integrations).
An already-running service is reused. MCP servers are launched by their agent
clients on demand; no project is indexed during preparation. Graphify is the
`graphifyy` package in the developer Pixi bundle; its exact pin has one owner in
`deployment/bundle-tools.tsv`.

Herdr is **not started** by this local command. Only after it reports success,
run this on the laptop:

```bash
herdr --remote ssh://t9kuser@127.0.0.1:23331
```

The laptop's existing SSH forwarding must already expose port 23331. The remote
command starts/attaches to the server on the notebook and resumes the prepared
agents. Do not connect while preparation is running or after it fails. Loading
`.env_core` in the link script cannot modify its parent shell, but the started
dependencies inherit it. The SSH shell separately loads the linked startup files.
This flow does not run the public bootstrap against the legacy symlink home.
