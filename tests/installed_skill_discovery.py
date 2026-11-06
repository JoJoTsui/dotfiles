"""Verify the fetched default library with installed clients, without model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from deployment.update_skills import check as check_skill_lock, rows
from fixtures.skill_discovery import codex_prompt, command_catalog, opencode_skills, pi_resources, qoder_skills, resolve_skill_path
from native_linux import managed_environment


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def selected_inventory(home, source=SOURCE):
    catalog, lock = source / "deployment/skills.tsv", source / "deployment/skills.lock.tsv"
    check_skill_lock(catalog, lock)
    selected = {row[0] for row in rows(catalog, 6) if row[5] == "auto"}
    pins = {row[0]: row[:4] for row in rows(lock, 5) if row[0] in selected}
    installed = {row[0]: row for row in rows(home / ".local/state/dotfiles/skills.lock.tsv", 4)}
    require(selected and installed == pins, "deployed skill inventory differs from the default selection or reviewed lock")
    files = [home / ".agents/skills" / name / "SKILL.md" for name in sorted(selected)]
    adapter_roots = []
    for line in (source / "deployment/agent-payload/targets.tsv").read_text().splitlines():
        if line and not line.startswith("#"):
            kind, origin, destination = line.split("|")
            if (kind, origin) == ("tree", "skills"):
                adapter_roots.append(destination)
    for path in files:
        require(path.is_file() and not path.is_symlink(), "missing regular selected skill: " + path.parent.name)
        for relative in adapter_roots:
            adapter = home / relative / path.parent.name / "SKILL.md"
            require(adapter.is_file() and not adapter.is_symlink() and adapter.read_bytes() == path.read_bytes(),
                    "selected skill adapter differs from the fetched library: " + relative + "/" + path.parent.name)
    # Ruby/Psych is already a Docker fixture prerequisite. Parse independently
    # of each client so a dropped or renamed skill cannot validate itself.
    ruby = r'''
require "json"
require "yaml"
data = ARGV.map do |file|
  lines = File.read(file).lines
  raise "missing skill frontmatter" unless lines.first&.strip == "---"
  closing = lines.drop(1).index { |line| line.strip == "---" }
  raise "unterminated skill frontmatter" unless closing
  metadata = YAML.safe_load(lines[1..closing].join, aliases: true)
  raise "skill frontmatter must be a mapping" unless metadata.is_a?(Hash)
  { name: metadata["name"], description: metadata["description"],
    disabled: metadata.fetch("disable-model-invocation", false) }
end
puts JSON.generate(data)
'''
    parsed = subprocess.run(["ruby", "-e", ruby, *(str(path) for path in files)],
                            capture_output=True, text=True, timeout=30)
    require(parsed.returncode == 0, "selected skill frontmatter could not be parsed by the independent YAML oracle")
    metadata = json.loads(parsed.stdout)
    require(len(metadata) == len(files), "selected skill metadata output is incomplete")
    inventory = {}
    for path, item in zip(files, metadata):
        name = item["name"] if item["name"] is not None else path.parent.name
        require(isinstance(name, str) and bool(name.strip()), "selected skill has an invalid name: " + path.parent.name)
        require(isinstance(item["description"], str) and bool(item["description"].strip()),
                "selected skill has no description: " + path.parent.name)
        require(isinstance(item["disabled"], bool), "selected skill has an invalid invocation flag: " + path.parent.name)
        require(name not in inventory, "selected skills declare a duplicate discovery name: " + name)
        inventory[name] = {"catalog_name": path.parent.name, "path": str(path.resolve()),
                           "disable_model_invocation": item["disabled"],
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return inventory


def verify_names(expected, discovered):
    missing = sorted(set(expected) - set(discovered))
    require(not missing, "selected skills missing from discovery: " + ", ".join(missing))
    return {"expected_names": sorted(expected), "discovered_names": sorted(discovered),
            "selected_discovered_names": sorted(set(expected) & set(discovered)),
            "selected_count": len(expected), "discovered_count": len(discovered)}


def verify_records(inventory, records, *, home, name_key, path_key):
    by_name = {record[name_key]: record for record in records}
    result = verify_names(inventory, by_name)
    for name, expected in inventory.items():
        actual = resolve_skill_path(by_name[name][path_key], home)
        require(actual == Path(expected["path"]), "discovered skill path does not match selected metadata: " + name)
    return result


def private_client_environment(client, home, scratch, base):
    root = scratch / client
    root.mkdir(parents=True)
    env = dict(base, HOME=str(home), DO_NOT_TRACK="1", DISABLE_TELEMETRY="1", DISABLE_AUTOUPDATER="1",
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", CODEGRAPH_NO_DOWNLOAD="1", CODEGRAPH_NO_DAEMON="1")
    for variable, relative in (("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
                               ("XDG_STATE_HOME", "state"), ("TMPDIR", "tmp")):
        path = root / relative
        path.mkdir()
        env[variable] = str(path)
    # Preserve actual rendered configuration while isolating client migrations,
    # sessions and caches. Authentication files are intentionally never copied.
    settings = {
        "codex": ("CODEX_HOME", ".codex", ("config.toml", "AGENTS.md")),
        "claude": ("CLAUDE_CONFIG_DIR", ".claude", ("settings.json", "CLAUDE.md")),
        "kimi": ("KIMI_CODE_HOME", ".kimi-code", ("config.toml", "tui.toml", "mcp.json")),
        "pi": ("PI_CODING_AGENT_DIR", ".pi/agent", ("settings.json", "AGENTS.md")),
        "opencode": ("OPENCODE_CONFIG_DIR", ".config/opencode", ("opencode.jsonc", "AGENTS.md")),
    }
    if client in settings:
        variable, relative, names = settings[client]
        destination = root / "config"
        destination.mkdir()
        for name in names:
            origin = home / relative / name
            require(origin.is_file() and not origin.is_symlink(), "missing regular rendered client configuration: " + str(origin.relative_to(home)))
            shutil.copyfile(origin, destination / name)
        env[variable] = str(destination)
        if client == "opencode":
            env["OPENCODE_CONFIG"] = str(destination / "opencode.jsonc")
        if client == "claude":
            (destination / "skills").symlink_to(home / ".claude/skills", target_is_directory=True)
    return env


def discover_installed(home, scratch, tools, environment):
    inventory = selected_inventory(home)
    selected = set(inventory)
    automatic = {name for name, item in inventory.items() if not item["disable_model_invocation"]}
    scratch.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "home": str(home), "selected_inventory": inventory,
              "selected_count": len(selected), "manual_only_names": sorted(selected - automatic),
              "discovery_source": "installed selected skill files", "clients": {}}
    # Client migrations, caches and the Claude adapter symlink are ephemeral.
    # Only regular reports/logs may reach the outer gate's artifact inventory.
    with tempfile.TemporaryDirectory(prefix="client-runtime-", dir=scratch) as directory:
        runtime = Path(directory)
        project = runtime / "project"
        project.mkdir()
        for client in ("pi", "opencode", "codex", "claude", "kimi", "qoder"):
            try:
                env = private_client_environment(client, home, runtime, environment)
                log = scratch / (client + ".log")
                if client == "pi":
                    data = pi_resources(tools["node"], tools["pi_module"], cwd=project, env=env, log=log)
                    result = verify_records(inventory, data["skills"], home=home, name_key="name", path_key="filePath")
                    by_name = {record["name"]: record for record in data["skills"]}
                    for name, item in inventory.items():
                        require(by_name[name]["disableModelInvocation"] == item["disable_model_invocation"],
                                "Pi invocation metadata differs: " + name)
                    prompt_names = set(re.findall(r"<name>([^<]+)</name>", data["prompt"]))
                    verify_names(automatic, prompt_names)
                    require(not ((selected - automatic) & prompt_names), "Pi automatically advertised manual-only selected skills")
                    result["diagnostics"] = data.get("diagnostics", [])
                    result["automatic_names"] = sorted(automatic)
                elif client == "opencode":
                    records = opencode_skills(tools[client], home=home, cwd=project, env=env, log=log,
                                              expected=selected, timeout=60)
                    result = verify_records(inventory, records, home=home, name_key="id", path_key="path")
                    by_name = {record["id"]: record for record in records}
                    automatic_flag_not_exposed = []
                    for name, item in inventory.items():
                        if "autoinvoke" in by_name[name]:
                            require(by_name[name]["autoinvoke"] is (not item["disable_model_invocation"]),
                                    "OpenCode invocation metadata differs: " + name)
                        else:
                            require(not item["disable_model_invocation"],
                                    "OpenCode manual invocation metadata is missing: " + name)
                            automatic_flag_not_exposed.append(name)
                    # The API omits the optional flag for ordinary skills.
                    # Discovery alone does not prove their automatic invocation.
                    result["automatic_flag_not_exposed_names"] = sorted(automatic_flag_not_exposed)
                    result["explicit_invocation_metadata_names"] = sorted(selected - set(automatic_flag_not_exposed))
                elif client == "codex":
                    text = codex_prompt(tools[client], cwd=project, env=env, log=log)
                    names = set(re.findall(r"(?m)^- (.+?):\s", text))
                    result = verify_names(automatic, names)
                    result["projection"] = "automatic skills in assembled prompt"
                elif client in ("claude", "kimi"):
                    names = command_catalog(client, tools[client], cwd=project, env=env, log=log)
                    result = verify_names(selected, {name.removeprefix("skill:") for name in names})
                else:
                    records = qoder_skills(tools[client], cwd=project, env=env, log=log)
                    result = verify_records(inventory, records, home=home, name_key="name", path_key="path")
                report["clients"][client] = {"passed": True, **result}
            except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError, TimeoutError) as error:
                report["clients"][client] = {"passed": False, "error": str(error)}
    report["status"] = "passed" if all(result["passed"] for result in report["clients"].values()) else "failed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    require(args.home.is_absolute() and args.home == args.home.resolve(), "installed home must be canonical and absolute")
    require(args.artifacts.is_absolute() and not args.artifacts.exists(), "discovery artifacts must be fresh and absolute")
    args.artifacts.mkdir(parents=True)
    home = args.home
    tools = {name: str(home / ".local/bin" / name) for name in ("opencode", "codex", "claude", "kimi", "qoder")}
    tools.update(node=str(home / ".pixi/bin/node"),
                 pi_module=str(home / ".bun/managed/pi/node_modules/@earendil-works/pi-coding-agent/dist/index.js"))
    try:
        report = discover_installed(home, args.artifacts, tools, managed_environment(home, args.artifacts))
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report = {"status": "failed", "home": str(home), "selected_count": 0,
                  "clients": {}, "error": str(error)}
    (args.artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "selected_count": report["selected_count"],
                      **({"error": report["error"]} if "error" in report else {}),
                      "clients": {name: {key: value for key, value in result.items() if key in ("passed", "selected_count", "error")}
                                  for name, result in report["clients"].items()}}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
