# 12: Integrate and verify

**What to build:** Integration and evidence. Run the public bootstrap in
disposable simulated homes shaped like macOS and Linux, extend the native macOS
verifier for the provider and PATH behaviour, run the skill check and record its
output, and capture the before/after effective provider for the current device.
Update the README and deployment docs so the provider chain, Herdr trigger, and
skill ownership are discoverable, and cross-link the ADRs. No real-home apply.

**Blocked by:** 02, 03, 04, 07, 08, 09, 10, 11.

**Status:** done

- [x] A simulated macOS apply succeeds and shows Homebrew-first providers and the macOS PATH order.
- [x] A simulated Linux apply succeeds and keeps the Bun-first order.
- [x] The native macOS verifier covers provider resolution, launcher targets, and PATH order, and passes.
- [x] The skill check output is recorded with the per-client inventory and ratchet result.
- [x] Before/after effective providers for the current device are recorded without applying to the real home.
- [x] README and deployment docs name the provider catalog, Herdr step, and skill ownership, and link the three ADRs.
- [x] Every new failure mode has a regression test; skips are documented with their reason.

## Comments

Verification is recorded in `docs/verification/agent-stack-unification.md` with
the native macOS report beside it. The native gate passed on commit `7dc9911`
with a clean tree; both simulated applies exited 0; the Windows boundary ran 30
tests (2 native-runner skips); the full suite's 42 failures/errors are the
identical pre-existing macOS host-scope set; the skill check reports 54 automatic
/ 46 tagged, 17 reviewed exceptions, no ratchet failures, and 37 disabled CLI-lock
entries. No account-home application was performed.
