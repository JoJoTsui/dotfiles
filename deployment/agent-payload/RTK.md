# RTK

Use RTK's supported command wrappers to reduce verbose shell output, for example
`rtk git status`, `rtk cargo test`, or `rtk uv run pytest`. Check `rtk --help` for
supported wrappers. Run other commands directly or through `rtk proxy <command>`.
Prefix individual supported commands within a shell chain.

For content search, ensure RTK invokes the working `rg` on the managed PATH.
Run `fd` directly for discovery. Recheck commands on each device.

Filtered output is a summary. When exact source, complete diagnostics, or
machine-readable output matters, use the native command or `rtk proxy <command>`
for unfiltered output. Recover omitted output with `rtk recall <hash>` when RTK
provides a recovery hint.

Use `rtk gain` to inspect recorded savings. These instructions do not install
client hooks, rewrite commands automatically, or change command permissions.
