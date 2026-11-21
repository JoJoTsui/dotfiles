# AGENTS.md

Read `README.md` for orientation (layout, deployment profiles, coding-agent table).
This file is the operational contract for working in this repo.

## Model

This repo is a **chezmoi source state** applied to new/test hosts in copy mode.
Rules that follow from it:

- The repo is the source of truth. Fold host changes *into it*; never edit a
  target host and consider the job done.
- **Real-home application requires explicit user authorization and successful
  verification first.** Validate in simulated homes, pass the matching native
  deployment gate, and rehearse migration of an existing device before applying
  to its account home. Read `docs/MACOS_DEPLOYMENT.md` for the existing-Mac gate.
- The legacy T9K live tree predates Chezmoi and remains outside ordinary
  deployment; its explicit legacy adapters preserve that separate boundary.

## Agent skills

### Issue tracker

Work is tracked as local markdown under `.scratch/`. See
`docs/agents/issue-tracker.md`.

### Triage labels

Tickets use the canonical five-role vocabulary. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` plus `docs/adr/`. See
`docs/agents/domain.md`.

## Naming

- `dot_x` → `~/x`; `dot_config/...` → `~/.config/...`; nested names map 1:1
  (`dot_pi/agent/settings.json` → `~/.pi/agent/settings.json`).
- Files needing template data end in `.tmpl` (suffix stripped on apply);
  without it, contents apply verbatim.
- `.chezmoiignore` patterns match **target** names (verified via
  `chezmoi ignored`), and cover everything not meant for `$HOME`:
  `README.md`, `AGENTS.md`, `bootstrap.sh`, `deployment`, `tests`, `docs`,
  `system`, `clash`, `.vscode-server` (workstation roles).

## Template data

Defined in `.chezmoi.toml.tmpl`, sourced from environment variables at init:
`platform` (`DOTFILES_PLATFORM`), `role` (`DOTFILES_ROLE`, default workstation),
`arch` (`DOTFILES_ARCH`), legacy `class` metadata, `proxyUrl`
(`HTTP_PROXY_URL`), `kimiApiKey` (`KIMI_API_KEY`). Defaults keep unattended
init non-interactive. `bootstrap.sh` resolves profile presets and legacy aliases
then exports canonical selectors. Read `docs/DEPLOYMENT_BOUNDARY.md` when
changing selection, planning, state isolation, or installer adapters.
Token defaults are the literal `REPLACE_ME` — a rendered
target containing `REPLACE_ME` is healthy, a committed real token is an
incident (rotate it; history rewrite is not a substitute).

## Secrets

- Never stage `*keys.json`, `auth.json`, `credentials`, `*.pem`, `*.token`
  (git-ignored at repo root *and* via the global gitignore). `claude/glm-keys.json`
  exists untracked on the legacy host — leave it that way.
- When copying config from a live host, redact tokens/keys/bearer headers to
  placeholders first (`ANTHROPIC_AUTH_TOKEN`, `CONTEXT7_TOKEN`, `sk-…`,
  `glmfix_…`, oauth `key =` fields).
- Codex providers take `env_key` names, not values — keep it that way.
- The Magpie credential store `~/.config/dotfiles/magpie.env` is device-owned,
  mode 0600, and never committed. The deployment parses it; no shell profile
  sources it, and a credential never enters a log, a report, or a ticket
  comment.

## Validating a change (simulated host)

1. Edit the source file(s); commit-worthy changes are staged but uncommitted.
2. Use a fresh `simulated_home=$(mktemp -d /tmp/dotfiles-sim.XXXXXX)` and run
   `DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh --source "$PWD" --home "$simulated_home" --class t9k --apply-only`.
   The boundary applies the **working tree** and isolates XDG/package-manager
   roots. Repeat with `--class linux` in a fresh simulated home to exercise
   the ignore branch. `init --apply "$PWD"` clones committed HEAD and misses
   working changes; the public bootstrap does not use that form.
3. Check rendered values with `rg`, confirm required files are regular files,
   then delete the simulated home after any shell checks.
4. For nushell edits, also run
   `nu --config "$simulated_home/.config/nushell/config.nu" --env-config "$simulated_home/.config/nushell/env.nu" -c 'print "ok"'`
   with `JOEY/JSHELL/...` unset (`env -u`) — config must bootstrap standalone
   without the host's external completion checkout. Read
   `docs/SHARED_SHELL_SETTINGS.md` for preparation and interactive checks.

Run `DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest discover -s tests -v`
for changes to the public deployment boundary; actual apply tests report a skip
when chezmoi is unavailable. They must run before claiming application passed.
That suite assumes a Linux x86_64 host: it asserts native-platform detection, the
Windows architecture matrix, and the Linux-only host bring-up helper. On macOS
those tests fail by design, so run `python tests/native_macos.py --arch aarch64
--role workstation --report <path>` instead, and treat the remaining Linux-suite
failures as host scope rather than regressions.

Done when: the simulated apply succeeds for both legacy profiles, the nushell check
passes (if touched), `git status` shows no secret files, and the commit body
explains every changed pair.

## Invariants

- **`.env_core` is POSIX sh and idempotent** (`: "${VAR:=...}"` guards);
  bash sources it before the interactive check so non-interactive shells get PATH.
  Managed tool paths own the front of PATH: `_dotfiles_prepend_path` moves an
  existing copy instead of skipping it, because macOS `path_helper` rewrites
  PATH after `~/.zshenv` runs.
- **Shared settings are defined once**: `.chezmoidata.toml` owns shared defaults
  and PATH priority. `dot_env_core.tmpl` and
  `dot_config/nushell/env.nu.tmpl` render its POSIX/Nu syntax; change the model,
  then verify both adapters. Managed PATH priority is per platform: macOS
  resolves the managed launcher directory (`~/.local/bin`) before the Bun
  directory, so a launcher for an adopted Homebrew agent wins; Linux, WSL,
  and native Windows keep the Bun directory first. `proxyUrl` is the static
  value written into the vscode-server setting; the shell proxy helpers
  resolve the port at call time through `with-proxy`, because the port belongs
  to whichever proxy client the device runs (Clash Verge 7897, deployment
  mihomo 7890), not to the OS. The `.bashrc` and `.zshrc` interactive blocks
  keep equivalent managed-tool hooks (Zsh adds its required `compinit`).
- **The completion module owns the Nu loader publication**:
  `dot_local/lib/dotfiles/completions.py` publishes one validated generation to
  every canonical loader (the canonical XDG loader plus the platform's catalog
  native copy) and retires a generation only after no loader imports it and
  its bytes prove the deployment published it: the published name carries the
  digest of its module files, so the cleanup recomputes that digest and a
  device directory with the same shape stays. A startup path is inside the home
  when it is spelled under the home or under its canonical spelling, so an
  alias outside the home that resolves into it is refused. A
  legacy loader path — one an earlier publication may have written, such as the
  macOS vendor autoload directory — is taken over only when the file carries
  the managed marker: a device file of the same name is preserved, an existing
  native directory is no reason to create a duplicate loader, and a preserved
  loader keeps the generation it names. A loader stores each import as a JSON
  string, so the retirement check decodes that reference instead of matching
  raw text. `dotfiles-shell-prepare` and the native Windows preparation select
  the loaders and call the module; they never write the loader themselves. The
  macOS catalog does not copy the pinned loader, so the deployment's discovery
  adapter is not a second publisher; a Nu that cannot answer the discovery
  command falls back to the documented macOS directories, so a required loader
  path is never omitted. Read `docs/SHARED_SHELL_SETTINGS.md` before changing
  the loader, the generation lifecycle, or the native copies.
- **macOS runs Zsh, not Bash**: macOS applies no Bash startup file and installs
  no managed Bash runtime. `dot_zprofile` is the Zsh login file and shares
  `~/.profile` with Bash's, because Zsh never reads `~/.profile` itself.
- **Env vars and managed binaries must match**: when a config or env var
  implies a command, the pixi manifest or a bootstrap step must install it in
  the same commit (`EDITOR=hx` → helix exposed as `hx`; `RUSTUP_*` → the
  rustup bootstrap step; `pip.conf` → the `python`/`pip` env; the vscode `ty`
  setting → the `ty` env; zellij's `default_shell` → managed
  `~/.local/bin/nu-login`).
- **A pinned version has one owner**: the catalog owns the version and the
  digests that verify it move with it. `deployment/update_versions.py` refreshes
  the manager digests when it bumps a manager version, and `check` fails when a
  pinned target is missing. A version bump that leaves a digest, a runtime
  version check, or a second catalog behind breaks the deployment.
- **A device may own the version it runs**: `~/.config/dotfiles/versions.tsv`
  is device state that the deployment reads and never writes. An `agent` entry
  replaces a client pin, a `tool` entry a Pixi specification, and a `cli` entry
  the accepted installer floor. The catalog keeps the default; the plan reports
  every effective override. Atuin and the bootstrap managers stay with the
  repository pin. Read `docs/adr/0010-device-version-overrides.md` before
  changing the override kinds, the manifest, or the merge input.
- **The agent provider catalog owns agent installation data**:
  `deployment/agents/providers.tsv` declares every agent, provider, package or
  release, package kind, version, version policy, command, platform, chain
  order, selection mode, and Herdr kind; `deployment/agents/herdr-kinds.tsv`
  declares the kinds a record may name. Both bootstrap adapters read these
  files, so a record is the only place an agent's installation is described,
  and an invalid record stops the deployment before it creates state. A
  Homebrew record carries a floor and is adopted, never installed; a
  deployment-owned record keeps an exact pin. Read
  `docs/AGENT_INSTALLATION.md` before changing an agent's provider, pin,
  command, or Herdr kind.
- **Herdr owns its integration bytes**: the deployment triggers
  `herdr integration install <kind>` for the selected managed agents, after
  the agent step and before the final client-settings merge, and never writes
  an integration file itself. The kind comes from the provider catalog, so an
  agent outside the selection is never passed to Herdr, and MiniMax Code and
  CodeGraph have no kind at all. A missing or outdated integration is
  installed, a current one is left alone, and a host without Herdr completes
  the deployment with nothing to do. Every codex install or reinstall is
  followed by `dotfiles-codex-herdr install`, so the managed resume hook stays
  last. That registration reconciles the owned command at command granularity:
  the owned command is the exact invocation of the managed hook script of this
  home — the script alone, or the script under `bash` or `sh`, with no extra
  argument and no operator — so a device command that names another home's
  copy, that only mentions the script, or that runs a file beside it, is a
  device command; a device command beside the owned one in a mixed
  SessionStart group keeps its own commands and its own metadata, Herdr's
  entries are never written, and `dotfiles-codex-herdr remove` takes the owned
  command out again. A Herdr restore reaches the thread through
  `dotfiles-codex-resume`, so a restored thread keeps its saved provider,
  model, and reasoning effort, while a fresh launch keeps the plain route. The
  launcher and that command are refreshed together, because the launcher
  passes `--no-daemon` and a command that predates that option refuses it.
  `~/.local/bin/dotfiles-herdr-status` owns the
  status vocabulary the
  deployment, `dotfiles-agents status`, and
  `dotfiles-agent-health --clients` share. Herdr's own skill is generated
  into the shared tree and recorded as a generated skill, so pruning leaves it
  alone. Read `docs/adr/0012-herdr-owned-integrations.md` before changing the
  Herdr step, the kind mapping, or the generated skill.
- **The installer order is per platform**: macOS resolves a missing command
  through Homebrew, then Pixi, then a native release; Linux, WSL, and native
  Windows use Pixi, then a native release. Homebrew is adopted from the device
  and never installed here, and a device without it falls through to the next
  installer. `deployment/installer-tools.tsv` owns macOS common formula
  candidates and casks, with version floors recorded in deployment state.
  Common command groups resolve before the Pixi merge and use regular
  `~/.local/bin` launchers on macOS. Retain existing device Pixi entries.
  An installer install writes outside the home, so it
  runs only on the real account home. Read
  `docs/adr/0008-installer-order.md` before changing the order, the catalog, or
  the tier step.
- **Legacy tool dirs stay off PATH**: `.env_core`/`env.nu` keep `$GIZMO`/
  `$BIO_GIZMO`/`$NUSHELL_PATH` as variables for legacy hosts and scripts, but
  never prepend them — every CLI (bio tools included) comes from the pixi
  manifest or a declared bootstrap exception. Add common tools to
  `deployment/common-tools.tsv`; read `deployment/inventory/README.md` when
  changing optional ownership. Desired manifests under `.config/dotfiles`
  merge into device registries; source application never replaces them.
- **Scripts need the `executable_` source prefix**: chezmoi derives a target's
  exec bit from that attribute, *not* from the source file's mode (a 0755
  source without it renders 0644 — verified on chezmoi 2.59.1 and 2.72.2), so
  every managed script is named `dot_local/bin/executable_*` and lands
  `~/.local/bin/<name>` with mode 0755.
- **The exec-nu guard** in `dot_profile`/`dot_bashrc` stays POSIX-safe and
  fires only for a real interactive TTY outside a Claude Code session
  (rationale: `docs/CLAUDE_SETUP_T9K.md`).
- **`dot_config/nushell/env.nu.tmpl` keeps guarded `$env.JOEY? | default` bootstrap
  + `path add … uniq`** — standalone `nu` (spawned without bash) must still
  resolve compatibility variables while `micromamba.nu` invokes managed
  `MAMBA_EXE`, never a legacy tool tree.
- **JSONC files**: `deployment/client-settings/opencode.jsonc.tmpl` (merged by
  bootstrap), `dot_vscode-server/data/Machine/settings.json.tmpl`,
  `docs/vscode-win-settings.jsonc` — validate as JSON-with-comments, not shell
  (historical `.sh` naming retired).
- **Every platform plan is read from its own public adapter**: the portable
  check calls `bootstrap.sh` for Linux, macOS, and WSL and `bootstrap.ps1` for
  native Windows, compares the fields the two adapters share, and asserts the
  tool and step selections in the adapter that owns them. A native
  verification report names the checkout it verified and the outcome of every
  scenario; a skip states its reason, and an unavailable runner never counts
  as acceptance. Read `docs/verification/complete-matrix.md` before changing
  the verification boundary.
- **A native report names the checkout it verified before it tested**: the
  identity is established before the first check runs, a run that cannot name
  its revision establishes no acceptance, and a required scenario that did not
  pass withholds the acceptance instead of sitting beside it. The native
  Windows adapter publishes its report only after the shared contract
  succeeded, so a report left by an earlier run never becomes this run's
  verdict. The portable check accepts its local layer only after the catalog,
  the skill pins, and the deterministic suite passed, and a failed report keeps
  the layer failed.
- Not applied to `$HOME` (ignored): `system/`, `clash/`, `docs/`, `deployment/`,
  `tests/`. Ordinary bootstrap has no system or account login-shell action.
- **Legacy home symlinks are explicit and opt-in**:
  `deployment/legacy/link-home.sh` and its `home-links.tsv` manifest
  maintain the pre-chezmoi T9K tree. Bootstrap never runs them; managed homes
  stay in copy mode. The utility validates before writing, backs up replaced
  targets, and requires `--system` for `/etc` changes. Read
  `docs/LEGACY_HOME_LINKS.md` before adding state roots to the manifest.
  `deployment/legacy/apply.sh` and `apply.tsv` are the companion file-level
  adapter: they sync only listed repo-owned executables and the Herdr config,
  refuse symlink targets and escapes, back up, and exclude client settings,
  payload blocks, shell rc, auth, packages, and runtime state. Read
  `docs/LEGACY_APPLY.md` before adding files.
- **Agent payloads use the public bootstrap copier**: instructions and adapters
  live under `deployment/agent-payload/`; skill bytes are fetched from the
  upstream catalog in `deployment/skills.tsv` and never vendored. Copying
  preserves filenames and permissions without executing helpers, and applying
  produces regular discovery files plus managed instruction blocks while
  preserving unrelated device content. A skill name belongs to one discovery
  root per client: the shared tree `~/.agents/skills` is the portable home, and
  a client root that repeats a name makes that client warn — the deployment
  reports the duplicate. Read `docs/AGENT_PAYLOAD.md` before changing global
  instructions, skills, or their copy adapters.
- **Proxy provisioning is opt-in and pinned**: `deployment/proxy/mihomo.tsv`
  owns the release URL and SHA-256 per target; `bootstrap.sh --proxy`
  installs and refreshes the profile, and the managed tree under
  `dot_local/share/dotfiles/proxy/` owns routing and supervision. The
  subscription URL is template data (`MIHOMO_SUBSCRIPTION_URL`), never git.
  Read `docs/PROXY.md` before changing either side.
- **The proxy launchers share one endpoint decision**: `with-proxy` owns the
  precedence, the health check, the overrides (`PROXY_HTTP`, `PROXY_SOCKS`,
  `PROXY_NO`), and the supported variables; the POSIX helper in `.env_core`
  and the Nushell adapter in `dot_config/nushell/proxy.nu` both read it, so the
  shell a session runs in never changes the route. A direct launch clears the
  supported inherited variables for its child only, and a proxied launch
  applies its environment to the child only. The bindings carry fixed
  variable names and the overrides are single-line values: an override that
  carries a line separator is refused before any binding is emitted, and the
  POSIX helper reads the answer before it evaluates it, so a refusal reaches
  the caller. Read `docs/PROXY.md` before changing a launcher, and
  `docs/adr/0016-shared-proxy-launcher-interface.md` before changing the
  decision itself.
- **The deployment proxy is a process, not a service**:
  `deployment/proxy-policy.tsv` says which sections need a proxy and which do
  not, and the bootstrap validates that every step has a rule. The instance
  starts with the first section that needs it and stops with the deployment.
  A proxy client the user already runs is detected and left alone: the
  deployment takes another port rather than competing for the usual one. The
  instance routes through US nodes on its own ports and its own profile, so
  the long-standing service keeps its profile and its controller.
- **Skills carry a selection**: the catalog's last column is `auto` or a tag.
  `auto` is the reviewed core; a tagged skill is not deployed automatically, and
  a host asks for it with `DOTFILES_SKILLS=<tag>` or by skill name. The tags are
  `caveman` for the caveman-branded skills other than the mode and its compress
  skill, `lark` for the Feishu skills outside the documentation cluster (including
  `lark-openapi-explorer`), and `optional` for the reviewed specialist workflows
  listed in `docs/SKILL_REVIEW.md`. The four design skills and the lark
  documentation cluster stay in the `auto` core; `find-skills` is disabled in
  `deployment/disabled-skills.tsv`.
- **Managed skills are recorded and pruned**: the deployment records the skill
  directories it wrote into each managed root in
  `~/.local/state/dotfiles/managed-skills.tsv`, and the prune step removes a
  recorded directory that leaves the selection. A device-created skill, a
  generated skill, and a symlinked entry are preserved and reported, never
  removed.
- **A copy root is inspected before a skill is written there**: a device entry
  that carries the name of a selected skill is preserved and reported, and the
  copy never follows a link or writes through it. An unrecorded directory that
  already holds the selected bytes is adopted without a rewrite; a directory
  the inventory records belongs to the deployment, so the staged copy replaces
  it. The generated Herdr skill reaches every managed root, and each root is
  recorded in `~/.local/state/dotfiles/generated-skills.tsv`.
- **The catalog is the only writer of a managed skill root**: `bunx skills add`
  and `bunx skills update` must not target `~/.agents/skills` or a client root
  the deployment owns. The CLI's lockfile at `~/.agents/.skill-lock.json` is
  device state: the deployment reads it, never writes it, and reports every
  uncatalogued or disabled entry with its exact `bunx skills remove <name>`
  command. An apply and the pin check report the drift without failing;
  `deployment/skill_drift.py` is the dedicated report a gate runs. Read
  `docs/AGENT_PAYLOAD.md` before changing the catalog, the lock, or the report.
- **The skill review gate is measured, not asserted**: a skill's description
  is at most 240 characters and its root document is at most 200 lines, unless
  the skill ships a reference file. `deployment/skill-budget-exceptions.tsv`
  records today's over-budget rows with their measured values and a reason; a
  new row above a budget fails the check by name, and a row whose measurements
  no longer match its exception fails as well, because updating an exception is
  a review action. `python3 deployment/update_skills.py check` reads the
  deployed shared tree by default, reports the per-client inventory, the
  findings, and the ratchet result, and never claims a budget it could not
  measure. The per-client matrix is `deployment/agent-payload/skill-clients.tsv`.
  Read `docs/SKILL_REVIEW.md` before changing the budget, the exception list,
  or the matrix.
- **Worktrunk is the shared worktree tool**: the `wt` command is a common Unix
  tool (native Windows keeps the name for Windows Terminal), its skill bytes
  come from the upstream catalog like every other skill, and the per-client
  plugins are client state that the CLI writes. The deployment never reproduces
  plugin content. Read `docs/WORKTRUNK.md` before changing the command, the
  skill rows, the shell integration, or the plugin step.
- **Client settings merge through bootstrap**: defaults under ignored
  `deployment/client-settings/` merge into runtime paths excluded from Chezmoi.
  The explicit legacy `deployment/legacy/agent-integrations.sh` adapter reuses
  the public copier/codec with canonical live-tree confinement and backups;
  it reconciles only global skills, owned instructions, and disabled integrations.
  `deployment/disabled-skills.tsv` resources stay outside discovery and cannot
  return through an override library. The Graphify skill uses reviewed upstream
  bytes through `deployment/skill-layouts.tsv`; initialization remains explicit.
  Read `docs/AGENT_SETTINGS.md` when changing client settings, MCP registration,
  ownership, or preservation. Index creation stays an explicit project action.
- **The Magpie model gateway owns the credentials and the generated agent
  files**: the deployment owns the eight catalogs under `deployment/magpie/`
  (providers, models, groups, families, wiring, visible, picked, plugins), the release
  catalog `deployment/magpie/releases.tsv` that pins the native CLI version
  and its SHA-256 digests, Claude Code's hand-written settings, Pi's default
  provider and model, the bootstrap switch, and the Codex content guard. A
  group the deployment owns is written by the apply; a gateway route the
  deployment only offers is declared in `families.tsv` and named in the
  pickers under the id the gateway publishes, so a picker entry is always an
  id the gateway serves. The status reports a group the gateway does not
  publish, a group that holds a member the gateway does not serve, and a
  route the gateway does not publish as findings, and the apply measures the
  ChatGPT account's allowance before a group that drains it is wired. The
  macOS application is adopted when present; otherwise macOS, Linux, and WSL
  install the pinned native CLI the release catalog names. CLI lifecycle is
  explicit: the deployment
  starts `magpie serve`, writes no systemd unit, no login item, and no
  registry key, and never writes its temporary proxy into the gateway's own
  settings. Native Windows currently installs only the CLI; it does not wire a
  gateway or clients. Magpie owns the provider keys,
  the accounts, the usage store, Pi's generated `~/.pi/agent/models.json`, and
  DSH's Magpie route and compaction field; none of them is ever committed.
  Magpie's CLI owns the compaction field: the apply reads and sets it only
  through `dsh compact_model`, never by editing the DSH profile, and uses a
  fixed workhorse route independent of the group the DSH session's main
  wiring row names. The enabled, Magpie-owned DSH wiring row and any bootstrap
  DSH selection only gate whether the field is set, never its value. It backs
  up the previous value and fails closed on a getter it cannot parse rather
  than guessing. Live `status` reports the field as matched, drifted, or
  unreadable from what the CLI answers now, not from recorded intent. Rejected
  or unavailable routes fall back to the original request; runtime routing is
  not verified, only the field and its preservation.
  Codex's `~/.codex/config.toml` and `~/.codex/auth.json` stay device-owned:
  every apply guards both by their parsed content, so a configuration the
  device rewrote into another layout is the same configuration. When Codex is
  selected, the deployment may select `magpie codex scope profile` and wire
  only its separate `~/.codex/magpie.config.toml` and `magpie-models.json`. The
  credential-bearing profile is private before it is written and stays 0600;
  unrecorded files and symlink targets are preserved, not
  adopted. Plain `codex` retains its subscription configuration; `codex -p
  magpie` starts Magpie sessions. The managed `dotfiles-codex-resume` command
  is the way to resume a thread: it adds provider definitions only and keeps
  each thread's saved provider, model, and reasoning effort, and it needs
  Codex 0.169.0 or newer and a `python3` with the standard library's
  `tomllib`, because it refuses to read a provider definition it cannot
  parse. Resume must
  preserve a thread's saved provider, not retag sessions; read
  `docs/MAGPIE.md` for the verification boundary and
  `docs/adr/0015-neutral-codex-resume-layer.md` for the design.
  `magpie visible` narrows an
  agent and never ticks a star; `picked.tsv` is the star set, and the apply
  writes only the `pickedModels` key into Magpie's settings while preserving
  everything else. No code path runs `--only-picked`. A community plugin is
  pinned and installed, never signed in: the browser sign-in is the
  operator's. Read `docs/MAGPIE.md` before changing the
  catalogs, the switch, the apply, or the credential sources.
- **Caveman uses standalone skills**: bootstrap leaves gateway configuration,
  runtime state, and old merge baselines device-owned. Existing integrations
  retire through the focused migration in `docs/CAVEMAN.md`; read it before
  changing that migration or gateway ownership.

## CLI tools

Follow the task mappings and shell-specific rules in
[`deployment/agent-payload/AGENTS.md` → CLI tools](deployment/agent-payload/AGENTS.md#cli-tools).
Check the common/selected bundle catalogs and actual command availability;
retain POSIX/Bash 3.2 compatibility where this deployment boundary requires it.

## Existing-host audits

Accept installed tool versions newer than the repository pin. A newer version
alone requires no deployment alignment or downgrade and does not block restart.
Report older versions, missing commands, configuration drift, and demonstrated
incompatibilities separately. Keep installation pins unchanged during an audit.

## Known rough edges

- Nu's vendor autoload runs for interactive sessions and is omitted by ordinary
  `-c` execution. `dotfiles-shell-prepare` validates generated resources
  explicitly; interactive tests establish prompt/completion discovery.
- `.chezmoi.toml.tmpl` explicitly persists `sourceDir`; bootstrap passes source,
  destination, config, cache, and state paths on both init and apply.
- Legacy live tree (JSHELL) is still symlink-managed and ahead in places this
  source intentionally diverged from (portable paths, GLM-5.3, env_key
  secrets); when folding live changes in, adapt rather than copy verbatim.

## Commits

`[tag]: message`, lowercase imperative, one logical config area per commit,
body summarizing what drifted/changed. Tags in use: `chore`, `shell`, `bash`,
`nu`, `claude`, `agents`, `devops`, `direnv`, `conda`, `clash`.
