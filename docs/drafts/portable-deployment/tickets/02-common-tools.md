# 02: Install common tools through managed installers

**Parent:** [Portable deployment specification](../spec.md)

**What to build:** A Linux user bootstraps the pinned common toolchain into the
selected user environment and can invoke its exposed commands immediately.
Pixi is installed first, required tools have one managed source, and specialist
packages do not determine whether the common deployment succeeds.

**Blocked by:** 01 — Resolve and apply an isolated Linux deployment.

**Status:** Implemented. Isolated Linux x86-64 execution and declared foreign
package resolution passed; native foreign/ARM execution remains separate work.

- [x] Default bootstrap installs Pixi, uv, Bun, a compatible Node runtime, Nushell, Zsh, Bash, RTK, Atuin, zoxide, Tailspin, and Tailspin's pager on supported Linux targets.
- [x] RTK and Tailspin are Pixi-managed and expose their standard commands; configuration-referenced common commands are installed by the manifest or a declared bootstrap step.
- [x] uv and pip discover the TUNA mirror settings in the rendered Linux environment.
- [x] Core and specialist inventory is distinguished; an ordinary common install does not install bioinformatics, GPU, or desktop bundles.
- [x] Required versions are pinned, locks are used where supported, and declared runtime engine ranges are compatible.
- [x] Tool paths resolve to the selected managed roots rather than legacy executable directories; rerunning bootstrap preserves unrelated installations.
- [x] Required download/install failures return nonzero with the failed step; no completion message represents a failed install as successful.
- [x] Controlled plan/failure tests and actual isolated Linux install/diagnostic checks report separate results, with foreign-target resolution distinct from native execution.

Evidence is recorded in [common-tool verification](../../../verification/common-tools.md).
Full bootstrap completion still awaits ticket 04's agent stage. Common success
before that deliberate failure is recorded independently, without a full
deployment completion message. Initial Linux glibc >=2.28 and macOS >=13 are
the selected Bun/Node package requirements; older hosts are not claimed tested.
