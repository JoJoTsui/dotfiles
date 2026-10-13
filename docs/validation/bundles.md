# Optional bundle verification

Ticket 08 keeps the 77 optional former Pixi environments owned, adds a pinned
curl environment for the bio helper, and gives each of the resulting 78 tool
environments an explicit command exposure. Bundle selection is independent of
host role. Common defaults select none.

## Checks performed

The public-boundary tests exercise explicit selection overriding environment
input, early unsupported/invalid rejection without state creation, actual
copy-mode application of the complete selected inventory and gated payloads,
exact package/channel/prerequisite plans, device-registry preservation, and
non-uninstalling deselection. Plans for all 14 accepted profile combinations
have no default specialist tools. `fetchChromSizes --help` is harmless; its
normal transport is the bio bundle's pinned curl over HTTPS.

On 2026-10-13, Pixi 0.81.0 produced a real workspace lock for 100 independent
tool/subdir environments covering all 78 logical tools. These comprise
Linux x86-64/ARM64 bio and GPU, Linux x86-64 developer, and Linux x86-64,
macOS Intel/Apple silicon, and Windows x86-64 desktop. Linux package subdirs
also supply the declared WSL inventory. The solver used explicit named
platform baselines of glibc 2.28 and macOS 14.2. WSL runtime behavior remains
separate. Published artifact metadata alone was not counted as resolution.

The resolution artifacts and solver output were retained outside source state
under `/tmp/dotfiles-implementation/bundle-resolution`. They are generated
evidence, not a Pixi global installation lock. Exact direct pins remain in
`deployment/bundle-tools.tsv`; global installation can still choose different
builds or transitive dependencies. Repeat the maintained resolution check after
changing those pins.

The first real Linux install exposed every requested command, preserved the
unrelated test tool and all bundles after deselection, and passed representative
bio/GPU/developer/Zed diagnostics. Firefox's version diagnostic found a missing
Linux X11 runtime library; that red result led to pinned Linux GTK/X11/audio/
D-Bus dependencies and a process-scoped user launcher. The corrected test then
passed both complete bundle installation and reapplication with `none`,
including samtools/seqkit, NVTOP, Firefox, Zed, sd/ShellCheck, Herdr/Zellij, the
DuckDB Python API, and bio-helper diagnostics. All 78 tool environments and
their selected exposures were installed in the separate Linux home. The known
pending-agent failure after those successful stages was kept distinct from
full-bootstrap completion. Actual GPU telemetry and graphical workloads are
not established by installing a package or running its version diagnostic.

After merging the completed shell and agent adapters, the same isolated test
passed full bootstrap twice with `--agents none`, including default CodeGraph
installation and managed shell preparation. Combined source/shell/agent/bundle
discovery passed 34 checks, with six separately reported opt-in verification
skips. This supplies actual Linux execution evidence for the combined slice.

## Repeatable checks

Use Python 3.11 or newer for complete TOML registry assertions, a real isolated
Chezmoi binary, and the pinned Pixi binary. Ordinary deterministic checks:

```bash
DOTFILES_TEST_CHEZMOI=/path/to/chezmoi python3 -m unittest discover -s tests -p test_bundles.py -v
```

The foreign solver starts from public plans and saves its generated workspace,
real lock, and diagnostics in an optional retained temporary directory:

```bash
DOTFILES_TEST_BUNDLE_RESOLUTION=1 \
DOTFILES_TEST_PIXI=/path/to/pixi \
DOTFILES_TEST_BUNDLE_RESOLUTION_ROOT=/tmp/dotfiles-bundle-resolution \
python3 -m unittest discover -s tests -p test_bundle_resolution.py -v
```

The network/native test installs all four requested bundles in its own home,
checks every selected Pixi exposure during bootstrap, runs representative
harmless diagnostics, and reapplies with `none` to prove preservation:

```bash
DOTFILES_TEST_BUNDLE_INSTALL=1 \
DOTFILES_TEST_BUNDLE_HOME=/tmp/dotfiles-bundle-native/home \
python3 -m unittest discover -s tests -p test_bundle_install.py -v
```

`DOTFILES_TEST_BUNDLE_SELECTION=bio,gpu` can select a smaller native sample.
Supplied native-test managers through `DOTFILES_TEST_PIXI` and
`DOTFILES_TEST_CHEZMOI` must be under `/tmp`; the source executables are read
only. The fixture copies just the supplied Pixi binary into its designated
managed bin so fresh shells discover it; it shares no writable installed
prefix. All writable package/XDG/cache state follows the separate test home. Logs for
both application attempts stay in that home. The test never imports history,
authenticates accounts, starts daemons, changes drivers/capabilities, or indexes
user projects. Historical pre-ticket-04 midpoint evidence remains separate
from the combined full-bootstrap result above.

## Runtime prerequisites and remaining evidence

- GPU: compatible visible hardware and driver telemetry interfaces; WSL also
  depends on its Windows host driver. Ordinary user bootstrap changes neither.
- Desktop: an actual graphical session and compatible graphics; macOS 14.2 or
  newer, or WSLg/an explicitly configured WSL display.
- Developer: glibc 2.28 or newer; kernel/container permissions can limit
  bubblewrap. Cloud accounts, project SDKs, Rust toolchains, Lark services,
  Headroom's optional local service, and reference datasets are set up on use.
- Native macOS/Windows/ARM and actual WSL execution remain the separate native
  profile acceptance work. Neither solver success nor Linux rendering counts
  as those runtimes passing.

Primary pin and constraint inputs were the published package records, including
[Bioconda tgv](https://api.anaconda.org/package/bioconda/tgv),
[Bioconda samtools](https://api.anaconda.org/package/bioconda/samtools),
[KMC](https://api.anaconda.org/package/bioconda/kmc),
[Zed](https://api.anaconda.org/package/conda-forge/zed), and
[Firefox](https://api.anaconda.org/package/conda-forge/firefox).
The retained extras also use primary records for
[ShellCheck](https://api.anaconda.org/package/conda-forge/shellcheck),
[shfmt](https://api.anaconda.org/package/conda-forge/go-shfmt),
[fnm](https://api.anaconda.org/package/conda-forge/fnm),
[sd](https://api.anaconda.org/package/conda-forge/sd), and
[curl](https://api.anaconda.org/package/conda-forge/curl).
[NVTOP's upstream requirements](https://github.com/Syllo/nvtop) distinguish
telemetry facilities from package installation.
