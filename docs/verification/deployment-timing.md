# Deployment timing baseline

Measure a fresh disposable home, an immediate reapply, and a subsequent
single-agent bootstrap. Time starts when bootstrap launches and ends after
the managed Pi launcher has run `--version` and returned the recorded version.
Planning and inventory hashing happen outside the timed runs. Each repetition
starts in a fresh home. The two warm workloads reuse that repetition's home.

Run the benchmark from the revision under test with Python 3.11 or newer.
Without tool overrides, the first two workloads use full bootstrap for the
Pi selection. Supply all three tool paths to benchmark the smaller
agents-only scope with the repository's fixture skill library:

```sh
baseline_output=$(cd "$(mktemp -d)" && pwd -P)
python3 tests/deployment_baseline.py \
  --execution native-macos --samples 3 --report "$baseline_output" \
  --chezmoi "$(command -v chezmoi)" --bun "$(command -v bun)" \
  --node "$(command -v node)"
```

On Linux, use exact pinned runtimes for the agents-only scope and specify
`native-linux` on a native host or `emulated-linux` in an emulated container.
For the runs below, the Linux image and the toolchain came from prior
disposable Ubuntu verification. Only the toolchain was mounted read-only.
The benchmark did not use the previous deployment's package cache or copy
its home. For separate cache-assisted experiments, `--cache-seed` accepts a
quiescent public package-cache snapshot and copies it into each fresh home
before starting the timer.

The selected Pi installation also runs the independent CodeGraph default.
The single-agent sample measures the bootstrap dispatch used after updating
or checking pins. Registry proposal, pin refresh, full default-agent
installation, Magpie and account operations are outside this scoped sample.
With the tool overrides, the full reapply stage is outside the measured scope.
In that mode the warm workloads run the same restricted command twice, giving
a check on repeatability while the single-agent path still uses the shared
bootstrap.

The JSON report records the source revision and fingerprint, toolchain,
started steps, wall time and log checksums. Stage intervals use the next
trace milestone or process exit as their endpoint, so they include any
intervening teardown or setup. Mutation counts cover regular files from source,
payload, settings and launcher inventories. Same-content mtime changes count
as rewrites. Package projects, caches and client runtime state are outside this
file-change inventory.

The runner counts fetch and retry notices visible in the logs and keeps
bounded logs for diagnosis. Package-manager output may omit successful
downloads and internal retries. Use these observations to investigate
failures and report package-manager behavior, and use separate network
instrumentation for exact request or byte counts.

## Observed baseline

The matched runs used clean source `56c4a0ed19d4d9b9e96567899ae2350cd953430b`
with fingerprint
`2e9f13c26d7cf5fdf62b524e45a5b8d01ff5f708f93244e3278a007c6c6cd9c7`.
Each fresh disposable home started with an empty package cache and
preinstalled tools. Both runs used Chezmoi 2.73.3 and exercised Pi 1.6.0.
The macOS workstation was arm64 on macOS 15.8.1 with Bun 1.4.5 and Node
26.13.1. Linux remote compute used Ubuntu 20.04 amd64 under OrbStack with
three CPUs and 4 GiB, Bun 1.4.2 and Node 26.12.1.

| Environment | Workload | Individual seconds | Median | Spread |
| --- | --- | --- | ---: | ---: |
| macOS | Fresh | 25.044, 25.888, 25.469 | 25.469 | 0.844 |
| macOS | Reapply | 4.366, 4.337, 4.382 | 4.366 | 0.045 |
| macOS | Single-agent | 4.462, 4.254, 4.252 | 4.254 | 0.210 |
| Emulated Ubuntu | Fresh | 38.354, 35.835, 45.208 | 38.354 | 9.373 |
| Emulated Ubuntu | Reapply | 19.151, 19.241, 19.496 | 19.241 | 0.345 |
| Emulated Ubuntu | Single-agent | 18.730, 18.319, 18.838 | 18.730 | 0.519 |

All 18 measured commands passed the launcher probe and matched eight
planned deployment steps. Median stage intervals in seconds:

| Step | Mac fresh | Mac reapply | Mac single | Ubuntu fresh | Ubuntu reapply | Ubuntu single |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `install-managers` | 0.021 | 0.020 | 0.021 | 0.075 | 0.087 | 0.090 |
| `apply-source` | 1.125 | 0.066 | 0.063 | 0.549 | 0.462 | 0.340 |
| `apply-source.skills` | 0.345 | 0.337 | 0.323 | 0.352 | 0.348 | 0.342 |
| `apply-source.agent-payload` | 0.282 | 1.382 | 1.390 | 1.816 | 3.463 | 3.454 |
| `apply-source.skills-prune` | 0.047 | 0.103 | 0.098 | 0.372 | 0.682 | 0.651 |
| `apply-source.client-settings` | 0.624 | 0.639 | 0.656 | 4.585 | 4.652 | 4.549 |
| `apply-source.macos-discovery` | 0.078 | 0.090 | 0.086 | 0.000 | 0.000 | 0.000 |
| `install-agents` | 22.295 | 1.243 | 1.187 | 27.685 | 7.466 | 7.116 |

Each fresh sample created 122 inventoried files on macOS and 127 on Ubuntu.
Each warm run rewrote 12 files with identical bytes and mode and made zero
content, mode, addition, or removal changes in that inventory. Bun reported 121 packages installed for
Pi and two for CodeGraph in the fresh run and no package changes in the warm
workloads. All successful-run logs contained zero explicit fetch or retry
notices. An earlier sandboxed probe failed at registry DNS and is
excluded from the network-enabled measurements.

The largest avoidable warm cost is shared payload on macOS and shared client
settings on emulated Ubuntu. Together those stages account for about two
seconds on macOS and eight seconds on Ubuntu. Their individual operations
must be checked against the selected agent's dependencies before omission.
Use one second on macOS and four seconds on emulated Ubuntu as conservative
initial savings targets for each matched single-agent sample. Both exceed
the observed warm spreads of 0.210 and 0.519 seconds. A candidate still
needs broken-output repair and preservation evidence. This timing scope
cannot establish cold full-bootstrap speed, package-manager retry totals,
or native Linux performance.

## Targeted update comparison

Repeat the command above with `--targeted-update` to measure the new
single-agent dispatch. Each fresh Pi home in the comparison ran the
ordinary warm `--agents-only` workload and then the targeted update with the
same toolchain, package cache, and version pins. Both commands verified
Pi 1.6.0 after the run. The comparison used clean source
`512a2af8778a252bf4aff94b12a920e6b09006bd` with fingerprint
`e9515ef25a1d86f813d382bc7dc261eb51fe7371f9d3428cbe80ce475a88d28a`.

| Environment | Warm regular (seconds) | Targeted (seconds) | Paired savings (seconds) |
| --- | --- | --- | --- |
| macOS | 4.433, 4.578, 4.480 | 1.035, 1.066, 1.035 | 3.398, 3.512, 3.445 |
| Emulated Ubuntu | 19.852, 19.750, 20.411 | 5.686, 5.714, 5.421 | 14.166, 14.036, 14.990 |

The targeted path dispatched three stages instead of eight. In every pair
it exceeded the initial one-second macOS and four-second emulated Ubuntu
targets. Median savings were 3.445 seconds on macOS and 14.166 seconds on
emulated Ubuntu. All warm regular runs rewrote 12 inventoried files with
identical bytes and mode. Each targeted run rewrote two identical files and
changed one inventoried file's content or mode. No inventoried files were
added or removed in the warm runs. An unselected-file preservation regression
checks byte and mtime stability outside the selected update's ownership.

A separate disposable macOS fixture moved the real Pi package entry, launcher,
and settings file aside. The targeted update forced a frozen reinstall of Pi,
restored the launcher and settings, and ran version 1.6.0. The unrelated Git
ignore drift stayed in place.

The comparison covers warm dispatch after version resolution. Full default
setup, true native Linux, native Windows, and different agent selections
require their own performance evidence.

### Final review recheck

The final runtime adds private Chezmoi rendering to targeted updates and
checks exact version tokens. Warm pairs from clean source
`b829c695ff36921f6c0be3a10cb7cd8380cc9b96` used the same toolchains and
alternated the order of the two dispatches on one pre-warmed disposable home
per environment. The source fingerprint was
`f7e8f0e0209bb377fc6cbac1502267dc548e6371c8fd2cba795f1f32e01926e7`.

| Environment | Warm regular (seconds) | Targeted (seconds) | Paired savings (seconds) |
| --- | --- | --- | --- |
| macOS | 4.174, 4.209, 4.306 | 1.051, 1.062, 1.124 | 3.123, 3.147, 3.182 |
| Emulated Ubuntu | 19.052, 19.801, 19.812 | 5.852, 5.785, 5.767 | 13.200, 14.016, 14.045 |

All 12 runs matched their step plans and validated the installed Pi version.
Every pair still exceeded the initial savings target.
