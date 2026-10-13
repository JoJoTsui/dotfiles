"""Resolve every pinned common and declared bundle environment per target.

This is deliberately network-enabled and opt-in. It creates one Pixi feature
per catalog environment and supported target, with all state confined to /tmp.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
TARGETS = {
    ("linux", "x86_64"): ("linux-64", "linux", "linux-64"),
    ("linux", "aarch64"): ("linux-aarch64", "linux", "linux-aarch64"),
    ("wsl", "x86_64"): ("linux-64", "wsl", "linux-64"),
    ("wsl", "aarch64"): ("linux-aarch64", "wsl", "linux-aarch64"),
    ("macos", "x86_64"): ("osx-64", "macos", "osx-64"),
    ("macos", "aarch64"): ("osx-arm64", "macos", "osx-arm64"),
    ("windows", "x86_64"): ("win-64", "windows", "win-64"),
}
PROFILES = (
    ("linux", "x86_64"), ("linux", "aarch64"),
    ("wsl", "x86_64"), ("wsl", "aarch64"),
    ("macos", "x86_64"), ("macos", "aarch64"), ("windows", "x86_64"),
)


def read_rows(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            yield line.split("|")


def dependencies(specifications):
    result = {}
    for specification in specifications.split(","):
        package, version = specification.rsplit("==", 1)
        result[package] = f"=={version}"
    return result


def version_pin(root, name):
    text = (root / "deployment/common.sh").read_text(encoding="utf-8")
    match = re.search(rf"^{name}=([^\r\n]+)$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"missing {name} manager pin")
    return match.group(1)


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_PACKAGE_RESOLUTION") == "1",
                     "requires explicit isolated Pixi resolution for all supported targets")
class PackageResolutionTests(unittest.TestCase):
    def test_common_and_supported_bundle_catalogs_resolve_on_every_declared_target(self):
        pixi = os.environ.get("DOTFILES_TEST_PIXI") or shutil.which("pixi")
        self.assertIsNotNone(pixi, "set DOTFILES_TEST_PIXI to the pinned Pixi binary")
        pixi = str(Path(pixi).resolve())
        self.assertTrue(Path(pixi).is_file())
        self.assertEqual(subprocess.check_output([pixi, "--version"], text=True).strip(),
                         "pixi " + version_pin(SOURCE, "PIXI_VERSION"))

        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-package-resolution-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        home = root / "home"
        home.mkdir()
        environment = {key: value for key, value in os.environ.items()
                       if key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                                  "SSL_CERT_FILE", "SSL_CERT_DIR")}
        environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                           XDG_DATA_HOME=str(home / ".local/share"),
                           XDG_CACHE_HOME=str(home / ".cache"), PIXI_HOME=str(home / ".pixi"),
                           PIXI_CACHE_DIR=str(home / ".cache/pixi"), CI="1")

        labels = {pair: ("win-64" if pair[0] == "windows" else "p-" + TARGETS[pair][0])
                  for pair in PROFILES}
        platforms = [
            '{ name = "p-linux-64", platform = "linux-64", glibc = "2.28" }',
            '{ name = "p-linux-aarch64", platform = "linux-aarch64", glibc = "2.28" }',
            '{ name = "p-osx-64", platform = "osx-64", macos = "14.2" }',
            '{ name = "p-osx-arm64", platform = "osx-arm64", macos = "14.2" }',
            '"win-64"',
        ]
        lines = ['[workspace]', 'name = "dotfiles-version-candidate"',
                 'channels = ["conda-forge"]', 'platforms = [' + ", ".join(platforms) + "]", ""]
        environments = []
        feature_count = 0

        def add_feature(name, target_label, channels, specs):
            nonlocal feature_count
            feature = f"resolve-{feature_count:04d}"
            feature_count += 1
            lines.extend([f"[feature.{json.dumps(feature)}]",
                          "platforms = [" + json.dumps(target_label) + "]",
                          "channels = " + json.dumps(channels),
                          f"[feature.{json.dumps(feature)}.dependencies]"])
            for package, constraint in specs.items():
                lines.append(f"{json.dumps(package)} = {json.dumps(constraint)}")
            lines.append("")
            environments.append((feature, name))

        for row in read_rows(SOURCE / "deployment/common-tools.tsv"):
            name, specifications, _exposed, targets = row[:4]
            for pair in PROFILES:
                _subdir, platform_name, _pixi_platform = TARGETS[pair]
                if targets == "unix" and platform_name == "windows":
                    continue
                if targets not in ("all", "unix"):
                    self.fail(f"unsupported common target selector {targets!r} in {name}")
                add_feature(f"common/{name}/{pair[0]}-{pair[1]}", labels[pair],
                            ["conda-forge"], dependencies(specifications))

        declarations = {}
        for bundle, supported, _prerequisites in read_rows(SOURCE / "deployment/bundles.tsv"):
            declarations[bundle] = set(supported.split(","))
        bundle_rows = list(read_rows(SOURCE / "deployment/bundle-tools.tsv"))
        for bundle, supported_targets in declarations.items():
            for pair in PROFILES:
                subdir, platform_name, _pixi_platform = TARGETS[pair]
                platform_role = f"{platform_name}-{pair[1]}"
                if platform_role not in supported_targets:
                    continue
                for row in bundle_rows:
                    row_bundle, environment_name, specifications, _exposed, channels, platforms_for_tool = row[:6]
                    if row_bundle != bundle:
                        continue
                    if platforms_for_tool != "all" and platform_name not in platforms_for_tool.split(","):
                        continue
                    add_feature(f"bundle/{bundle}/{environment_name}/{subdir}", labels[pair],
                                channels.split(","), dependencies(specifications))

        lines.append("[environments]")
        for index, (feature, _name) in enumerate(environments):
            lines.append(f"resolve-{index:04d} = {{ features = [{json.dumps(feature)}], no-default-feature = true }}")
        lines.append("")
        manifest = root / "pixi.toml"
        manifest.write_text("\n".join(lines), encoding="utf-8")
        result = subprocess.run([pixi, "lock", "--manifest-path", str(manifest), "--no-config",
                                 "--concurrent-solves", "4"], cwd=root, env=environment,
                                check=False, capture_output=True, text=True, timeout=1800)
        (root / "resolution.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-8000:])
        self.assertTrue((root / "pixi.lock").is_file(), "Pixi must write a real candidate lockfile")
        self.assertGreater(feature_count, 100, "resolution must cover common and specialist environments")


if __name__ == "__main__":
    unittest.main()
