# Shared history verification

Observed 2026-10-13 on Linux x86-64. This is isolated Linux evidence, not native
macOS/WSL/Windows or ARM execution.

```bash
DOTFILES_TEST_CHEZMOI=/path/to/isolated/chezmoi \
DOTFILES_TEST_TOOL_HOME=/path/to/isolated/common-install/home \
python3 -m unittest discover -s tests -p test_history_behavior.py -v
```

The suite borrowed actual pinned Atuin 18.23.0, Nu 0.116.1, Bash/Zsh and Python
executables read-only from the common-tools test installation. Each case applied
the working source into a separate writable temporary home with explicit XDG
and Atuin roots. No existing device history or credentials were read.

Seven behavior checks passed:

- A new device shows pending activation without importing synthetic native
  history, generating an encryption key, or creating an auth session.
- Controlling-terminal Nu/Bash/Zsh commands enter one searchable local history;
  synthetic recognized GitHub tokens are excluded using Atuin's built-in filter.
- Bash migration is explicit, filtered and one-time; the original timestamp
  remains visible through Atuin search.
- Zsh, Nu text (including multiline commands), and Nu SQLite each use the actual
  pinned importer. Original fixtures remain byte-identical and recognized
  credentials are excluded before device transfer.
- Two devices register/join one synthetic account at a loopback-only endpoint,
  using one key. Actual Atuin PASETO v4 records are transferred and decrypted on
  the joined device. Wire records contain no plaintext command token. Both the
  password and encryption key stay out of captured terminal output.
- After the local endpoint stops, local recording and search still work;
  explicit sync fails visibly while offline status still reports activation.
- Invalid credential arguments are rejected without echo; activation requires a
  terminal, and symlinked history state is rejected before external writes.

Red tests first established missing status/preparation/import/activation
behavior, and then caught secret argv echo and history state symlink writes.
After refreshing the ticket branch from integration, the combined deployment,
agent, bundle, shell and history suite passed 47 tests in 44 seconds, with seven
explicit skips for opt-in network/tool checks and system Python's absent TOML
support. The deterministic bundle registry case was then run with managed
Python. The required legacy T9K and Linux simulated applies both passed, and
standalone Nu printed `standalone-ok` in both homes with inherited host settings
removed. Source-following Bash ShellCheck and POSIX driver ShellCheck passed.

During an earlier red sync test, the pinned config's precedence over
`ATUIN_SYNC_ADDRESS` briefly opened a hosted browser-flow session. No account
credentials or history were sent, and no account/login was activated. That test
attempt was stopped and its temporary state removed. The corrected fixture
sets the loopback address in the actual temporary config and asserts Atuin's
effective address before every activation; process-group cleanup covers child
processes. No synthetic process or listener remained after the corrected run.

The loopback server implements the official pinned record protocol at the
external service boundary. Atuin itself performs account/key state, encryption,
decryption, recording, filtering and search. This proves client behavior against
an isolated endpoint; it does not verify a real hosted account or browser flow.
The hosted default and native platform preparation are deployed, with actual
foreign-native checks delegated to platform/matrix tickets.
