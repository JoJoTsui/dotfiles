# Preserved optional inventory

`legacy-pixi-global.toml` retains the previous 106-environment inventory, with
Codex's former entry replaced by its migration note. Codex has one repo-owned
installation source, Bun. `legacy-bun-package.json` preserves the prior client
and Lark CLI inventory for its Bun migration. These files are historical input
to the selectable inventory work, not manifests applied over a device registry.

Common defaults are declared in `../common-tools.tsv`. The remaining inventory
belongs to opt-in bundles: bioinformatics (the 14 Bioconda environments), GPU
(`nvtop`), desktop (`zed`, `firefox`), and developer tools. Ticket 08 supplies
their exact pins and supported targets. The developer inventory includes
secondary language/toolchain managers and optional multiplexers such as `fnm`,
Zellij, and Herdr. Managed Node replaces automatic fnm initialization.

Preserve bootstrap-only ownership as well: gping 1.21.0's earlier Linux release
installation, Rust compiler/toolchain setup, Lark CLI, and Headroom's optional
local service. Rustup itself is now a pinned common manager installed without
a default toolchain; `cargo`/`rustc` use requires deliberate toolchain setup.
Headroom's MCP is disabled until its optional capability is configured.

Common deployment does not install these specialist tools or enable their
dependent configuration. Selecting fewer tools must preserve existing device
installations; changes to owned entries merge with the device's registry.
