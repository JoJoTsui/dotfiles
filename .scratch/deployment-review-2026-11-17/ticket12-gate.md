# Ticket 12 gate sequence (supervisor, prepared 2026-11-19)

Run in order against the integration tip after ticket 10 is merged. Every
command records its exit status; a skipped check is reported as skipped, never
as a pass.

## 0. Preconditions

- Integration tip is `fix/deployment-review` with ticket 10 merged.
- `git status` shows only the untracked `.scratch/` tracker.
- Host: macOS 15.8.1, arm64, chezmoi, codex 0.169.0, python3 3.15.2.

## 1. Review (standards and spec)

- Standards review against `AGENTS.md`, `README.md`, `GLOSSARY.md`,
  `docs/adr/`, and the completion checkpoint, in the repository's code-review
  shape (two axes, side by side).
- Spec review against `.scratch/deployment-review-2026-11-17/spec.md` and
  `issues/09`–`issues/12`.
- Fix every verified finding through the implementer; rerun the affected
  checks. No unfinished blocker becomes a pass.

## 2. Deterministic checks

```bash
DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) python3 -m unittest discover -s tests -v
/bin/bash -n deployment/magpie.sh
/bin/bash -n dot_local/bin/executable_dotfiles-codex-resume
git diff --check
```

- ShellCheck and shfmt are not installed: report them as skipped.
- The Linux-only suite fails by design on macOS (native-platform detection,
  the Windows matrix, the Linux bring-up helper); run the macOS gate instead
  and report the scope, not a regression.
- Pre-existing on this host at the base commit `1aa75c9`, measured by the
  supervisor: `python3 -m unittest tests.test_deployment tests.test_agent_herdr
  tests.test_host_up` → 32 tests, **16 failures + 1 error** (the last one:
  "FAIL codex app-server daemon / host bring-up stopped at ensure_codex;
  Herdr restore withheld"). The same counts were reported by the ticket 10
  implementer at the same commit, so they are host scope, not a regression.
  The new `tests/test_codex_resume.py` adds to the deterministic suite:
  `python3 -m unittest tests.test_codex_resume -v` → 22 unit tests run, 10
  runtime tests skipped without the opt-in.

## 3. Simulated homes (both documented profiles)

```bash
simulated_home=$(mktemp -d /tmp/dotfiles-sim.XXXXXX)
DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh \
  --source "$PWD" --home "$simulated_home" --class t9k --apply-only
# fresh home for the ignore branch
simulated_home_linux=$(mktemp -d /tmp/dotfiles-sim.XXXXXX)
DOTFILES_CHEZMOI_BIN=$(command -v chezmoi) bash bootstrap.sh \
  --source "$PWD" --home "$simulated_home_linux" --class linux --apply-only
```

- Check `~/.local/bin/dotfiles-codex-resume` landed as a regular file with
  mode 0755 in both homes.
- Check the rendered values with `rg`; confirm the required files are regular
  files; delete the simulated homes after the checks.

## 4. Native macOS gate (fresh, stable source)

```bash
python3 tests/native_macos.py --arch aarch64 --role workstation \
  --agents kimi,pi,opencode,claude,codex,minimax,qoder \
  --report /private/tmp/dotfiles-native-macos.json
```

- Record the revision/fingerprint, the selected agents, the runtime, the
  counts, and the exclusions. The gate excludes the account Magpie wiring and
  cannot prove inference.

## 5. Existing-device rehearsal (approved redacted projection)

```bash
python3 deployment/rehearse_settings.py \
  --source-home "$HOME" \
  --manifest deployment/rehearsal/existing-mac-inputs.tsv \
  --projection /private/tmp/dotfiles-rehearsal \
  --report /private/tmp/dotfiles-rehearsal-report.json
```

- Both output paths must be new; the projection must live outside the account
  home; no raw credential or session enters a hosted tool. Report paths and
  counts only.

## 6. Headless Linux preparation

- The native Linux gate is `python3 tests/native_linux.py --home … --agents
  kimi,pi,opencode,claude,codex,minimax,qoder --execution native`.
- It requires an authorized native Linux x86_64 host. On macOS it fails
  before any installation: report the command as prepared, not as a pass.

## 7. Protected application to the account home

- Only after steps 1–6 pass.
- Protect the affected configuration files and symlinks (a copy with recorded
  hashes), then recheck the device's drift, then run the authorized public
  bootstrap once.
- A real interruption of the active client transport pauses for a separate
  user decision; serialization-only churn must not interrupt it.

## 8. Live verification

- Live managed versions, configuration and discovery, history compatibility,
  gateway health, provider and group routes, the new-session profiles, and
  provider-preserving resume as far as it can go without reading real
  conversations.
- Report model-list discovery, actual inference, and classifier runtime proof
  separately.

## 9. Cleanup

- Merge or commit the worktree's tracked changes, tag the archive, inventory
  untracked and ignored files, then remove only the worktrees this task
  created (`git worktree remove` without `--force`). Never remove a worktree
  the user is using.
