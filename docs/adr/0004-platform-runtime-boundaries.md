---
status: accepted
---

# Distinguish simulated deployment from native runtime validation

The current Linux compute host will validate every profile through isolated
rendering, configuration checks, and package-resolution checks, and execute the
applicable Linux shells. Native macOS and Windows execution belongs on native
CI runners: overriding template data leaves the Linux runtime in place and
cannot establish native installer or binary behavior.

Native Windows will use Nushell as its primary shell and Git Bash for agent
subprocesses. WSL provides the full Nushell, Bash, and Zsh environment; native
Windows does not promise the same three-shell installation.

References: [chezmoi template overrides](https://www.chezmoi.io/reference/command-line-flags/common/),
[native CI runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
and [Kimi Code's Windows shell requirement](https://moonshotai.github.io/kimi-code/en/guides/getting-started).
