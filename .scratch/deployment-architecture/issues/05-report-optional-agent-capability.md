# 05: Report the optional native dependency by client impact

Status: done
Blocked by: None (can start immediately)

## What to build

Use the Ubuntu 20.04 baseline to report whether the optional better-sqlite3 failure affects a supported operation in the relevant selected clients.

## Acceptance criteria

- [x] Exercise a representative affected operation where the fixture permits it. Record package presence and client behavior separately. Record which affected clients were actually selected.
- [x] A measured optional loss is degraded. An unavailable probe is unverified with a reason. A successful unaffected operation records its observed scope. Required failures still fail.
- [x] The deployment evidence surfaces the outcome without reading Bun's warning manually. No new required compiler or package is assumed.

## Comments

MiniMax Code 0.7.9 reported its version on both emulated Ubuntu fixtures. In a clean offline home, ACP initialization was degraded on Ubuntu 20.04 with a present package and missing native binding. ACP initialized successfully on Ubuntu 24.04 with the binding present. The report records the scope and distinguishes operation failure from unavailable evidence.
