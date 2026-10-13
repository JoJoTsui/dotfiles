---
status: accepted
---

# Synchronize shell history through hosted Atuin

Shared shell history covers Nushell, Bash, and Zsh commands across devices.
Atuin's hosted encrypted sync will provide that collection while each device
retains local history for offline use, avoiding file synchronization of a live
history database. Integration is deployed by default; device activation uses
the same account and encryption key, kept outside the dotfiles source state.

The hosted service was selected over operating a private server for the initial
deployment. See [Atuin's sync guide](https://docs.atuin.sh/main/guide/sync/) for the
account and key requirements.
