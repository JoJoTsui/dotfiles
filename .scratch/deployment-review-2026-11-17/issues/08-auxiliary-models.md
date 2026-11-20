# 08: Model roles and auxiliary routing

## Outcome

DSH and DSH TUI deployment and routing work are deferred under the current
scope. Their existing device state must be preserved; the acceptance items
below remain future work where they concern DSH.

Use the conductor tier for planning, organization, supervision, and direction;
use the workhorse tier for bounded lightweight work where the client supports
that routing. Keep the permission classifier independently configured and
verify it with benign requests rather than inferring accuracy from a 200.
Subagents should not be made stronger than their parent by a global default.

## Acceptance

- Consider Claude Code, Codex, Pi, OpenCode, Kimi, DSH, DSH TUI, MiniMax Code,
  and Qoder. Identify session, worker, classifier, summary/compaction, title,
  and progress routing where each installed version actually supports it.
- Use parent inheritance where no safe per-role worker selection is available;
  preserve conductor for supervisors. Configure DSH's supported compaction
  override to `group/workhorse`, independently of the DSH session's main model,
  while reporting the gateway's fallback to the original model if that route is
  unavailable. Status must report a drifted compaction setting rather than
  echoing recorded intent. Test the client loader and observable requests in
  isolated fixtures, not merely the spelling of a setting.
- A static worker selection is not a dynamic parent ceiling. Explicit model
  overrides, fixed-model built-ins, gateway fallback and unknown client paths
  must be reported rather than represented as enforced hierarchy.
- Honor ownership boundaries: Codex's config and auth remain device-owned;
  do not copy credentials or replace official client provider configuration.
- Preserve the active gateway until a real migration is ready, and separately
  report failures, unavailable models, untested paths, and restart needs. For
  Claude, the old managed `group/conductor` subagent default must be retired
  only when the previous managed baseline still owns that exact value; the
  ordinary pre-gateway merge currently replaces the baseline, so migration must
  retain the pre-merge baseline without disturbing device overrides.

## Research notes

Claude documents subagent model precedence and the separate auto classifier;
Pi compaction normally uses the session model; OpenCode's internal compaction
agent can have a model but native provider compaction uses the session model;
Claude's documented `ANTHROPIC_DEFAULT_HAIKU_MODEL` also controls background
functionality, while `ANTHROPIC_SMALL_FAST_MODEL` is deprecated. The partial
source routes both to Terra, and its gateway drift checker now checks those
aliases and the classifier while preserving device subagent overrides. The
253-test Magpie suite passed with the compaction changes on macOS using
synthetic fixtures; live background routing remains unverified.
No dedicated Claude compaction-model selector was found in the documented
environment variables.
Kimi has a secondary model pool; DSH has plugin-specific subagent, compaction,
and title controls; MiniMax exposes a light model for some auxiliary work;
Qoder CLI defaults custom agents to inheritance. Pinned Magpie upstream can
integrate OpenCode, Kimi, MiniMax, and Qoder, but this repository deliberately
leaves their official configurations device-owned. Upstream's OpenCode V2
migration handles a separate title model, Kimi supports a subagent pool, and
MiniMax's integration recognizes light-model fields without exposing a separate
selector. These integrations do not establish a dynamic child-strength ceiling.
The installed Magpie CLI also
exposes `magpie dsh compact_model`: its gateway recognizes DSH compaction and
can redirect it to a model or group independently of the profile. If that route
is unavailable or disallowed, compaction falls back to the requested model;
therefore the configured override alone does not prove a cheaper request. The
pinned upstream setter accepts `group/workhorse`, and its gateway applies the
override only to requests classified as DSH compaction. An unavailable, disabled,
or disallowed route is left unchanged. The current source sets that override
independently of the DSH session group and checks the live field for drift;
focused fake-gateway tests cover those behaviors. Actual compaction requests,
other clients' auxiliary routes, and a dynamic child-strength ceiling remain
unverified.

The installed pinned pair had two independently reproduced headless failures.
With an isolated home, `dsh-tui cli capabilities --json` exited 3 because it
could not resolve the managed `dsh` shell launcher. Commit `f4410d1` repairs
Unix launcher discovery: synthetic launchers exercising the installed packages
now report DSH `0.2.2-rc.1` for both `dsh-tui` and `dst`. The agent test module
ran 14 tests with 3 skips. The compatibility gate remains: capabilities report
that DSH version as unvalidated, and `dsh-tui run` exits 3 with
`ADAPTER_UNAVAILABLE` before starting DSH. The installed TUI `0.20.1` adapter
validates releases only through `0.2.1-rc.5`; current upstream main has the same
allowlist. No model request was sent. This blocks headless DSH TUI acceptance
even if profile routing is repaired; do not bypass the upstream version gate or
downgrade a device silently. Native
acceptance currently checks only command versions, so it must also check the
headless adapter's reported runtime compatibility before claiming the pair works.
Commit `f94c12a` adds an adapter capability report to the macOS native gate,
separate from installation success. An isolated probe through a synthetic launcher
and the installed packages returned `unvalidated` for DSH `0.2.2-rc.1`; the
verifier and installer test modules ran 19 tests with one network-install skip.
The complete native macOS gate has not yet been rerun against this change.
Commit `ca8fe17` adds the same adapter verdict to the native Linux gate using a
shared classifier. The Linux and macOS verifier modules and macOS cache module
ran 49 tests with no skips; a synthetic Linux-probe invocation on this Mac
reported the installed pair as `unvalidated`. Native Linux acceptance itself
has not run.

The documented `dst dsh` native passthrough is separate from `dst run` and does
not enforce the automation adapter's allowlist. In a synthetic home,
`dsh-tui dsh --profile headless --help` exited 0, establishing launcher
resolution and native help only; it sent no model request and did not establish
profile initialization or Magpie routing. Pinned upstream Magpie source has an
automatic reconciliation path for empty profiles when a wired profile and a
nonempty model catalog are present. Its timing and the installed client's actual
headless route remain unverified. A read-only Pi assessment outlined a synthetic
headless request to an ephemeral local fake gateway; it would not establish the
real Magpie route or validate `dst run`.

Sources: <https://code.claude.com/docs/en/sub-agents>,
<https://code.claude.com/docs/en/permission-modes#choose-the-classifier-model>,
<https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/compaction.md>,
<https://opencode.ai/docs/agents/>,
<https://moonshotai.github.io/kimi-code/en/configuration/config-files>,
<https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/compaction/compaction-basic/README.md>,
<https://github.com/MiniMax-AI/minimax-code/blob/main/packages/config/src/config.ts>,
<https://docs.qoder.com/cli/subagent>,
<https://github.com/ccch1mneyyy/dsh-TUI/blob/main/cli/adapters/dsh/index.mjs>,
<https://registry.npmjs.org/%40deepseek-harness-tui%2Fdsh-tui/latest>,
<https://github.com/yetone/magpie/blob/v0.1.4404/internal/provider/dsh_compact.go>,
<https://github.com/yetone/magpie/blob/v0.1.4404/internal/gateway/dsh_compact.go>,
<https://github.com/yetone/magpie/blob/v0.1.4404/internal/agent/opencode_v2.go>,
<https://github.com/yetone/magpie/blob/v0.1.4404/internal/agent/kimi_secondary.go>,
<https://github.com/yetone/magpie/blob/v0.1.4404/internal/agent/minimax.go>.
