---
status: accepted
---

# Run Zsh on macOS instead of Bash

The shell is part of a deployment profile, not a per-device preference. macOS
therefore runs Zsh: the profile applies no Bash startup file, installs no
managed Bash runtime, and manages `~/.zprofile` as the Zsh login file. Linux and
WSL keep both shells.

Zsh never reads `~/.profile`, so the Zsh login file has to exist on its own.
`~/.zprofile` delegates to the same POSIX login file as Bash, which keeps one
owner for the shared environment and the Nu guard. macOS's `/etc/zprofile` runs
`path_helper` after `~/.zshenv` has set PATH, so the managed tool paths are
applied again from the login file and keep the front of PATH.

This replaces treating Bash as the everywhere shell and Zsh as an extra, which
left macOS hosts with startup files nothing read and a PATH that the system
profile reordered.
