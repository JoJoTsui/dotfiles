# Version update workflow

Normal bootstrap consumes the committed exact pins and supported Bun lockfiles.
It never runs an update command. The maintenance helper works on repository
source files only; it never applies a deployment or edits a device registry.

Run the read-only consistency check first:

```sh
python3 deployment/update_versions.py check
```

To prepare a change, create a reviewed JSON proposal from upstream release
metadata. Its keys are optional. Common and bundle values are exact package
versions; bundle keys use `bundle/package`. Agent names match
`deployment/agents/catalog.tsv`. A changed Windows exception requires the new
version, HTTPS URL, and published SHA-256 together.

```json
{
  "common": { "uv": "<exact-version>" },
  "bundles": { "bio/samtools": "<exact-version>" },
  "agents": { "codex": "<exact-version>" },
  "managers": { "pixi": "<exact-version>" },
  "windowsAssets": {
    "pixi": {
      "version": "<exact-version>",
      "url": "https://<official-release-asset>",
      "sha256": "<64 lowercase hex characters>"
    }
  }
}
```

The manager and matching Windows asset versions must agree. Update their two
entries together. Do not guess Windows checksums: verify the candidate against
the publisher's release metadata before putting it in the proposal. Asset
installer layout changes (`kind`, archive entry, or target path) need a
separate implementation change.

Refresh on a worktree with the currently pinned Bun binary. The helper checks
the selected npm release metadata and its Node engine, then regenerates each
changed agent's lock in a temporary home/cache with lifecycle scripts disabled.
It checks the entire staged version set before writing any changed source file.
The candidate version set appears in `git diff` for review.

```sh
python3 deployment/update_versions.py refresh \
  --proposal /tmp/version-proposal.json \
  --bun /absolute/path/to/currently-pinned/bun
git diff -- deployment
python3 deployment/update_versions.py check
```

Then run verification with the same pinned Bun version:

```sh
python3 deployment/update_versions.py verify \
  --bun /absolute/path/to/candidate-pinned/bun
```

This checks npm Node-engine compatibility, validates all six frozen Bun locks
without installing packages, and runs the agent, CodeGraph configuration, and
Windows adapter contract suites in disposable homes. If the isolated package
cache or registry is unavailable, report that layer as pending and retry when
network access is available.

Resolve the actual common and optional package sets for every declared target
with the pinned Pixi binary:

```sh
python3 deployment/update_versions.py verify \
  --bun /absolute/path/to/candidate-pinned/bun \
  --pixi /absolute/path/to/candidate-pinned/pixi \
  --resolve
```

This uses the package resolution test to create a fresh Pixi workspace and lock
under `/tmp`; it covers Linux and WSL on both architectures, both macOS
architectures, native Windows x86-64, the common tools, and every declared
bundle/target pair. Resolution proves metadata solvability, not native binary
execution. Push the reviewed integration branch to run the native macOS,
Windows, and WSL workflows before calling those targets verified. macOS, native
Windows and WSL2 x86-64 have now passed natively at commit 81857d6; WSL ARM64
is not scheduled unless a Windows ARM64 WSL runner is supplied.

After the plan and resolution checks pass, install the candidate working tree
only into a disposable Linux home. Inspect its commands and rendered state,
then remove the temporary home. Use native runners for other operating
systems; never target the maintainer's real home as a version-update test.

```sh
DOTFILES_VERSION_HOME="$(mktemp -d /tmp/dotfiles-version.XXXXXX)"
bash bootstrap.sh --source "$PWD" --home "$DOTFILES_VERSION_HOME" \
  --platform linux --arch x86_64 --role workstation
rm -rf "$DOTFILES_VERSION_HOME"
```

Commit the reviewed version set only after the required checks pass. New hosts
then deploy that committed set through ordinary bootstrap.

The agent refresh and verification commands use Bun's lock-only and frozen
lock workflows; Bun documents these modes in its
[lockfile guide](https://bun.sh/docs/pm/lockfile) and
[install reference](https://bun.sh/docs/pm/cli/install). Pixi global has no
committed lockfile in this repository. Its catalog pins direct packages
exactly, while transitive builds can change when Pixi resolves them during
global sync; the resolution check records a fresh lock as evidence, not as a
committed deployment lock.

## Current verification snapshot

On 2026-10-13, the read-only catalog check passed for 29 common environments
with 30 distinct package pins, 79 bundle-tool rows with 82 distinct package
pins, six agents, and eight Windows exceptions. The updater
transaction tests passed, including an isolated agent refresh, Windows manager
pin synchronization, and repeated-proposal idempotence. The deterministic suite
ran 95 tests with 67 environment-dependent tests skipped. The pinned Bun frozen
lock and configuration verification passed. The isolated Pixi resolver
successfully locked every common and declared bundle target.

No package version proposal was applied in this snapshot, so those checks
validate the currently committed set. Native macOS, Windows and WSL2 x86-64
execution has since passed their runners — runs 38524061897, 38524061998 and
38524061914 at commit `81857d6` — while WSL2 ARM64 remains unscheduled. After a
real proposal, repeat all layers above, review the complete diff, run the
disposable-home install, and commit the accepted pin set before deploying it to
a new host.
