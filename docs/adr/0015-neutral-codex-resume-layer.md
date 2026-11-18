# The resume layer carries provider definitions only

A Codex thread records the provider, the model, and the reasoning effort it
ran with. Codex 0.169.0 restores those saved settings on resume unless a
*selection layer* names a model, a provider, or a reasoning effort: the
interactive TUI keeps `RestoreFromThread` when no such layer exists
(`tui/src/app/config_persistence.rs`, `resume_model_settings_for_overrides`),
and the app server then injects the thread's saved provider before it loads
the configuration and refuses a resume that would change it
(`app-server/src/config_manager.rs`, `load_for_resume`). The device therefore
needs one way to resume a thread of any provider without selecting one. We
chose a managed command that adds provider *definitions* only; we rejected
editing the base configuration, weakening Magpie's profile, and retagging
sessions.

## Considered Options

- **A separate resume profile file** (`$CODEX_HOME/<name>.config.toml`): the
  same shape as Magpie's own profile, but it is a second persistent file that
  carries a gateway credential into the device's Codex home and needs a
  collision, permission, and cleanup policy of its own.
- **Injecting the definitions into the base `config.toml`**: one file to read,
  but the base configuration is device-owned and hash-guarded; the deployment
  would write into a file it does not own and would change what plain `codex`
  does.
- **Weakening Magpie's profile so it stops selecting**: the profile selects on
  purpose. A profile that no longer selects is a second profile with a
  different name and the same ownership problem.
- **Rewriting each session's saved provider**: it would make every thread look
  like it came from the gateway, and it destroys the record the resume exists
  to restore.

## The decision

`~/.local/bin/dotfiles-codex-resume` (source
`dot_local/bin/executable_dotfiles-codex-resume`) runs
`codex resume --all --include-non-interactive` and adds a provider layer that
carries definitions only:

- The definitions come from Magpie's own `~/.codex/magpie.config.toml` at run
  time. The deployment never owns, copies, or persists that credential. The
  provider table reaches the child as command-line configuration overrides,
  and the credential reaches it through the environment with the provider's
  `env_key` mechanism, so it never enters argv, a file, a log, or this
  repository.
- The layer never sets `model`, `model_provider`, or `model_reasoning_effort`.
  A selection would switch Codex to `OverrideFromCurrentConfig` and defeat the
  preservation the command exists for.
- A base configuration that already defines `model_providers.magpie` wins: the
  device's own definition is left alone.
- The two files the command reads are refused when they are aliased, the way
  the deployment's Codex boundary refuses an aliased path: the command does
  not read through a link, it degrades to a plain resume with a message.
- Without a Magpie profile the command degrades to a plain resume and says so
  on stderr.
- `--model`, `--model-provider`, `-c model=…`, `-c model_provider=…`,
  `-c model_reasoning_effort=…`, and `--profile` are refused with a message
  that names the guarantee they would defeat. They are not ignored. The key
  of an override is compared the way Codex compares it, after trimming, so
  the spaced form is refused as well.
- The command needs Codex 0.169.0 or newer: below that release the app server
  required the saved provider to equal the provider of the current
  configuration, so a neutral layer alone was not enough. An older Codex is
  refused with a message that names both versions.

## Consequences

- A thread of the gateway and a thread of the subscription both resume
  through one command, each with its own saved provider, model, and reasoning
  effort. The synthetic run against two fake loopback providers shows the
  resumed turn reaching the thread's own endpoint with the thread's saved
  model and effort, and shows the two failures that the same run has to
  avoid: a saved-versus-requested provider mismatch and a provider that is no
  longer configured. The interactive picker path is proven on a pty-capable
  host; the runtime class that carries it is opt-in, because it needs the real
  Codex CLI and a pseudo terminal. The driver waits for the session list to
  load before it sends its Return: the picker renders its header and its
  footer while the list is still loading, and a Return sent in that state
  accepts no row. The driver sends no arrow key: the picker orders the list
  and highlights a row itself, so the check accepts the highlighted row and
  asserts on the thread that was actually resumed, whichever row it was.
- A turn produces more than one request at the provider. Codex sends a
  request of its own for the thread title, and that request carries the
  configuration's own reasoning effort. The check asserts on the request whose
  `prompt_cache_key` matches the thread's creation request, and records the
  auxiliary request separately. Every fake provider is searched for that
  request, because the picker may highlight a row of any provider and the
  turn of a thread of another provider reaches that provider's endpoint.
- `--all` covers every working directory and `--include-non-interactive` adds
  the resumable Exec/AppServer threads. Archived threads are not resumable and
  are documented, not promised. `codex exec resume` always sends resolved
  settings and is not a substitute.
- The command depends on the pinned Codex behaviour above. A Codex release
  that changes the selection rule needs its own verification.
- The credential reaches the child through the environment, so the shell
  commands the resumed agent runs inherit it, the same way the other
  `env_key` providers of the device already do. The command does not override
  `shell_environment_policy`: a merge would replace the device's own list
  instead of extending it.
- The layer carries no model catalog. A thread whose model the active catalog
  does not know — every Magpie group id — therefore runs with Codex's
  fallback model metadata, and Codex warns about it. The fallback changes
  the context window Codex assumes, the model-specific tool modes, and the
  web search tool; the saved provider, the saved model, and the saved
  reasoning effort still hold. The catalog is not carried: an explicit
  `model_catalog_json` resolves a model by its exact slug alone and replaces
  the active catalog for the whole process, so carrying it would take the
  model metadata away from the other threads resumed in the same run.
- The command is thin: no new package, no service, and no file outside the
  dotfiles source and the user's own Codex and Magpie state.
