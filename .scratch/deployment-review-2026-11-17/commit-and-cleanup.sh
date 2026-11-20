#!/usr/bin/env bash
# Every measurement the 2026-11-19 classifier outage kept from running.
#
# One gate pass runs this. Every step prints its own result, a step that
# fails does not stop the ones after it, and nothing is pushed.
#
# The steps, in order:
#   1. the worktrunk plugin test, and the commit that depends on it
#   1b. the classifier-route change (ticket 20), its suite, and its commit
#   2. the device configuration against the pre-apply snapshot
#   3. the merge against the device configuration
#   4. the live state (with the corrected agent command names)
#   5. the gateway's model list, with and without the deployment's credential
#   6. the gateway's own answer for the groups, under both spellings
#   6b. the authorized apply, so the device takes the new classifier route
#   6c. the gateway again, after the apply
#   7. the provider-preserving resume (synthetic runtime only)
#   8. cleanup: archive the merged worktrees
#   9. the final state
set -uo pipefail

repo=/Users/joey/SHELL/dotfiles
scratch="$repo/.scratch/deployment-review-2026-11-17"
cd "$repo" || exit 1

# The gateway CLI can wait on a busy provider, so a read gets a bound when
# the host has one. Without it the read still runs, only unbounded.
run_bounded() {
    if command -v gtimeout >/dev/null 2>&1; then
        gtimeout 30 "$@"
    elif command -v timeout >/dev/null 2>&1; then
        timeout 30 "$@"
    else
        "$@"
    fi
}

printf '=== 1. the worktrunk plugin test (ticket 17) ===\n'
python3 -m unittest tests.test_worktrunk -v 2>&1 | tail -12
test_status=${PIPESTATUS[0]}
printf -- '--- committing the fix when the test is green ---\n'
if [ "$test_status" -eq 0 ]; then
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
    printf 'the test is not green (exit %s); the fix stays uncommitted\n' "$test_status"
fi

printf '\n=== 1b. the classifier route (ticket 20) ===\n'
# The auxiliary aliases and the permission classifier move from one provider's
# model to the gateway's own Terra family, so a spent ChatGPT account does not
# deny every checked action. The suite that covers the change runs first, and
# the commit follows only when it is green.
DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) \
    python3 -m unittest tests.test_magpie tests.test_magpie_auxiliary_models 2>&1 | tail -14
suite_status=${PIPESTATUS[0]}
printf -- '--- committing the classifier route when the suite is green ---\n'
if [ "$suite_status" -eq 0 ]; then
    git add deployment/client-settings/claude-settings.json.tmpl deployment/magpie.sh \
        docs/AGENT_SETTINGS.md docs/MAGPIE.md \
        tests/test_magpie.py tests/test_magpie_auxiliary_models.py
    git commit -F - <<'EOF'
[agents]: route the classifier through the terra family

The auto-mode classifier, the Haiku alias, and the small-fast alias were
pinned to codex/gpt-6.1-terra, one provider's model. When the ChatGPT-plan
account that serves it is exhausted, the safety classifier cannot answer and
every command with a side effect is denied, which froze the deployment work
on this Mac.

The route is now auto/gpt-6.1-terra, the gateway's own Terra family, which
routes Codex first and then OpenAI. The template, the constant the status
compares against, both documents, and the tests that name the route change
together.

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
    printf 'committed: %s\n' "$(git rev-parse --short HEAD)"
else
    printf 'the suite is not green (exit %s); the classifier-route change stays uncommitted\n' "$suite_status"
fi

printf '\n=== 2. the device configuration against the pre-apply snapshot ===\n'
if [ -x /private/tmp/dotfiles-device-config-state.sh ]; then
    bash /private/tmp/dotfiles-device-config-state.sh 2>/dev/null
    if diff /private/tmp/dotfiles-device-config-pre-apply.tsv \
            <(bash /private/tmp/dotfiles-device-config-state.sh 2>/dev/null); then
        printf 'the device configurations are byte-identical to the pre-apply state\n'
    else
        printf 'the device configurations differ from the pre-apply snapshot\n'
    fi
else
    printf 'the snapshot script is gone\n'
fi

printf '\n=== 3. the merge against the device configuration ===\n'
if [ -x "$scratch/merge-check.sh" ]; then
    bash "$scratch/merge-check.sh"
else
    printf 'the merge check is at /private/tmp/dotfiles-device-merge-check.sh\n'
    [ -x /private/tmp/dotfiles-device-merge-check.sh ] && bash /private/tmp/dotfiles-device-merge-check.sh
fi

printf '\n=== 4. the live state ===\n'
bash "$scratch/live-verify.sh" 2>&1 | head -60

printf '\n=== 5. the gateway model list (tickets 21 and 22) ===\n'
printf -- '--- without a credential ---\n'
curl -s -m 15 http://127.0.0.1:3425/v1/models | jq -r '.data[]?.id' 2>/dev/null | sort
printf -- '--- with the deployment credential ---\n'
curl -s -m 15 -H 'Authorization: Bearer magpie' http://127.0.0.1:3425/v1/models |
    jq -r '.data[]?.id' 2>/dev/null | sort
printf -- '--- the deployment fetch, as the apply makes it ---\n'
(
    source "$repo/deployment/magpie.sh" 2>/dev/null
    magpie_models_fetch "${MAGPIE_GATEWAY:-http://127.0.0.1:3425}" 2>/dev/null |
        magpie_model_ids 2>/dev/null | sort
) || printf 'the deployment fetch did not run\n'

printf '\n=== 6. the gateway answer for the groups (tickets 21 and 22) ===\n'
for group in auto-gpt-6-1-sol auto-gpt-6-1-terra auto-gpt-6-luna auto-gpt-6-astra; do
    printf -- '--- the deployment group %s ---\n' "$group"
    run_bounded magpie group "$group" 2>&1 | head -14
done
# The gateway serves its own family ids under a slash form. Asking for both
# spellings is what separates a name collision from a stale "listed" value:
# if the slash form answers with the same members, the two ids are one
# object in the gateway's namespace.
for family in auto/gpt-6.1-sol auto/gpt-6.1-terra auto/gpt-6-luna \
             auto/gpt-6-astra auto/gpt-6.2-astra auto/gpt-6.2-sol; do
    printf -- '--- the gateway family %s ---\n' "$family"
    run_bounded magpie group "$family" 2>&1 | head -14
done

printf '\n=== 6b. the authorized apply, so the device takes the new route ===\n'
# The same public bootstrap the gate ran, against the real home. The client
# settings merge is the only writer of the device's Claude Code settings, so
# the new classifier route reaches the device through it rather than through a
# hand edit.
apply_log=/private/tmp/dotfiles-real-apply-2026-11-20.log
bash "$repo/bootstrap.sh" --source "$repo" --home "$HOME" \
    --agents kimi,pi,opencode,claude,codex,minimax,qoder </dev/null >"$apply_log" 2>&1
apply_status=$?
printf 'the apply exited %s; the full log is %s\n' "$apply_status" "$apply_log"
tail -n 12 "$apply_log"
printf -- '--- the classifier route the device now carries ---\n'
python3 - <<'PY'
import json
import pathlib

path = pathlib.Path.home() / ".claude" / "settings.json"
try:
    env = json.loads(path.read_text(encoding="utf-8")).get("env", {})
except Exception as error:
    print("unreadable:", error)
else:
    for key in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                "CLAUDE_CODE_AUTO_MODE_MODEL"):
        print(key, "=", env.get(key))
PY

printf '\n=== 6c. the gateway after the apply (tickets 21 and 22) ===\n'
printf -- '--- the published model list ---\n'
curl -s -m 15 -H 'Authorization: Bearer magpie' http://127.0.0.1:3425/v1/models |
    jq -r '.data[]?.id' 2>/dev/null | sort
printf -- '--- the four groups, under both spellings ---\n'
for group in auto-gpt-6-1-sol auto-gpt-6-1-terra auto-gpt-6-luna auto-gpt-6-astra \
             auto/gpt-6.1-sol auto/gpt-6.1-terra auto/gpt-6-luna auto/gpt-6-astra; do
    printf -- '--- %s ---\n' "$group"
    run_bounded magpie group "$group" 2>&1 | head -12
done

printf '\n=== 7. the provider-preserving resume (synthetic runtime only) ===\n'
DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v 2>&1 | tail -14

printf '\n=== 8. cleanup: archive the merged worktrees ===\n'
for branch in fix/codex-content-guard fix/client-settings-toml-bytes; do
    name=${branch//\//-}
    path="$repo.$name"
    if ! git rev-parse --verify "archive/$name" >/dev/null 2>&1; then
        git tag "archive/$name" "$branch" 2>/dev/null
    fi
    if git rev-parse --verify "archive/$name" >/dev/null 2>&1; then
        printf 'archive/%s resolves to %s\n' "$name" "$(git rev-parse --short "archive/$name")"
    else
        printf 'archive/%s did NOT resolve; the worktree is left alone\n' "$name"
        continue
    fi
    # Git removes ignored files even when the status is clean, so the
    # inventory names them too. Anything left behind keeps its worktree.
    if [ -n "$(git -C "$path" ls-files -m 2>/dev/null)" ] ||
       [ -n "$(git -C "$path" ls-files --others --exclude-standard 2>/dev/null)" ] ||
       [ -n "$(git -C "$path" ls-files --others --ignored --exclude-standard 2>/dev/null)" ]; then
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

printf '\n=== 9. the final state ===\n'
git status --short
git log --oneline -5
git worktree list
git tag --list 'archive/*'
