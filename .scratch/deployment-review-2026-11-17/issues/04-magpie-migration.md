# 04: Gate and back up Magpie client migration

**What to build:** Client settings point to Magpie only after gateway readiness is established; disabled and partial deployment modes preserve usable client settings, and migration is recoverable.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Disabled, unavailable, and skipped gateway cases do not newly wire clients to an unavailable gateway.
- [ ] Original client settings are backed up before gateway migration changes them, preserving unrelated settings.
- [ ] Successful migration, failure, repeated deployment, and partial modes are covered through disposable-home behavior tests.

## Comments

Gateway-specific client settings are gated until the Magpie step. Bootstrap now snapshots the original client files before its first settings merge and uses that snapshot if migration needs a backup. The focused regression reproduces the merge and gateway sequence and confirms the original Claude and Pi bytes are backed up. A public bootstrap failure test confirms the temporary snapshot is removed. Apply-only tests pass. A full bootstrap migration and native macOS gate have not yet established end-to-end acceptance; this ticket remains open.
