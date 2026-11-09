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

    def run_script(self, body, env=None, home=None):
        home = home or self.root
        script = self.root / "run.sh"
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{self.source}'\n"
            f"DEPLOY_HOME='{home}'\n"
            f"export XDG_CACHE_HOME='{home}/xdg-cache' XDG_STATE_HOME='{home}/xdg-state' TMPDIR='{self.tmp}'\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            f"source '{SOURCE}/deployment/skills.sh'\n"
            f"source '{SOURCE}/deployment/payload.sh'\n"
            + body,
            encoding="utf-8")
        environment = dict(os.environ, **(env or {}))
        return subprocess.run(["/bin/bash", str(script)], env=environment,
                              capture_output=True, text=True, timeout=120)

    def write_catalog(self, *rows, reviewed=True):
        # The catalog carries a selection column; these rows are automatic
        # unless a test names its own selection.
        rows = [row if len(row.split('|')) >= 6 else row + '|auto' for row in rows]
        self.catalog.write_text("# name|kind|source|ref|path|selection\n" + "\n".join(rows) + "\n")
        if reviewed:
            # Fetch fixtures pin the actual local bytes. Catalog-validation and
            # hermetic-library cases do not need an upstream lock.
            pins = []
            for row in rows:
                name, kind, source, ref, _, selection = row.split('|')
                if kind == "git":
                    pin = subprocess.check_output(
                        ["git", "-C", source, "rev-parse", ref], text=True).strip()
                else:
                    self.assertTrue(source.startswith("file://"))
                    pin = hashlib.sha256(Path(source[7:]).read_bytes()).hexdigest()
                pins.append(f"{name}|{kind}|{source}|{pin}|{selection}")
            (self.catalog.parent / "skills.lock.tsv").write_text(
                "# name|kind|source|resolved|selection\n" + "\n".join(pins) + "\n")

    def make_git_repo(self, name, path="skills/demo"):
        repo = self.root / name
        skill = repo / path
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\nbody\n")
        (skill / "note.md").write_text("note\n")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        # Model upstreams that serve a locked ancestor after the branch advances.
        subprocess.run(["git", "-C", str(repo), "config", "uploadpack.allowReachableSHA1InWant", "true"], check=True)
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

    def test_portable_layout_keeps_upstream_bytes_and_relative_references(self):
        repo = self.make_git_repo("portable-repo", "graphify")
        skill = repo / "graphify"
        (skill / "SKILL.md").rename(skill / "skill-agents.md")
        refs = skill / "skills/agents/references"
        refs.mkdir(parents=True)
        (refs / "query.md").write_text("official reference bytes\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "portable layout"], check=True)
        self.write_catalog(f"graphify|git|{repo}|main|graphify")
        (self.catalog.parent / "skill-layouts.tsv").write_text(
            "graphify|skill-agents.md|SKILL.md\ngraphify|skills/agents/references|references\n")
        result = self.run_script('prepare_skill_library\n'
                                 f'cmp "{skill}/skill-agents.md" "$PAYLOAD_SKILLS_DIR/graphify/SKILL.md"\n'
                                 f'cmp "{refs}/query.md" "$PAYLOAD_SKILLS_DIR/graphify/references/query.md"\n'
                                 'test ! -e "$PAYLOAD_SKILLS_DIR/graphify/note.md"\n')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_layout_cannot_escape_its_destination(self):
        repo = self.make_git_repo("unsafe-layout")
        self.write_catalog(f"demo|git|{repo}|main|skills/demo")
        (self.catalog.parent / "skill-layouts.tsv").write_text("demo|SKILL.md|../escaped\n")
        result = self.run_script('prepare_skill_library')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.tmp / "escaped").exists())

    def test_root_skill_layout_keeps_metadata_and_excludes_repository_tools(self):
        repo = self.make_git_repo("root-skill-repo", ".")
        metadata = repo / "agents/openai.yaml"
        metadata.parent.mkdir()
        metadata.write_text('interface:\n  display_name: "Root skill"\n')
        (repo / "LICENSE").write_text("synthetic license\n")
        (repo / "AGENTS.md").write_text("repository maintainer instructions\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "root layout"], check=True)
        self.write_catalog(f"demo|git|{repo}|main|.")
        (self.catalog.parent / "skill-layouts.tsv").write_text(
            "demo|SKILL.md|SKILL.md\ndemo|agents/openai.yaml|agents/openai.yaml\ndemo|LICENSE|LICENSE\n")
        result = self.run_script('prepare_skill_library\nprintf "%s" "$PAYLOAD_SKILLS_DIR"')
        self.assertEqual(result.returncode, 0, result.stderr)
        copied = Path(result.stdout) / "demo"
        self.assertEqual({p.relative_to(copied).as_posix() for p in copied.rglob("*") if p.is_file()},
                         {"SKILL.md", "agents/openai.yaml", "LICENSE"})
        for relative in ("SKILL.md", "agents/openai.yaml", "LICENSE"):
            self.assertEqual((copied / relative).read_bytes(), (repo / relative).read_bytes())

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

    def test_symlinked_skill_state_is_rejected_before_fetching(self):
        archive = self.make_tarball("arc")
        self.write_catalog(f"arc|tarball|file://{archive}||")
        state = self.root / "xdg-state/dotfiles/skills.lock.tsv"
        state.parent.mkdir(parents=True)
        outside = self.root / "outside"
        outside.write_text("preserve outside\n")
        state.symlink_to(outside)
        result = self.run_script("prepare_skill_library")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(outside.read_text(), "preserve outside\n")
        self.assertFalse((self.root / "xdg-cache").exists())

    def test_skill_cache_symlinks_are_rejected_before_writes(self):
        self.write_catalog()
        for index, relative in enumerate((
                "xdg-cache", "xdg-cache/dotfiles", "xdg-cache/dotfiles/skills",
                "xdg-cache/dotfiles/skills/git", "xdg-cache/dotfiles/skills/tarballs",
                "xdg-cache/dotfiles/skills/.refreshed")):
            with self.subTest(path=relative):
                home = self.root / f"home-{index}"
                outside = self.root / f"outside-{index}"
                outside.mkdir()
                sentinel = outside / "preserve"
                sentinel.write_text("preserve outside\n")
                target = home / relative
                target.parent.mkdir(parents=True)
                target.symlink_to(sentinel if relative.endswith(".refreshed") else outside)
                result = self.run_script("prepare_skill_library", home=home)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn("symlink", result.stderr)
                self.assertEqual(sentinel.read_text(), "preserve outside\n")
                self.assertEqual(sorted(path.name for path in outside.iterdir()), ["preserve"])
                self.assertEqual(list(self.tmp.iterdir()), [])

    def test_nested_git_cache_symlink_is_rejected_before_fetching(self):
        repo = self.make_git_repo("demo-repo")
        self.write_catalog(f"demo|git|{repo}|main|skills/demo")
        result = self.run_script("prepare_skill_library\ncleanup_skill_library")
        self.assertEqual(result.returncode, 0, result.stderr)
        cached_repo = next((self.root / "xdg-cache/dotfiles/skills/git").iterdir())
        config = cached_repo / ".git/config"
        outside = self.root / "outside-config"
        outside.write_bytes(config.read_bytes())
        config.unlink()
        config.symlink_to(outside)
        before = outside.read_bytes()
        result = self.run_script("prepare_skill_library")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(outside.read_bytes(), before)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_archive_cache_and_download_symlinks_are_rejected(self):
        archive = self.make_tarball("arc")
        self.write_catalog(f"arc|tarball|file://{archive}||")
        outside = self.root / "outside-archive"
        outside.write_bytes(archive.read_bytes())
        before = outside.read_bytes()
        for suffix in ("", ".part.$$"):
            with self.subTest(suffix=suffix):
                home = self.root / ("archive-home" if not suffix else "download-home")
                result = self.run_script(
                    'cache=$(skills_cache_root)\n'
                    'mkdir -p "$cache/tarballs"\n'
                    f"slug=$(skill_slug 'file://{archive}')\n"
                    f'ln -s \'{outside}\' "$cache/tarballs/$slug.tgz{suffix}"\n'
                    'prepare_skill_library', home=home)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn("symlink", result.stderr)
                self.assertEqual(outside.read_bytes(), before)
                self.assertEqual(list(self.tmp.iterdir()), [])

    def test_explicit_external_skill_cache_is_supported(self):
        archive = self.make_tarball("arc")
        self.write_catalog(f"arc|tarball|file://{archive}||")
        # /tmp is a system symlink on macOS, above this deliberately chosen
        # cache root. It does not turn the cache itself into a symlink.
        external = tempfile.TemporaryDirectory(prefix="dotfiles-skills-cache-", dir="/tmp")
        self.addCleanup(external.cleanup)
        cache = Path(external.name) / "skills"
        result = self.run_script("prepare_skill_library", env={"DOTFILES_SKILLS_CACHE": str(cache)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((cache / ".refreshed").is_file())
        self.assertEqual(len(list((cache / "tarballs").glob("*.tgz"))), 1)
        self.assertFalse((self.root / "xdg-cache").exists())

    def test_skill_state_replacement_is_regular_private_and_preserves_failed_fetch(self):
        archive = self.make_tarball("arc")
        self.write_catalog(f"arc|tarball|file://{archive}||")
        state = self.root / "xdg-state/dotfiles/skills.lock.tsv"
        state.parent.mkdir(parents=True)
        state.write_text("previous state\n")
        result = self.run_script("prepare_skill_library")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(state.is_file())
        self.assertFalse(state.is_symlink())
        self.assertEqual(state.stat().st_mode & 0o777, 0o600)
        self.assertIn("arc|tarball|", state.read_text())
        before = state.read_bytes()
        self.write_catalog("broken|tarball|file:///nonexistent-skill-archive||", reviewed=False)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (self.catalog.parent / "skills.lock.tsv").write_text(
            f"broken|tarball|file:///nonexistent-skill-archive|{digest}|auto\n")
        result = self.run_script("sleep() { :; }\nprepare_skill_library")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state.read_bytes(), before)
        self.assertEqual(list(state.parent.glob(".skills.lock.*")), [])

    def test_public_preflight_rejects_skill_state_symlink_before_preparing_home(self):
        home = self.root / "selected"
        state = home / ".local/state/dotfiles/skills.lock.tsv"
        state.parent.mkdir(parents=True)
        outside = self.root / "outside"
        outside.write_text("preserve outside\n")
        state.symlink_to(outside)
        result = subprocess.run(
            ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--home", str(home),
             "--platform", "macos", "--apply-only"],
            env={"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(outside.read_text(), "preserve outside\n")
        self.assertFalse((home / ".config").exists())

    def test_failed_refresh_reuses_cache_without_advancing_timestamp(self):
        archive = self.make_tarball('arc')
        self.write_catalog(f'arc|tarball|file://{archive}||')
        first = self.run_script('prepare_skill_library')
        self.assertEqual(first.returncode, 0, first.stderr)
        marker = self.root / 'xdg-cache/dotfiles/skills/.refreshed'
        marker.write_text('1\n')
        archive.rename(self.root / 'offline-archive')
        result = self.run_script('sleep() { :; }\nprepare_skill_library',
                                 env={'DOTFILES_SKILLS_REFRESH': '1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(), '1\n')

    def test_catalog_rejects_duplicates_and_unsafe_paths(self):
        self.write_catalog("demo|git|https://example.invalid/r|main|/absolute", reviewed=False)
        result = self.run_script("validate_skill_catalog")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("relative", result.stderr)
        self.write_catalog("demo|git|https://example.invalid/r|main|skills/demo",
                           "demo|git|https://example.invalid/r2|main|skills/demo", reviewed=False)
        result = self.run_script("validate_skill_catalog")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr)

    def test_missing_skill_lock_is_rejected_before_fetching(self):
        repo = self.make_git_repo("demo-repo")
        archive = self.make_tarball("arc")
        for kind, row in (("git", f"demo|git|{repo}|main|skills/demo"),
                          ("tarball", f"arc|tarball|file://{archive}||")):
            for override in (False, True):
                with self.subTest(kind=kind, override=override):
                    self.write_catalog(row)
                    lock = self.catalog.parent / "skills.lock.tsv"
                    env = {}
                    if override:
                        env["DOTFILES_SKILLS_LOCK"] = str(self.root / "missing.lock.tsv")
                    else:
                        lock.unlink()
                    home = self.root / f"missing-{kind}-{override}"
                    result = self.run_script("prepare_skill_library", env=env, home=home)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertIn("skill lock", result.stderr)
                    self.assertFalse((home / "xdg-cache").exists())
                    self.assertFalse((home / "xdg-state").exists())
                    self.assertEqual(list(self.tmp.iterdir()), [])

    def test_invalid_skill_lock_pins_are_rejected(self):
        repo = self.make_git_repo("demo-repo")
        self.write_catalog(f"demo|git|{repo}|main|skills/demo")
        lock = self.catalog.parent / "skills.lock.tsv"
        valid = lock.read_text()
        for content, expected in (("# no matching entry\n", "missing skill pin"),
                                  (f"demo|git|{repo}|not-a-pin|auto\n", "invalid"),
                                  (valid + valid, "duplicate"),
                                  (valid.replace(str(repo), "different-source"), "source mismatch")):
            with self.subTest(content=content):
                lock.write_text(content)
                result = self.run_script("prepare_skill_library")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertFalse((self.root / "xdg-state").exists())

    def test_explicit_reviewed_skill_lock_is_supported(self):
        archive = self.make_tarball("arc")
        self.write_catalog(f"arc|tarball|file://{archive}||")
        lock = self.root / "reviewed.lock.tsv"
        (self.catalog.parent / "skills.lock.tsv").rename(lock)
        result = self.run_script("prepare_skill_library",
                                 env={"DOTFILES_SKILLS_LOCK": str(lock)})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_git_lock_keeps_reviewed_revision_after_upstream_changes(self):
        repo = self.make_git_repo('demo-repo')
        self.write_catalog(f'demo|git|{repo}|main|skills/demo')
        (repo / 'skills/demo/note.md').write_text('unreviewed update\n')
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                        'commit', '-qm', 'update'], check=True)
        result = self.run_script('prepare_skill_library\ncat "$PAYLOAD_SKILLS_DIR/demo/note.md"\n',
                                 env={"DOTFILES_SKILLS_REFRESH": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'note\n')

    def test_archive_checksum_mismatch_preserves_verified_cache(self):
        archive = self.make_tarball('arc')
        self.write_catalog(f'arc|tarball|file://{archive}||')
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
        catalog_before = self.catalog.read_bytes()
        lock = self.catalog.parent / 'skills.lock.tsv'
        # Explicit updates may create a lock; deployment must require it.
        lock.unlink()
        import sys
        command = [sys.executable, str(SOURCE / 'deployment/update_skills.py'), 'refresh',
                   '--catalog', str(self.catalog), '--lock', str(lock)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        old = lock.read_bytes()
        (repo / 'skills/demo/note.md').write_text('reviewed update\n')
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                        'commit', '-qm', 'update'], check=True)
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(lock.read_bytes(), old)
        revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertIn(revision, lock.read_text())
        self.assertEqual(self.catalog.read_bytes(), catalog_before)
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

    def test_tagged_skills_are_not_deployed_without_a_request(self):
        repo = self.make_git_repo("tagged-repo")
        self.write_catalog(f"demo|git|{repo}|main|skills/demo",
                           f"tagged|git|{repo}|main|skills/demo|manual")
        result = self.run_script('prepare_skill_library && ls "$PAYLOAD_SKILLS_DIR"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("demo", result.stdout)
        self.assertNotIn("tagged", result.stdout)

    def test_a_tagged_skill_is_deployed_when_the_host_asks_for_it(self):
        repo = self.make_git_repo("tagged-repo")
        self.write_catalog(f"tagged|git|{repo}|main|skills/demo|manual")
        result = self.run_script('prepare_skill_library && ls "$PAYLOAD_SKILLS_DIR"',
                                 env={"DOTFILES_SKILLS": "manual"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tagged", result.stdout)

    def test_override_library_skips_fetching(self):
        library = self.root / "override"
        (library / "demo").mkdir(parents=True)
        (library / "demo/SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n")
        self.write_catalog("demo|git|https://example.invalid/r|main|skills/demo", reviewed=False)
        result = self.run_script('prepare_skill_library && test "$PAYLOAD_SKILLS_DIR" = "' + str(library) + '"',
                                 env={"DOTFILES_SKILLS_DIR": str(library)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.catalog.parent / "skills.lock.tsv").exists())
        self.assertFalse((self.root / "xdg-cache").exists())


class SkillCollisionTests(unittest.TestCase):
    """A name in two roots of one client is a warning in that client."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-skills-collision-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()

    def write_skill(self, relative, name):
        directory = self.home / relative / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(f"---\nname: {name}\ndescription: demo\n---\nbody\n")

    def run_report(self):
        script = self.root / "report.sh"
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{SOURCE}'\n"
            f"export HOME='{self.home}' TMPDIR='{self.tmp}'\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            f"source '{SOURCE}/deployment/payload.sh'\n"
            "report_skill_collisions\n",
            encoding="utf-8")
        return subprocess.run(["/bin/bash", str(script)], capture_output=True,
                              text=True, timeout=120)

    def test_reports_a_name_the_shared_tree_and_the_client_root_share(self):
        self.write_skill(".agents/skills", "impeccable")
        self.write_skill(".pi/agent/skills", "impeccable")
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("impeccable", result.stderr)
        self.assertIn(".pi/agent/skills", result.stderr)

    def test_a_name_only_one_root_provides_is_not_reported(self):
        self.write_skill(".agents/skills", "impeccable")
        self.write_skill(".pi/agent/skills", "other")
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), "")


if __name__ == "__main__":
    unittest.main()
