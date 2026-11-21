# 01: Preserve agent records on a narrow apply

Status: done
Blocked by: None (can start immediately)

## What to build

Run a full apply followed by a one-agent apply on an existing simulated home. Keep the records for every agent outside that run's selection on both adapters.

## Acceptance criteria

- [x] Portable PowerShell reproduces full → narrow state loss before the fix. Native Windows preserves the original rows after the fix, and the Unix regression scenario still passes.
- [x] The latest successful selected result replaces its prior row without duplicates. An unsuccessful selected install cannot publish an unverified observation.
- [x] A missing ledger and the existing ledger format remain usable. Verify via public apply and status. Run the existing Windows workflow at the tested revision or report the native gate pending.

## Comments

Portable PowerShell reproduced the dropped row before the fix and passed full-to-narrow, selected replacement, and failed-install preservation after it. Both simulated Unix profiles passed. The existing Windows workflow carries the native regression; keep native parity open until that runner executes it.

Native Windows acceptance passed at `9352f8a08ee27673b1931c823cededbb98d59048` on x86-64 Windows with PowerShell 5.1. The workstation, remote-compute, and desktop plus developer-portable jobs each ran 79 tests with one standalone Nushell fixture skipped. All three artifacts record passing full-to-narrow state and status and targeted repair and preservation scenarios. The pre-fix reproduction used portable PowerShell. [Native Windows run](https://github.com/JoJoTsui/dotfiles/actions/runs/44874276890)
