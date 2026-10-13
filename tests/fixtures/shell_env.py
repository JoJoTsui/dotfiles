"""Launch isolated client diagnostics with the rendered shared shell values."""
import json
import subprocess
import sys


def managed_shell_environment(home, environment):
    # Load the public POSIX adapter instead of copying its role/PATH defaults
    # into fixtures. Only the supplied temporary home and explicit tools apply.
    result = subprocess.run([
        "/bin/sh", "-c",
        '. "$HOME/.env_core"; exec "$1" -c \'import json, os; print(json.dumps(dict(os.environ)))\'',
        "dotfiles-test-env", sys.executable,
    ], env=environment, cwd=home, capture_output=True, text=True, timeout=15, check=True)
    return json.loads(result.stdout)
