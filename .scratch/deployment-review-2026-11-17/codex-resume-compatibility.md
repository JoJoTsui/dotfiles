# Codex mixed-provider resume: compatibility evidence

Date: 2026-11-18
Status: source-backed; both-version runtime comparison pending in ticket 10

## Repository pin versus installed runtime

The installation provider catalog currently names Codex 0.166.0 (Homebrew floor and Bun exact package). The installed runtime reports `codex-cli 0.169.0`. No pin has been changed during this investigation.

Both sources choose `RestoreFromThread` when neither harness overrides nor a selected profile/session layer supplies model, model_provider, or model_reasoning_effort:

- [0.166.0 config_persistence.rs, lines 31–54](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/tui/src/app/config_persistence.rs#L31-L54)
- [0.169.0 config_persistence.rs, lines 31–54](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/tui/src/app/config_persistence.rs#L31-L54)

The server validation differs materially:

- [0.166.0 config_manager.rs, lines 538–618](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server/src/config_manager.rs#L538-L618) loads `current_provider` from the latest config before applying saved-provider resume overrides. It then requires both the saved and requested providers to equal that current provider. Thus a neutral provider-definition layer alone appears insufficient when the saved thread uses another provider. This is a source-traced incompatibility, not yet a captured runtime failure.
- [0.169.0 config_manager.rs, lines 521–594](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/app-server/src/config_manager.rs#L521-L594) records any explicit requested provider, injects the saved provider as a typesafe override before loading, validates that saved/requested providers exist and satisfy policy, and rejects an actual saved-versus-requested mismatch. It no longer enforces the old unrelated current-config-provider equality.

## Consequence for ticket 10

Prove behavior using two synthetic providers/threads and actual interactive resume, on both the repository pin and installed version. If the older pin fails, preserve that failure as evidence and obtain explicit authority to update its catalog/frozen lock. Do not silently claim a local 0.169.0 test proves the deployment pin or implement a custom session picker/retagging workaround without agreement.

Primary files were fetched as public source only, not executed. Local read-only copies:
- `/tmp/dotfiles-codex-166-source.BRpMUs/`
- `/tmp/dotfiles-codex-source.svew9Q/`

The earlier primary-page summarizer returned a Kimi quota error; these files were fetched directly from the owning public repository instead. That research-tool error is not a Pi quota result and does not authorize the requested OpenCode fallback.

## Update (2026-11-19)

The catalog pin, the frozen lock, the registry digests, the tests, and the docs now carry Codex 0.169.0 (commit `1aa75c9`), after the user directed the version directly. The two-version runtime comparison is therefore no longer a version gate; it stays as ticket 10 acceptance evidence for the 0.169.0 mixed-provider resume behavior. The 0.166.0 server-side difference recorded above (saved provider must equal the current config provider) stays historical: it explains why a neutral provider-definition layer alone is sufficient on 0.169.0 and was not on 0.166.0.

A full 0.169.0 source tree is available read-only at `/tmp/codex-1690-src/codex-rust-v0.169.0/` for the ticket 10 implementation.
