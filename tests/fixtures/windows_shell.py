"""Ordinary native Nu discovery; the caller establishes its isolated roots."""
import subprocess


def ordinary_nu_settings(executable, environment):
    # Pinned Nu's -c mode omits ordinary startup files. -e executes after
    # normal REPL startup; explicit print/exit keeps the result noninteractive.
    return subprocess.run([str(executable), '-e',
                           'print ([$nu.default-config-dir $env.EDITOR $env.UV_PYTHON_PREFERENCE] | to json --raw); exit'],
                          env=environment, capture_output=True, text=True, timeout=30)
