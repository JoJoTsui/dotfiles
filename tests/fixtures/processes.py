"""Terminate whole native client trees on disposable test hosts."""
import os
import subprocess


def stop_client(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill.exe', '/T', '/F', '/PID', str(process.pid)],
                           capture_output=True, timeout=15)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
