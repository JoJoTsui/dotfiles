"""Real Zsh login timing after public source application in disposable homes."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest

if os.name == "posix":
    import fcntl
    import pty
    import termios


SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "requires Unix Zsh and a controlling TTY")
class ZprofileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zsh = "/bin/zsh" if Path("/bin/zsh").is_file() else shutil.which("zsh")
        cls.bash = "/bin/bash" if Path("/bin/bash").is_file() else shutil.which("bash")
        cls.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        for name, binary in (("zsh", cls.zsh), ("bash", cls.bash), ("chezmoi", cls.chezmoi)):
            if not binary or not os.access(binary, os.X_OK):
                raise unittest.SkipTest(f"requires available {name} runtime")
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-zprofile-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.rendered = cls.root / "rendered"
        environment = {"HOME": str(cls.root / "original"), "PATH": "/usr/bin:/bin",
                       "DOTFILES_CHEZMOI_BIN": cls.chezmoi,
                       "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library")}
        result = subprocess.run([
            cls.bash, str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
            "--home", str(cls.rendered), "--profile", "macos-workstation",
            "--arch", "aarch64", "--apply-only",
        ], env=environment, cwd=SOURCE, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError("public simulated apply failed:\n" + result.stderr)

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="case-", dir=self.root))
        self.addCleanup(shutil.rmtree, self.home)
        shutil.copytree(self.rendered, self.home, dirs_exist_ok=True)
        for relative in (".env_core", ".profile", ".zprofile", ".zshenv"):
            self.assertTrue((self.home / relative).is_file(), relative)
            self.assertFalse((self.home / relative).is_symlink(), relative)
        self.trace = self.home / "trace"
        # Inherit no host hooks, agent-session markers, caches, or tool roots.
        self.env = {"HOME": str(self.home), "ZDOTDIR": str(self.home), "TERM": "dumb",
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "ZPROFILE_TRACE": str(self.trace)}
        hook = self.home / ".config/dotfiles/zprofile.local.zsh"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text('printf "login-hook\\n" >> "$ZPROFILE_TRACE"\n')
        profile = self.home / ".profile"
        profile.write_text('printf "profile\\n" >> "$ZPROFILE_TRACE"\n' + profile.read_text())
        # Replace interactive tool integrations with a controlled observation.
        (self.home / ".zshrc").write_text('printf "zshrc\\n" >> "$ZPROFILE_TRACE"\n')
        for command in ("nu", "nu-login"):
            target = self.home / ".local/bin" / command
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('#!/bin/sh\nprintf "nu\\n" >> "$ZPROFILE_TRACE"\n')
            target.chmod(0o755)

    def shell(self, *, login=False, interactive=False, tty=False):
        # Disable global rc files; only the disposable home's public startup
        # files and controlled fixtures participate in the login proof.
        arguments = [self.zsh, "-d"]
        if login:
            arguments.append("-l")
        if interactive:
            arguments.append("-i")
        arguments += ["-c", 'printf "command\\n" >> "$ZPROFILE_TRACE"']
        if tty:
            master, slave = pty.openpty()

            def terminal_session():
                os.setsid()
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)

            process = None
            try:
                process = subprocess.Popen(arguments, env=self.env, cwd=self.home,
                                           stdin=slave, stdout=slave, stderr=slave,
                                           preexec_fn=terminal_session)
                os.close(slave)
                slave = None
                process.wait(timeout=10)
                self.assertEqual(process.returncode, 0)
            finally:
                if process is not None and process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                os.close(master)
                if slave is not None:
                    os.close(slave)
        else:
            result = subprocess.run(arguments, env=self.env, cwd=self.home,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
        return self.trace.read_text().splitlines() if self.trace.exists() else []

    def test_noninteractive_login_runs_hook_once_before_shared_profile(self):
        self.assertEqual(self.shell(login=True), ["login-hook", "profile", "command"])

    def test_interactive_tty_runs_hook_before_shared_profile_executes_nu(self):
        self.assertEqual(self.shell(login=True, interactive=True, tty=True),
                         ["login-hook", "profile", "nu"])

    def test_nonlogin_noninteractive_shell_omits_login_hook(self):
        self.assertEqual(self.shell(), ["command"])

    def test_interactive_nonlogin_tty_omits_login_hook_and_profile(self):
        self.assertEqual(self.shell(interactive=True, tty=True), ["zshrc", "command"])

    def test_missing_local_hook_keeps_login_usable(self):
        (self.home / ".config/dotfiles/zprofile.local.zsh").unlink()
        self.assertEqual(self.shell(login=True), ["profile", "command"])


if __name__ == "__main__":
    unittest.main()
