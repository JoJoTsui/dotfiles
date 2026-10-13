# 07: Enable shared shell history and deliberate device setup

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** Commands entered in supported shells use Atuin history by
default, remain usable offline, and synchronize through hosted encrypted sync
after deliberate device activation. Setup offers optional one-time import of
existing history from each available shell and clearly distinguishes installed
integration from activated sync.

**Blocked by:** 03 — Deliver shared Nushell-first shell behavior.

**Status:** Implemented; isolated Linux acceptance passed. Native execution
continues in platform tickets 09–11 and the final matrix.

- [x] Atuin hooks and hosted encrypted sync settings deploy by default in supported Nushell, Bash, and Zsh adapters.
- [x] Local command history and search work before login and while offline; sync activation status is visible and pending activation does not masquerade as a synced device.
- [x] Device setup supports first-device setup and joining the same account/encryption key, keeping those values outside source control and logs.
- [x] Ordinary bootstrap does not log in, create a real account, read existing device history, or import it automatically.
- [x] Setup offers explicit one-time import from each available shell, including Nushell's applicable text or database importer; automatic single-shell detection is not presented as an all-shell import.
- [x] Built-in secret filtering remains enabled; synthetic recognized credentials exercise exclusion, with native-shell filtering limitations documented accurately.
- [x] Coding-agent conversations, sessions, credentials, and trust state remain outside shared shell history.
- [x] Synthetic command/import fixtures and isolated sync credentials/endpoints verify recording, search, offline operation, activation, import choice, and sync behavior without uploading real device history.

Evidence: [shared history setup](../../../SHARED_HISTORY.md) and
[isolated Linux checks](../../../verification/shared-history.md). Native Windows
console masking, Nu discovery and write isolation require its ticket 11 adapter;
Linux rendering does not establish those behaviors. Atuin 18.23's hosted browser
flow is documented but a real account was intentionally not activated.
