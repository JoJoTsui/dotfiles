#!/usr/bin/env bash
# Finish the checks that the 2026-11-19 classifier outage kept from running.
#
# It is safe to run more than once. Every step prints its own status, a step
# that fails does not stop the ones after it, and nothing is pushed.
set -uo pipefail

repo=/Users/joey/SHELL/dotfiles
scratch="$repo/.scratch/deployment-review-2026-11-17"
cd "$repo" || exit 1

printf '=== 1. the worktrunk plugin test (ticket 17) ===\n'
if python3 -m unittest tests.test_worktrunk -v 2>&1 | tail -12; then :; fi
printf -- '--- committing the fix when the test is green ---\n'
if python3 -m unittest tests.test_worktrunk >/dev/null 2>&1; then
    git add tests/test_worktrunk.py
    git commit -F - <<'EOF'
[agents]: isolate the worktrunk plugin test from the device's own CLI

The plugin step resolves wt from the managed tool directory before the Pixi
one, so the ambient DOTFILES_COMMON_BIN pointed the test at the device's
real worktrunk. The stub that records the calls never ran, and the test
failed without exercising the step.

The harness now points DOTFILES_COMMON_BIN at the stub directory and asks
for its clients the way the bootstrap asks for them, through the requested
selection that resolve_agent_selection turns into the resolved one.

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
    printf 'committed: %s\n' "$(git rev-parse --short HEAD)"
else
    printf 'the test is not green; the fix stays uncommitted\n'
fi

printf '\n=== 2. the device configuration against the pre-apply snapshot ===\n'
bash /private/tmp/dotfiles-device-config-state.sh 2>/dev/null || printf 'the snapshot script is gone\n'
diff /private/tmp/dotfiles-device-config-pre-apply.tsv \
    <(bash /private/tmp/dotfiles-device-config-state.sh 2>/dev/null) \
    && printf 'the device configurations are byte-identical to the pre-apply state\n'

printf '\n=== 3. the merge against the device configuration ===\n'
bash "$scratch/merge-check.sh"

printf '\n=== 4. the live state ===\n'
bash /private/tmp/dotfiles-live-verify.sh 2>&1 | head -60

printf '\n=== 5. the gateway model list ===\n'
curl -s -m 15 http://127.0.0.1:3425/v1/models | jq -r '.data[]?.id' 2>/dev/null | sort

printf '\n=== 6. the provider-preserving resume (synthetic runtime only) ===\n'
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v 2>&1 | tail -14

printf '\n=== 7. cleanup: archive the merged worktrees ===\n'
for branch in fix/codex-content-guard fix/client-settings-toml-bytes; do
    name=${branch//\//-}
    path="$repo.$name"
    git tag "archive/$name" "$branch" 2>/dev/null
    if git rev-parse --verify "archive/$name" >/dev/null 2>&1; then
        printf 'archive/%s resolves to %s\n' "$name" "$(git rev-parse --short archive/$name)"
    else
        printf 'archive/%s did NOT resolve; the worktree is left alone\n' "$name"
        continue
    fi
    if [ -n "$(git -C "$path" ls-files -m)" ] || [ -n "$(git -C "$path" ls-files --others --exclude-standard)" ]; then
        printf '%s has uncommitted content; the worktree is left alone\n' "$path"
        continue
    fi
    if git merge-base --is-ancestor "$branch" fix/deployment-review; then
        git worktree remove "$path" && printf 'removed %s\n' "$path"
        git branch -d "$branch"
    else
        printf '%s is not merged into fix/deployment-review; the worktree is left alone\n' "$branch"
    fi
done

printf '\n=== 8. the final state ===\n'
git status --short
git log --oneline -5
git worktree list
