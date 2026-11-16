# 12: Integrate and verify

**What to build:** Integration and evidence. Run the public bootstrap in
disposable simulated homes shaped like macOS and Linux, extend the native macOS
verifier for the provider and PATH behaviour, run the skill check and record its
output, and capture the before/after effective provider for the current device.
Update the README and deployment docs so the provider chain, Herdr trigger, and
skill ownership are discoverable, and cross-link the ADRs. No real-home apply.

**Blocked by:** 02, 03, 04, 07, 08, 09, 10, 11.

**Status:** ready-for-agent

- [ ] A simulated macOS apply succeeds and shows Homebrew-first providers and the macOS PATH order.
- [ ] A simulated Linux apply succeeds and keeps the Bun-first order.
- [ ] The native macOS verifier covers provider resolution, launcher targets, and PATH order, and passes.
- [ ] The skill check output is recorded with the per-client inventory and ratchet result.
- [ ] Before/after effective providers for the current device are recorded without applying to the real home.
- [ ] README and deployment docs name the provider catalog, Herdr step, and skill ownership, and link the three ADRs.
- [ ] Every new failure mode has a regression test; skips are documented with their reason.
