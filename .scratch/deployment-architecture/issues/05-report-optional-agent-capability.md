# 05: Report the optional native dependency by client impact

Status: ready-for-agent
Blocked by: None (can start immediately)

## What to build

Use the Ubuntu 20.04 baseline to report whether the optional better-sqlite3 failure affects a supported operation in the relevant selected clients.

## Acceptance criteria

- [ ] Exercise a representative affected operation where the fixture permits it. Record package presence and client behavior separately. Record which affected clients were actually selected.
- [ ] A measured optional loss is degraded. An unavailable probe is unverified with a reason. A successful unaffected operation records its observed scope. Required failures still fail.
- [ ] The deployment evidence surfaces the outcome without reading Bun's warning manually. No new required compiler or package is assumed.

## Comments
