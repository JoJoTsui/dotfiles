"""A test-only engine shim for Magpie's direct-command guard.

The public `dotfiles-magpie` command resolves the platform from `uname -s`
and the account home through `magpie_real_account_home`, neither of which
trusts an environment override. Positive fixtures run against a synthetic HOME
with fake CLIs, so they source this shim instead of the deployment engine: it
loads the real engine and then neutralizes those two guard inputs. The guard's
negative coverage uses the unmodified engine (test_magpie_direct_isolation.py).
"""
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2]
ENGINE = SOURCE / "deployment" / "magpie.sh"


def engine_shim_text(engine=ENGINE):
    """Shell source of a shim that satisfies the direct-command guard."""
    return (
        "#!/usr/bin/env bash\n"
        "# Test-only engine shim: the deployment engine with the direct-command\n"
        "# account-home guard neutralized for a synthetic HOME.\n"
        "# shellcheck source=/dev/null\n"
        "source " + repr(str(engine)) + "\n"
        "\n"
        "# The command resolves both guard inputs natively. A positive fixture\n"
        "# owns its HOME, so report it as the real account home and derive the\n"
        "# kernel name from the deployment selector the fixture set. Any other\n"
        "# uname call still reaches the real command.\n"
        "magpie_real_account_home() { return 0; }\n"
        "\n"
        "uname() {\n"
        '    if [ "$#" -eq 1 ] && [ "${1:-}" = -s ]; then\n'
        '        case "${DEPLOY_PLATFORM:-}" in\n'
        "            macos) printf 'Darwin\\n'; return 0 ;;\n"
        "            linux|wsl) printf 'Linux\\n'; return 0 ;;\n"
        "        esac\n"
        "    fi\n"
        '    command uname "$@"\n'
        "}\n"
    )


def install_engine_shim(directory, name="engine.sh", engine=ENGINE):
    """Write the shim into a test-owned directory and return its path."""
    path = Path(directory) / name
    path.write_text(engine_shim_text(engine), encoding="utf-8")
    return path
