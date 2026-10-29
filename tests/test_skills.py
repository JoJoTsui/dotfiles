"""Skill catalog validation and fetch behavior without network access."""
import os
import hashlib
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class SkillFetchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skills-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.catalog = self.source / "deployment/skills.tsv"
        self.catalog.parent.mkdir(parents=True)
        self.cache = self.root / "cache"
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()

    def run_script(self, body, env=None):
        script = self.root / "run.sh"
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{self.source}'\n"
            f"export XDG_CACHE_HOME='{self.root}/xdg-cache' XDG_STATE_HOME='{self.root}/xdg-state' TMPDIR='{self.tmp}'\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            f"source '{SOURCE}/deployment/skills.sh'\n"
            + body,
            encoding="utf-8")
        environment = dict(os.environ, **(env or {}))
        return subprocess.run(["/bin/bash", str(script)], env=environment,
                              capture_output=True, text=True, timeout=120)

    def write_catalog(self, *rows):
        self.catalog.write_text("# name|kind|source|ref|path\n" + "\n".join(rows) + "\n")

    def make_git_repo(self, name, path="skills/demo"):
        repo = self.root / name
        skill = repo / path
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\nbody\n")
        (skill / "note.md").write_text("note\n")
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "init"], check=True)
        return repo

    def make_tarball(self, name, path="."):
        root = self.root / f"{name}-src"
        skill = root / path if path != "." else root
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text("---\nname: arc\ndescription: archive\n---\nbody\n")
        archive = self.root / f"{name}.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            for item in sorted(skill.rglob("*")):
                handle.add(item, arcname=str(item.relative_to(skill)))
        return archive

    def test_git_and_tarball_rows_are_fetched_into_the_library(self):
        repo = self.make_git_repo("demo-repo")
        archive = self.make_tarball("arc")
        self.write_catalog(f"demo|git|{repo}|main|skills/demo",
                           f"arc|tarball|file://{archive}||")
        result = self.run_script(
            'prepare_skill_library\n'
            'test -f "$PAYLOAD_SKILLS_DIR/demo/SKILL.md"\n'
            'test -f "$PAYLOAD_SKILLS_DIR/arc/SKILL.md"\n'
            'cat "$XDG_STATE_HOME/dotfiles/skills.lock.tsv"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("demo|git|", result.stdout)
        self.assertIn("arc|tarball|", result.stdout)
        self.assertIn("|main|", self.catalog.read_text())

    def test_cached_library_is_reused_without_network(self):
        repo = self.make_git_repo("demo-repo")
        self.write_catalog(f"demo|git|{repo}|main|skills/demo")
        first = self.run_script('prepare_skill_library && echo "$PAYLOAD_SKILLS_DIR"')
        self.assertEqual(first.returncode, 0, first.stderr)
        marker = self.root / 'xdg-cache/dotfiles/skills/.refreshed'
        previous = str(int(time.time()) - 10800)
        marker.write_text(previous + '\n')
        second = self.run_script('prepare_skill_library && echo "$PAYLOAD_SKILLS_DIR"',
                                 env={"DOTFILES_SKILLS_REFRESH": "0"})
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(marker.read_text().strip(), previous)
        automatic = self.run_script('prepare_skill_library', env={"DOTFILES_SKILLS_REFRESH": "auto"})
        self.assertEqual(automatic.returncode, 0, automatic.stderr)
        self.assertEqual(marker.read_text().strip(), previous)

    def test_failed_refresh_reuses_cache_without_advancing_timestamp(self):
        repo = self.make_git_repo('demo-repo')
        self.write_catalog(f'demo|git|{repo}|main|skills/demo')
        first = self.run_script('prepare_skill_library')
        self.assertEqual(first.returncode, 0, first.stderr)
        marker = self.root / 'xdg-cache/dotfiles/skills/.refreshed'
        marker.write_text('1\n')
        repo.rename(self.root / 'offline-repo')
        result = self.run_script('prepare_skill_library', env={'DOTFILES_SKILLS_REFRESH': '1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(), '1\n')

    def test_catalog_rejects_duplicates_and_unsafe_paths(self):
        self.write_catalog("demo|git|https://example.invalid/r|main|/absolute")
        result = self.run_script("validate_skill_catalog")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("relative", result.stderr)
        self.write_catalog("demo|git|https://example.invalid/r|main|skills/demo",
                           "demo|git|https://example.invalid/r2|main|skills/demo")
        result = self.run_script("validate_skill_catalog")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr)

    def test_git_lock_keeps_reviewed_revision_after_upstream_changes(self):
        repo = self.make_git_repo('demo-repo')
        revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        self.write_catalog(f'demo|git|{repo}|main|skills/demo')
        (self.catalog.parent / 'skills.lock.tsv').write_text(f'demo|git|{repo}|{revision}\n')
        (repo / 'skills/demo/note.md').write_text('unreviewed update\n')
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                        'commit', '-qm', 'update'], check=True)
        result = self.run_script('prepare_skill_library\ncat "$PAYLOAD_SKILLS_DIR/demo/note.md"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'note\n')

    def test_archive_checksum_mismatch_preserves_verified_cache(self):
        archive = self.make_tarball('arc')
        self.write_catalog(f'arc|tarball|file://{archive}||')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (self.catalog.parent / 'skills.lock.tsv').write_text(f'arc|tarball|file://{archive}|{digest}\n')
        result = self.run_script('prepare_skill_library')
        self.assertEqual(result.returncode, 0, result.stderr)
        archive.write_bytes(b'unreviewed archive')
        # Conditional requests compare timestamps at second precision.
        changed = time.time() + 5
        os.utime(archive, (changed, changed))
        result = self.run_script('prepare_skill_library', env={'DOTFILES_SKILLS_REFRESH': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)
        result = self.run_script('prepare_skill_library', env={'DOTFILES_SKILLS_REFRESH': '0'})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_refresh_changes_only_lock_and_fails_atomically(self):
        repo = self.make_git_repo('demo-repo')
        archive = self.make_tarball('arc')
        self.write_catalog(f'demo|git|{repo}|main|skills/demo', f'arc|tarball|file://{archive}||')
        lock = self.catalog.parent / 'skills.lock.tsv'
        import sys
        command = [sys.executable, str(SOURCE / 'deployment/update_skills.py'), 'refresh',
                   '--catalog', str(self.catalog), '--lock', str(lock)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        old = lock.read_bytes()
        archive.write_bytes(b'broken archive')
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(lock.read_bytes(), old)

    def test_archive_with_links_or_absolute_members_is_rejected(self):
        unsafe = self.root / "unsafe.tar.gz"
        with tarfile.open(unsafe, "w:gz") as handle:
            info = tarfile.TarInfo("/etc/passwd")
            info.size = 0
            handle.addfile(info)
        result = self.run_script(f"skill_archive_is_safe '{unsafe}'")
        self.assertNotEqual(result.returncode, 0)

        linked = self.root / "linked.tar.gz"
        with tarfile.open(linked, "w:gz") as handle:
            info = tarfile.TarInfo("SKILL.md")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            handle.addfile(info)
        result = self.run_script(f"skill_archive_is_safe '{linked}'")
        self.assertNotEqual(result.returncode, 0)

    def test_override_library_skips_fetching(self):
        library = self.root / "override"
        (library / "demo").mkdir(parents=True)
        (library / "demo/SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n")
        self.write_catalog("demo|git|https://example.invalid/r|main|skills/demo")
        result = self.run_script('prepare_skill_library && test "$PAYLOAD_SKILLS_DIR" = "' + str(library) + '"',
                                 env={"DOTFILES_SKILLS_DIR": str(library)})
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
