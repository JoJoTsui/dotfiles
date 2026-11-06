"""Offline diagnostics shared by fixture and installed-library acceptance."""
import base64
import json
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import threading
import time
import urllib.request
from urllib.parse import unquote, urlencode, urlparse

from fixtures.processes import stop_client


def resolve_skill_path(value, home):
    raw_value = str(value)
    if Path(raw_value).is_absolute():
        return Path(raw_value).resolve()
    parsed = urlparse(raw_value)
    if parsed.scheme not in ("", "file"):
        return None
    if parsed.scheme == "file":
        if unquote(parsed.netloc) == "~":
            raw = "~" + unquote(parsed.path)
        elif parsed.netloc in ("", "localhost"):
            raw = (unquote(parsed.path)[1:] if parsed.path.startswith("/~/")
                   else urllib.request.url2pathname(parsed.path))
        else:
            return None
    else:
        raw = raw_value
    if raw.startswith("/~/"):
        raw = raw[1:]
    if raw == "~":
        return home.resolve()
    path = home / raw[2:] if raw.startswith("~/") else Path(raw)
    return (home / path if not path.is_absolute() else path).resolve()


def _text_command(command, *, cwd, env, log):
    with Path(log).open("w") as errors:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=errors, text=True,
                                   start_new_session=os.name != "nt")
        try:
            stdout, _ = process.communicate(timeout=30)
        finally:
            stop_client(process)
        if process.returncode:
            raise RuntimeError(f"client discovery exited {process.returncode}; see {Path(log).name}")
        return stdout


def _json_command(command, *, cwd, env, log):
    return json.loads(_text_command(command, cwd=cwd, env=env, log=log))


def codex_prompt(binary, *, cwd, env, log):
    messages = _json_command([binary, "debug", "prompt-input"], cwd=cwd, env=env, log=log)
    return "\n".join(part.get("text", "") for message in messages for part in message.get("content", []))


def pi_resources(node, module, *, cwd, env, log):
    script = """
const {DefaultResourceLoader,SettingsManager,formatSkillsForPrompt} = await import(process.argv[1]);
const settingsManager=SettingsManager.create(process.cwd(),process.env.PI_CODING_AGENT_DIR);
const loader=new DefaultResourceLoader({cwd:process.cwd(),agentDir:process.env.PI_CODING_AGENT_DIR,settingsManager,
  noExtensions:true,noThemes:true,noPromptTemplates:true});
await loader.reload();
const {skills,diagnostics}=loader.getSkills();
console.log(JSON.stringify({skills:skills.map(skill=>({name:skill.name,filePath:skill.filePath,
  disableModelInvocation:skill.disableModelInvocation===true})),diagnostics,
  prompt:formatSkillsForPrompt(skills),instructions:loader.getAgentsFiles().agentsFiles}));
"""
    return _json_command([node, "--input-type=module", "-e", script, Path(module).as_uri()],
                         cwd=cwd, env=env, log=log)


def qoder_skill_records(text):
    records = []
    pending = None
    for line in text.splitlines():
        match = re.fullmatch(r"([^\s]+) \[(Enabled|Disabled)\]", line.strip())
        if match:
            if pending is not None:
                raise ValueError("Qoder skill record has no location")
            pending = {"name": match[1], "enabled": match[2] == "Enabled"}
        elif line.lstrip().startswith("Location:"):
            if pending is None:
                raise ValueError("Qoder skill location has no name")
            pending["path"] = line.split("Location:", 1)[1].strip()
            records.append(pending)
            pending = None
    if pending is not None:
        raise ValueError("Qoder skill record has no location")
    return records


def qoder_skills(binary, *, cwd, env, log):
    return qoder_skill_records(_text_command([binary, "skills", "list"], cwd=cwd, env=env, log=log))


def opencode_skills(binary, *, home, cwd, env, log, expected, timeout=12):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = dict(env, OPENCODE_SERVER_PASSWORD="synthetic-payload-test")
    environment.setdefault("OPENCODE_CONFIG_DIR", str(home / ".config/opencode"))
    environment.setdefault("OPENCODE_CONFIG", str(home / ".config/opencode/opencode.jsonc"))
    location = urlencode({"location[directory]": str(cwd)})
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/skill?{location}")
    request.add_header("Authorization", "Basic " + base64.b64encode(b"opencode:synthetic-payload-test").decode())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with Path(log).open("w") as errors:
        process = subprocess.Popen([binary, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
                                   cwd=cwd, env=environment, stdout=errors, stderr=errors,
                                   start_new_session=os.name != "nt")
        try:
            deadline = time.monotonic() + timeout
            records = []
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    records = json.loads(opener.open(request, timeout=2).read())["data"]
                    if expected.issubset({item["id"] for item in records}):
                        break
                except OSError:
                    pass
                time.sleep(0.1)
            return records
        finally:
            stop_client(process)


def command_catalog(client, binary, *, cwd, env, log):
    if client == "claude":
        env = dict(env, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                   DISABLE_TELEMETRY="1", DISABLE_AUTOUPDATER="1")
        command = [binary, "--print", "--input-format", "stream-json", "--output-format", "stream-json",
                   "--verbose", "--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                   "--settings", '{"env":{"ANTHROPIC_BASE_URL":"http://127.0.0.1:9","ANTHROPIC_AUTH_TOKEN":"synthetic"}}']
    elif client == "kimi":
        command = [binary, "acp"]
    else:
        raise ValueError("unsupported command-catalog client")
    with Path(log).open("w") as errors:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=errors, text=True,
                                   start_new_session=os.name != "nt")
        inbox = queue.Queue()
        def collect():
            try:
                for line in process.stdout:
                    inbox.put(json.loads(line))
            except (ValueError, OSError):
                inbox.put({"discovery_error": "invalid client protocol output"})
        reader = threading.Thread(target=collect, daemon=True)
        reader.start()
        deadline = time.monotonic() + 30
        def send(message):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        def receive():
            try:
                message = inbox.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty as error:
                raise RuntimeError("client command discovery timed out") from error
            if "discovery_error" in message:
                raise RuntimeError(message["discovery_error"])
            return message
        try:
            if client == "claude":
                send({"type": "control_request", "request_id": "discovery", "request": {"subtype": "initialize"}})
                while True:
                    message = receive()
                    if message.get("type") == "control_response":
                        return {item["name"] for item in message["response"]["response"]["commands"]}
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": 1, "clientCapabilities": {}}})
            while True:
                message = receive()
                if message.get("id") == 1:
                    if "result" not in message:
                        raise RuntimeError("Kimi initialization failed")
                    break
            send({"jsonrpc": "2.0", "id": 2, "method": "session/new",
                  "params": {"cwd": str(cwd), "mcpServers": []}})
            while True:
                message = receive()
                update = message.get("params", {}).get("update", {})
                if update.get("sessionUpdate") == "available_commands_update":
                    return {item["name"] for item in update["availableCommands"]}
        finally:
            stop_client(process)
            process.stdin.close()
            reader.join(timeout=5)
            process.stdout.close()
