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

**Manager pin**:
The version and per-target release digests of one bootstrap manager, treated as
a single value. A version without matching digests is not a pin.
_Avoid_: Version, version pin

**Shared shell history**:
One logical collection of commands entered across devices in Nushell, Bash, and
Zsh. Coding-agent conversations and sessions are outside this term.
_Avoid_: Shared history, agent history

**Shared shell settings**:
The environment values and interactive behavior intended to agree across the
shells available in a deployment profile.

**Common defaults**:
The portable tools and settings selected by default for every supported device.

**Full default deployment**:
The complete baseline environment selected by a deployment profile, including
common tools, coding agents, shared shell settings, instructions, and skills.
Optional tool bundles and account or system changes are separate selections.
_Avoid_: All optional tools, system setup

**Tool bundle**:
A selectable group of specialist tools added to the common defaults, such as
bioinformatics, GPU, or desktop tools.

**Installer**:
A mechanism that provides a command to a deployment: Homebrew, a Pixi
environment, or a native release.
_Avoid_: Manager, package manager

**Installer order**:
The per-platform sequence that decides which installer provides a command the
device does not have.
_Avoid_: Install priority, tool priority

**Adopted command**:
A command the device already provides, used as it is and never reinstalled.
_Avoid_: Provisioned command

**Provisioned command**:
A command the deployment installed through an installer.
_Avoid_: Adopted command

**Shared agent instructions**:
The personal operating rules that apply to coding agents across projects and
devices. A project's own instructions describe that project's separate contract.

**Global agent integration**:
Skills and guidance available to a coding agent across projects on one device.
It does not imply that a particular project has been initialized.

**Project initialization**:
The deliberate creation of a tool's working state for a selected project.
It is separate from making the tool available to coding agents.

**Disabled integration**:
An integration unavailable to agent discovery and automatic invocation, with
its previous configuration and resources retained so it can be restored.

**Simulated home**:
A disposable home used to validate a deployment without changing the current
device's home or settings.

**Native validation**:
Verification of a deployment on its target operating system and processor
architecture without processor emulation.

**Container validation**:
Verification of a deployment within a disposable container. The container's
operating environment and execution limits are part of the result.

**Emulated validation**:
Verification of a deployment while its target processor architecture is
translated. The result establishes behavior under that translation.

**T9K profile**:
The Linux remote-compute deployment used for T9K. It is distinct from the legacy
T9K installation and that device's existing state.

**Deployment match**:
Agreement between a device item and the selected deployment's declared version,
content, or behavior. Exact agreement is distinct from a compatible difference.

**Intentional legacy adaptation**:
A device-specific difference retained deliberately for an existing installation.
It is documented separately from accidental deployment drift.

**Migration rehearsal**:
Verification of a deployment starting from an existing device's configuration
and preservation constraints.
_Avoid_: Fresh installation, live application

**Deployment step**:
One named stage of a bootstrap run, such as installing managers or applying the
source. A step that fails ends the run; a step that has nothing to do succeeds.

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
_Avoid_: Login shell

**Agent tool shell**:
The client-owned shell an agent uses for tool commands, independent of the pane
shell.
_Avoid_: Pane shell, login shell

**Script shell**:
The managed shell a launcher keeps for script arguments and agent entry points:
Bash on Linux and WSL, Zsh on macOS.
_Avoid_: Agent tool shell, Pane shell, Login shell
