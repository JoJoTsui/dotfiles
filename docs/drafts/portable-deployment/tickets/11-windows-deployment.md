# 11: Deliver the common environment on native Windows

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A native Windows x86-64 user selects workstation or remote
compute and receives Nushell, Git Bash for subprocesses, common tools, all five
agents, portable instructions/skills, CodeGraph integration, and Atuin history.
Pinned user-scoped installer exceptions close the Windows package gaps.

**Blocked by:** 06 — Configure CodeGraph access without automatic indexing;
07 — Enable shared shell history and deliberate device setup.

**Status:** Draft awaiting review; publish as ready-for-agent after approval.

- [ ] Native Windows detection, explicit selection, and both roles produce correct native home/configuration/tool paths; Windows ARM is rejected as outside the initial target matrix.
- [ ] Pixi installs supported required packages, including RTK, uv, Nushell, zoxide, Tailspin, and the compatible Node runtime.
- [ ] Pinned upstream Windows steps install Bun and Atuin where conda-forge has no native package; Git Bash provides the required agent subprocess environment.
- [ ] All five agents install through Bun and run harmless native diagnostics; Kimi Code finds its supported Git Bash subprocess shell.
- [ ] Nushell is the primary managed interactive shell, Git Bash retains its appropriate role, and the full Nushell/Zsh/Bash promise is reserved for WSL.
- [ ] Native uv/pip discover TUNA configuration, and zoxide, Tailspin logs, and applicable Atuin hooks/setup work in the available managed shells.
- [ ] All clients discover portable real-file instructions/skills and supported CodeGraph configuration without automatic indexing or overwriting unrelated client state.
- [ ] User-scoped bootstrap/reapplication preserve credentials and history; required installer failure propagates and account activation pending is reported distinctly.
- [ ] Native Windows runner tests exercise these behaviors; Linux render/plan success is not represented as native Windows execution.
