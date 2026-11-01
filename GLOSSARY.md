# Dotfiles deployment

This context describes how one set of personal tools and settings is deployed
across devices with different platforms and purposes.

## Language

**Platform**:
The operating environment of a device: Linux, macOS, WSL, or native Windows.
_Avoid_: Host class, profile

**Host role**:
The primary purpose of a device, such as a workstation or a remote compute host.
_Avoid_: Platform, host class

**Deployment profile**:
A combination of platform and host role that selects the tools and settings for
a device.
_Avoid_: Host class

**Profile preset**:
A named choice of platform and host role for a common deployment.

**Shared shell history**:
One logical collection of commands entered across devices in Nushell, Bash, and
Zsh. Coding-agent conversations and sessions are outside this term.
_Avoid_: Shared history, agent history

**Shared shell settings**:
The environment values and interactive behavior intended to agree across the
shells available in a deployment profile.

**Common defaults**:
The portable tools and settings selected by default for every supported device.

**Tool bundle**:
A selectable group of specialist tools added to the common defaults, such as
bioinformatics, GPU, or desktop tools.

**Shared agent instructions**:
The personal operating rules that apply to coding agents across projects and
devices. A project's own instructions describe that project's separate contract.

**Simulated home**:
A disposable home used to validate a deployment without changing the current
device's home or settings.

**Native validation**:
Verification of a deployment using its target platform's actual runtime.

**Account shell**:
The program recorded in the account database for a login session. It is not
necessarily the interactive shell a TTY ends up running.
_Avoid_: Login shell

**Interactive login shell**:
The shell a TTY login actually runs after the account shell's startup guard; it
may replace itself with another shell.
_Avoid_: Login shell, pane shell

**Pane shell**:
The default command a terminal multiplexer starts in a new pane.
_Avoid_: Login shell, agent shell

**Agent tool shell**:
The client-owned shell an agent uses for tool commands, independent of the pane
shell.
_Avoid_: Pane shell, login shell
