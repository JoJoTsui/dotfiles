# Legacy home links

`deployment/legacy/link-home.sh` is the maintained, opt-in relinker for the
pre-chezmoi T9K-style home layout. Ordinary deployments never use it: the
public boundary applies this repo in **copy mode**, and `deployment/` is
excluded from `$HOME` by `.chezmoiignore`.

Use it only when the host's home entries are already symlinks into a live tree
that contains this checkout, for example:

```text
/t9k/mnt/.bashrc -> /t9k/mnt/joey/SHELL/.bashrc
/t9k/mnt/.qoder  -> /t9k/mnt/joey/SHELL/.qoder
```

The live tree is the **parent of the repository checkout**, not the chezmoi
source state. The script never runs `chezmoi`, and running it on a managed host
would replace copy-mode files with symlinks. Do not do that.

## Usage

From the repository root:

```bash
# Inspect before changing anything.
bash deployment/legacy/link-home.sh --check
bash deployment/legacy/link-home.sh --dry-run

# Relink the default legacy tree into the current home.
bash deployment/legacy/link-home.sh

# Relink only the agent roots, or use an explicit source and destination.
bash deployment/legacy/link-home.sh --groups agents
bash deployment/legacy/link-home.sh --source /srv/legacy --home /home/example

# List manifest entries without touching the filesystem.
bash deployment/legacy/link-home.sh --list
```

A legacy host can expose the utility through a convenience symlink such as
`~/link-home`; the script resolves its own symlink chain before locating the
manifest.

The manifest names entries relative to the live tree; the directory must already
exist there. A manifest entry whose source is absent is skipped, and `--strict`
turns that into a failure. To adopt a home-only root such as `.caveman` or
`.lark-cli`, move or copy it into the live tree first, then run the relinker. The default source is the parent of this checkout. The default home
is `$HOME`. Both must exist and resolve to different directories.

## Safety model

Before writing, the script validates the whole selected set:

- manifest paths are top-level, relative, unique, and contain no `..` or `.`
  components;
- the selected source tree contains at least one entry (an empty or wrong
  `--source` fails instead of silently doing nothing);
- no target would contain its own source, which would create a symlink loop;
- `--strict` makes any missing selected source fatal before any change.

Then, for each selected entry:

- an already-correct symlink is left alone, so repeat runs are idempotent;
- a regular file, directory, or wrong symlink is moved to
  `<target>.bak.YYYYmmdd-HHMMSS` before the new symlink is created;
- a same-second backup collision gets a `-1`, `-2`, ... suffix;
- if symlink creation fails, the backup is moved back;
- missing sources are skipped with a warning, unless `--strict` was used.

`--dry-run` performs the same validation and prints planned changes without
creating backups, directories, or links. `--check` is read-only and exits `1`
when a selected target is missing or points somewhere else.

Exit status is `0` for success, `1` for an operational failure or detected
drift, and `2` for invalid arguments.

## Manifest

`deployment/legacy/home-links.tsv` is the single list of linked entries. Rows
are `group|path`, where `path` is relative to home:

```text
config|.bashrc
agents|.qoder
agents|.minimax
```

Groups are `config`, `runtime`, `dev`, `vscode`, `trae`, `other`, and `agents`.
Add new state roots to the appropriate group and keep the file limited to
top-level home entries. The agent group deliberately includes the Qoder,
MiniMax Code, and MiniMax install-log roots.

## System Bash opt-in

The old live script always replaced `/etc/bash.bashrc` with a symlink to
`<source>/bash.bashrc` via `sudo`. The maintained script does that only with
`--system`, and only on legacy hosts:

```bash
bash deployment/legacy/link-home.sh --system
```

Without `--system`, no system path and no `sudo` is touched. On a
chezmoi-managed host use the public `--system-config` action instead; that
path manages a marked block and explicitly refuses symlinked system files.

## Tests

The utility is covered by `tests/test_legacy_link.py`, which uses disposable
homes and never touches the real account or `/etc`:

```bash
python3 -m unittest tests.test_legacy_link -v
```

The full suite remains the release gate:

```bash
DOTFILES_TEST_CHEZMOI=$(command -v chezmoi) \
  python3 -m unittest discover -s tests -v
```
