# 06. Verify deployment through native adapters

**What to build:** Compare public deployment plans and record what each native verification run actually established.

**Blocked by:** None to start. Final acceptance exercises the integrated changes from 01–05.

**Status:** ready-for-human

- [x] The portable check calls the public platform adapters, compares shared plan fields, and verifies platform-specific tools and steps independently.
- [x] Version override fixtures derive defaults from the current catalog. Simulated bundle verification respects the live-only Magpie guard.
- [x] Native verification reports identify the checkout and the outcome of each scenario. Skips have a reason, and an unavailable runner does not count as acceptance.
- [ ] Run the relevant simulated and native scenarios against the integration revision. Record failed or unrun checks with the reason.

## Comments

### Integrated verification

The final verifier group, public plan matrix, simulated applies, and earlier Apple silicon gate passed within the scope recorded in the spec. Native Windows acceptance remains open.
