# Shared hosts, remote jobs, and bounded search

t9k hosts are shared containers with a project tree mounted under `/t9k`. Local
and remote execution differ in ways an agent must account for.

## Local vs remote

| | local shell | remote runner |
| --- | --- | --- |
| dotfiles | linked into `$HOME` by the legacy relinker | fresh `$HOME`, nothing linked |
| shell | interactive or login, sources `.env_core` | non-login, no rc files |
| `PATH` | includes `~/.local/bin`, `~/.pixi/bin` | operator `PATH` only, if exported |
| resources | host view, cgroup may still cap | cgroup of the execution container |
| scratch | operator tree | must be created on the execution host |

The reference pattern is a project script that links the operator tree before a
runner starts. Keep its behavior:

```bash
# source overridable, default to the operator tree
CVC_DOTFILES=${CVC_DOTFILES_DIR:-/t9k/mnt/joey/SHELL}
[[ -d $CVC_DOTFILES ]] || exit 2
[[ $CVC_DOTFILES != "$(cd "$HOME" && pwd -P)" ]] || exit 2

for name in .local .pixi .cargo .rustup .env_core; do
    src="$CVC_DOTFILES/$name"; dest="$HOME/$name"
    [[ -e $src ]] || continue
    [[ -e $dest || -L $dest ]] || ln -sT -- "$src" "$dest"
done
```

Rules that follow:

- Never replace an existing home entry; link only when absent.
- Skip the whole step when the project sets a no-link flag, so a managed host can
  opt out.
- After linking, source `.env_core` or the project's `env.sh`; a non-login shell
  does not do it.
- Pass environment over `ssh` explicitly. Tilde does not expand inside a
  double-quoted remote command, so use absolute quoted paths.
- Create scratch directories on the execution host, keep inputs read-only, and
  return the remote exit status.
- The execution host may be a container: apply the cgroup budget there, not on
  the submit host.

## Bounded search

t9k mounts are network-backed. A recursive search over them can take minutes and
burn the task budget.

1. If `.codegraph/` or `graphify-out/graph.json` exists, query the graph first.
2. Otherwise bound every text search:

   ```bash
   timeout 15s rg -n 'pattern' path
   timeout 10s rg --files -g '*.py' path
   timeout 15s rg -n 'pattern' path --max-count 20
   ```

3. Scope to the repository or a subdirectory. Never scan `/t9k`, use
   `--no-ignore`, or search `$HOME`.
4. Inside a git repository, `git grep -n` and `git ls-files` are usually faster
   than a filesystem walk.
5. A timeout is a signal to narrow the query or build an index. Retrying the
   same search wider wastes the budget.
6. Run long graph queries with a timeout too (`timeout 60s codegraph explore ...`,
   `timeout 60s graphify query ...`).
