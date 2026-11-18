"""Runtime evidence for the Codex resume command against fake providers.

The harness is deliberately value free: the fake providers record the model
and the reasoning effort they received, never a credential. Every endpoint
binds an ephemeral loopback port, so the live Magpie gateway on 127.0.0.1:3425
is never part of an experiment.
"""
import errno
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIVE_GATEWAY_PORT = 3425

# The update prompt of a fresh Codex home offers to run the upgrade. The
# driver must never be able to accept it: the synthetic home turns the
# startup update check off, and the driver refuses to continue when the
# prompt is on the screen.
UPDATE_PROMPT_MARKERS = ("Update available", "Update now", "brew upgrade")
# The picker has rendered when its own footer is on the screen. These are
# the header and the footer of the picker: they are on the screen while the
# session list is still loading, so they do not tell a list with rows.
PICKER_MARKERS = ("enter resume", "browse", "Resume a previous session", "No sessions yet")
# The counter of the picker: "0 / 0… · 0%" while the list is loading, and
# "1 / 4" once the rows are there.
SESSION_COUNTER = re.compile(r"(\d+)\s*/\s*(\d+)")
# The thread view has rendered when the composer is on the screen.
THREAD_MARKERS = ("Ask Codex to do anything", "Ask a follow-up question")

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[@-Z\\-_]")

# Every request gets a sequence number of its own, so the requests of the
# several fake providers can be put back in the order they arrived in.
REQUEST_SEQUENCE = itertools.count()

SSE_EVENTS = (
    ("response.created", {"type": "response.created", "response": {"id": "resp_probe"}}),
    (
        "response.output_item.done",
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "id": "msg_probe",
                "content": [{"type": "output_text", "text": "ok"}],
            },
        },
    ),
    (
        "response.completed",
        {
            "type": "response.completed",
            "response": {
                "id": "resp_probe",
                "usage": {
                    "input_tokens": 0,
                    "input_tokens_details": None,
                    "output_tokens": 0,
                    "output_tokens_details": None,
                    "total_tokens": 0,
                },
            },
        },
    ),
)

SHIM = '''#!/usr/bin/env python3
"""Record the argv a caller hands to codex, then run the real app-server.

The managed command is exercised through this shim: the argv it builds is the
argv the app-server is started with, so the provider layer under test is the
layer the command really produced.
"""
import json
import os
import pathlib
import sys

record = pathlib.Path(os.environ["PROBE_CODEX_RECORD"])
with record.open("a") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")

argv = sys.argv[1:]
if argv[:1] != ["resume"]:
    os.execvp(os.environ["PROBE_REAL_CODEX"], [os.environ["PROBE_REAL_CODEX"], *argv])

overrides = []
index = 0
while index < len(argv):
    if argv[index] == "-c" and index + 1 < len(argv):
        overrides += ["-c", argv[index + 1]]
        index += 2
        continue
    if argv[index].startswith("--config="):
        overrides += ["-c", argv[index].split("=", 1)[1]]
    index += 1

real = os.environ["PROBE_REAL_CODEX"]
os.execv(real, [real, "app-server", *overrides])
'''


def session_list_loaded(text):
    """Whether the picker's session list has rows.

    The picker renders in two stages: the header and the footer are on the
    screen while the list is still loading ("Loading sessions…", and the
    counter "0 / 0… · 0%"). A Return sent in that state accepts no row: the
    picker stays on the screen and no thread is resumed.

    The list has rows when the picker shows its counter with a non-zero
    total ("1 / 4"): that is the first moment at which a row can be
    chosen. The counter of the loading stage ("0 / 0… · 0%") has a total of
    zero, so it never satisfies this rule.
    """
    for match in SESSION_COUNTER.finditer(text):
        current = int(match.group(1))
        total = int(match.group(2))
        if 1 <= current <= total:
            return True
    return False


def plain(text):
    """The screen text without the terminal's own control sequences."""
    text = ANSI_ESCAPE.sub("", text)
    text = text.replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text)


def user_text(payload):
    """The tail of the user input of a request, never the instructions.

    The prompt of a turn is the last thing the user sent, so the tail is
    what identifies the request. The instructions of Codex are not part of
    the input and are never recorded.
    """
    parts = []
    for item in payload.get("input") or []:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        for piece in content or []:
            if isinstance(piece, dict) and piece.get("type") in ("input_text", "text"):
                parts.append(str(piece.get("text") or ""))
    return "\n".join(parts)[-200:]


class FakeProvider:
    """A Responses API over SSE that records what the client sent."""

    def __init__(self, label):
        self.label = label
        self.requests = []
        self.lock = threading.Lock()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = {}
                reasoning = payload.get("reasoning") or {}
                items = payload.get("input") or []
                record = {
                    "seq": next(REQUEST_SEQUENCE),
                    "label": provider.label,
                    "path": self.path,
                    "model": payload.get("model"),
                    "effort": reasoning.get("effort"),
                    "bearer": bool(self.headers.get("Authorization")),
                    "actor": self.headers.get("x-openai-actor-authorization"),
                    "prompt_cache_key": payload.get("prompt_cache_key"),
                    "input_items": len(items),
                    "input_chars": len(json.dumps(items)),
                    "user_text": user_text(payload),
                }
                with provider.lock:
                    provider.requests.append(record)
                body = "".join(
                    "event: %s\ndata: %s\n\n" % (kind, json.dumps(data))
                    for kind, data in SSE_EVENTS
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self):
        return "http://127.0.0.1:%d/v1" % self.port

    def received(self):
        with self.lock:
            return list(self.requests)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class AppServerClient:
    """A JSON-RPC client for the Codex app-server over stdio.

    The command under test is the process that is spawned, so the provider
    layer the app-server loads is the layer that command built.
    """

    def __init__(self, argv, env, cwd, timeout=60.0):
        self.process = subprocess.Popen(
            argv,
            env=env,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.messages = []
        self.errors = []
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_errors, daemon=True).start()
        self.next_id = 1
        self.initialize_response = self.initialize(timeout)

    def _read(self):
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            with self.lock:
                self.messages.append(message)

    def _read_errors(self):
        for line in self.process.stderr:
            self.errors.append(line.rstrip())

    def send(self, method, params=None, notify=False):
        message = {"jsonrpc": "2.0", "method": method}
        if not notify:
            message["id"] = self.next_id
            self.next_id += 1
        if params is not None:
            message["params"] = params
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, ValueError):
            return None
        return message.get("id")

    def wait_for(self, request_id, timeout=45.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                for message in self.messages:
                    if message.get("id") == request_id:
                        return message
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
        return None

    def initialize(self, timeout=45.0):
        request_id = self.send(
            "initialize",
            {
                "clientInfo": {
                    "name": "ticket10-probe",
                    "title": "Ticket 10 probe",
                    "version": "0.1",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        response = self.wait_for(request_id, timeout)
        self.send("initialized", notify=True)
        return response

    def resume(self, thread_id, model=None, model_provider=None):
        params = {"threadId": thread_id}
        if model is not None:
            params["model"] = model
        if model_provider is not None:
            params["modelProvider"] = model_provider
        request_id = self.send("thread/resume", params)
        return self.wait_for(request_id)

    def turn(self, thread_id, text):
        request_id = self.send(
            "turn/start",
            {"threadId": thread_id, "input": [{"type": "text", "text": text}]},
        )
        return self.wait_for(request_id)

    def close(self):
        try:
            self.process.stdin.close()
        except Exception:
            pass
        try:
            self.process.wait(timeout=5)
        except Exception:
            self.process.kill()
        for stream in (self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except Exception:
                pass


def thread_ids(codex_home):
    """Every recorded thread with the provider it was created with."""
    found = []
    sessions = Path(codex_home) / "sessions"
    if not sessions.exists():
        return found
    for path in sorted(sessions.rglob("*.jsonl")):
        try:
            with path.open(encoding="utf-8") as handle:
                first = handle.readline()
        except OSError:
            continue
        if not first:
            continue
        try:
            payload = json.loads(first).get("payload", {})
        except ValueError:
            continue
        identifier = payload.get("id")
        if identifier:
            found.append(
                {
                    "id": identifier,
                    "provider": payload.get("model_provider"),
                    "source": payload.get("source"),
                    "path": str(path),
                }
            )
    return found


def error_of(response):
    if not response:
        return {"message": "no response"}
    error = response.get("error")
    if not error:
        return {}
    return {
        "message": error.get("message", ""),
        "type": (error.get("data") or {}).get("type", ""),
    }


class Device:
    """A synthetic Codex home with two fake providers and a Magpie profile."""

    def __init__(self, root, codex_bin, command):
        self.root = Path(root)
        self.codex_bin = codex_bin
        self.command = command
        self.home = self.root / "home"
        self.codex_home = self.home / ".codex"
        self.codex_home.mkdir(parents=True)
        self.work = self.root / "work"
        self.work.mkdir()
        self.record = self.root / "codex-argv.jsonl"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        shim = self.bin / "codex"
        shim.write_text(SHIM)
        shim.chmod(0o755)

    def write_config(self, alpha, magpie, other):
        (self.codex_home / "config.toml").write_text(
            'model = "gpt-6.1-sol"\n'
            'model_provider = "alpha"\n'
            'model_reasoning_effort = "medium"\n'
            # The startup update check is off: a fresh Codex home would offer
            # the upgrade, and the driver must never be able to accept it.
            "check_for_update_on_startup = false\n"
            "\n"
            # The working directory is trusted, so the interactive path never
            # stops on the trust dialog.
            '[projects."%s"]\n'
            'trust_level = "trusted"\n'
            "\n"
            "[model_providers.alpha]\n"
            'name = "alpha"\n'
            'base_url = "%s"\n'
            'wire_api = "responses"\n'
            'env_key = "PROBE_ALPHA_KEY"\n'
            "\n"
            "[model_providers.other]\n"
            'name = "other"\n'
            'base_url = "%s"\n'
            'wire_api = "responses"\n'
            'env_key = "PROBE_OTHER_KEY"\n' % (self.work, alpha, other)
        )
        (self.codex_home / "magpie.config.toml").write_text(
            'model_provider = "magpie"\n'
            'model = "gpt-6.1-terra"\n'
            "\n"
            "[model_providers.magpie]\n"
            'name = "magpie"\n'
            'base_url = "%s"\n'
            'wire_api = "responses"\n'
            'experimental_bearer_token = "probe-placeholder-token"\n'
            'http_headers = { "x-openai-actor-authorization" = "magpie" }\n' % magpie
        )

    def env(self, extra=None, use_shim=True):
        path = "%s:/usr/bin:/bin" % self.bin if use_shim else "%s:/usr/bin:/bin" % os.path.dirname(
            self.codex_bin
        )
        env = {
            "HOME": str(self.home),
            "CODEX_HOME": str(self.codex_home),
            "PATH": path,
            "TERM": "xterm-256color",
            "PROBE_ALPHA_KEY": "probe-placeholder-key",
            "PROBE_OTHER_KEY": "probe-placeholder-key",
            "PROBE_CODEX_RECORD": str(self.record),
            "PROBE_REAL_CODEX": self.codex_bin,
        }
        env.update(extra or {})
        return env

    def run_codex(self, arguments, extra_env=None, timeout=120):
        return subprocess.run(
            [self.codex_bin, *arguments],
            env=self.env(extra_env),
            cwd=str(self.work),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def recorded_argv(self):
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text().splitlines() if line.strip()]


def overrides_of(argv):
    values = []
    index = 0
    while index < len(argv):
        if argv[index] == "-c" and index + 1 < len(argv):
            values.append(argv[index + 1])
            index += 2
            continue
        if argv[index].startswith("--config="):
            values.append(argv[index].split("=", 1)[1])
        index += 1
    return values


def drive_picker(argv, env, cwd, prompt_text="picker turn"):
    """Drive the interactive picker in a pseudo terminal.

    The sequence is the one that works against Codex 0.169.0: wait for the
    picker to render, wait for the session list to load, accept the
    highlighted row with a Return of its own, wait for the thread view,
    write the prompt in a write of its own, and send the Return in a write
    of its own afterwards. Text and Return in one write are read as a
    paste: the Return is swallowed and the text lands in the composer
    without submitting it.

    The wait for the list is its own step, because the picker renders in
    two stages: the header and the footer are on the screen while the list
    is still loading. A Return sent in that state accepts no row, so the
    driver waits until the list has rows (see ``session_list_loaded``).

    No arrow key is sent. The picker lists the sessions in its own order
    and highlights the one it considers the most recent, so a browse would
    not land on a row this harness can name; the run therefore accepts the
    row the picker highlights, and the caller asserts on the thread that
    was actually resumed rather than on a row of its own.

    The update prompt can never be accepted: no key is sent before the
    picker has rendered, and a screen that shows the update prompt aborts
    the run instead of continuing.

    The call fails when the host does not hand out pseudo terminals; the
    caller records that as a blocker.
    """
    import fcntl
    import pty
    import select
    import signal
    import struct
    import termios

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    process = subprocess.Popen(
        argv,
        env=env,
        cwd=str(cwd),
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave)
    screen = ""
    steps = []
    failure = ""

    def write(data):
        try:
            os.write(master, data)
        except OSError as error:
            if error.errno not in (errno.EIO, errno.EPIPE):
                raise

    def read_until(predicate, deadline):
        """Read the screen until the predicate holds or the deadline passes."""
        nonlocal screen
        while time.time() < deadline:
            readable, _, _ = select.select([master], [], [], 0.2)
            if master in readable:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    return False
                if not data:
                    return False
                screen += data.decode("utf-8", "replace")
                if any(marker in plain(screen) for marker in UPDATE_PROMPT_MARKERS):
                    raise RuntimeError(
                        "the update prompt was on the screen; the run was stopped "
                        "before any key could accept it"
                    )
            if predicate(plain(screen)):
                return True
        return False

    def wait_for(markers, limit, label):
        return wait_until(
            lambda text: any(marker in text for marker in markers), limit, label
        )

    def wait_until(predicate, limit, label):
        if read_until(predicate, time.time() + limit):
            steps.append(label)
            return True
        steps.append("%s: timed out" % label)
        return False

    try:
        if not wait_for(PICKER_MARKERS, 60.0, "the picker rendered"):
            failure = "the picker did not render"
        elif not wait_until(session_list_loaded, 60.0, "the session list loaded"):
            # The list never got its rows: the picker is still loading, and
            # a Return now would accept no row at all.
            failure = "the session list did not load"
        else:
            # The row the picker highlights is accepted as it is: the order
            # of the list is the picker's own, and no row is claimed here.
            write(b"\r")
            steps.append("accepted the highlighted row")
            if not wait_for(THREAD_MARKERS, 90.0, "the thread view rendered"):
                failure = "the thread view did not render"
            else:
                write(prompt_text.encode())
                time.sleep(1.5)
                steps.append("wrote the prompt in a write of its own")
                write(b"\r")
                steps.append("submitted the prompt in a write of its own")
                # The turn needs a moment to reach the endpoint.
                read_until(lambda text: False, time.time() + 25.0)
                write(b"\x03")
    except RuntimeError as error:
        failure = str(error)
    finally:
        if process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                pass
        process.wait()
        os.close(master)
    return {
        "status": "failed" if failure else "ran",
        "error": failure,
        "steps": steps,
        "screen": plain(screen)[-2000:],
        "update_prompt_seen": any(
            marker in plain(screen) for marker in UPDATE_PROMPT_MARKERS
        ),
    }


def pty_blocker():
    """Whether the host hands out pseudo terminals, and why not when it does not."""
    detail = ""
    try:
        fd = os.open("/dev/ptmx", os.O_RDWR)
        os.close(fd)
    except OSError as error:
        detail = "opening /dev/ptmx failed: %s (errno %s)" % (
            error.strerror or error,
            error.errno,
        )
    try:
        import pty

        master, slave = pty.openpty()
        os.close(master)
        os.close(slave)
        return {"available": True, "error": ""}
    except OSError as error:
        return {
            "available": False,
            "error": "opening a pseudo terminal failed: %s; %s"
            % (error.strerror or error, detail),
            "errno": error.errno,
        }


def codex_version(codex_bin):
    try:
        result = subprocess.run(
            [codex_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return (result.stdout or result.stderr).strip().splitlines()[-1] if (result.stdout or result.stderr) else "unknown"


PROFILE_OVERRIDES = [
    "-c",
    'model_providers.magpie.name="magpie"',
    "-c",
    'model_providers.magpie.base_url="http://127.0.0.1:{port}/v1"',
    "-c",
    'model_providers.magpie.wire_api="responses"',
    "-c",
    "model_providers.magpie.env_key=DOTFILES_CODEX_RESUME_MAGPIE_TOKEN",
    "-c",
    'model_provider="magpie"',
    "-c",
    'model="gpt-6.1-terra"',
]


def profile_overrides(port):
    return [value.replace("{port}", str(port)) for value in PROFILE_OVERRIDES]


def thread_request(received, cache_key, prompt_text=""):
    """The request that belongs to the resumed thread.

    Codex sends an additional request of its own for some turns: the request
    that generates a thread title carries the configuration's own effort and
    belongs to a temporary thread of its own. The request that belongs to the
    resumed thread is the one whose cache key matches the thread's creation
    request.
    """
    candidates = [
        request
        for request in received
        if request.get("prompt_cache_key") == cache_key
    ]
    if prompt_text:
        matching = [
            request
            for request in candidates
            if prompt_text in (request.get("user_text") or "")
        ]
        if matching:
            return matching[-1]
    return candidates[-1] if candidates else None


def resumed_thread_request(received, known, prompt_text=""):
    """The request of the thread that was actually resumed.

    The thread is identified by its ``prompt_cache_key``: it is the key of
    the creation request of that thread. Every fake provider is searched,
    so the request is found no matter which provider the thread saved: the
    picker resumes whichever row it highlights, and that row may belong to
    any of them.

    The auxiliary request of Codex's own (the thread title request) belongs
    to a thread of its own and carries a cache key that is not known, so it
    is not a candidate here.
    """
    candidates = sorted(
        (
            request
            for request in received
            if request.get("prompt_cache_key") in known
        ),
        key=lambda request: request.get("seq") or 0,
    )
    if not candidates:
        return None
    if prompt_text:
        matching = [
            request
            for request in candidates
            if prompt_text in (request.get("user_text") or "")
        ]
        if matching:
            return matching[-1]
    return candidates[-1]


def run_scenarios(codex_bin, command):
    """Run every acceptance scenario and return a value free report."""
    report = {
        "codex_version": codex_version(codex_bin),
        "codex_binary": codex_bin,
        "command": str(command),
        "pty": pty_blocker(),
        "scenarios": [],
    }
    alpha = FakeProvider("alpha")
    magpie = FakeProvider("magpie")
    other = FakeProvider("other")
    providers = {"alpha": alpha, "magpie": magpie, "other": other}
    try:
        for provider in (alpha, magpie, other):
            assert provider.port != LIVE_GATEWAY_PORT
        report["ports"] = {
            "alpha": alpha.port,
            "magpie": magpie.port,
            "other": other.port,
            "live_gateway_excluded": LIVE_GATEWAY_PORT,
        }
        with tempfile.TemporaryDirectory(prefix="dotfiles-codex-runtime-") as root:
            device = Device(root, codex_bin, command)
            device.write_config(alpha.base_url, magpie.base_url, other.base_url)
            base_before = (device.codex_home / "config.toml").read_bytes()

            created = device.run_codex(
                [
                    "exec",
                    "--skip-git-repo-check",
                    "-c",
                    "model_provider=alpha",
                    "-c",
                    "model=gpt-6.1-sol",
                    "-c",
                    "model_reasoning_effort=medium",
                    "alpha thread",
                ]
            )
            alpha_run = {
                "command": "codex exec --skip-git-repo-check -c model_provider=alpha "
                "-c model=gpt-6.1-sol -c model_reasoning_effort=medium 'alpha thread'",
                "exit": created.returncode,
            }
            alpha_creation = alpha.received()[-1:]
            created = device.run_codex(
                [
                    "exec",
                    "--skip-git-repo-check",
                    "-p",
                    "magpie",
                    "-c",
                    "model_reasoning_effort=high",
                    "magpie thread",
                ]
            )
            magpie_run = {
                "command": "codex exec --skip-git-repo-check -p magpie "
                "-c model_reasoning_effort=high 'magpie thread'",
                "exit": created.returncode,
            }
            magpie_creation = magpie.received()[-1:]
            threads = thread_ids(device.codex_home)
            alpha_thread = None
            magpie_thread = None
            for thread in threads:
                if thread["provider"] == "alpha" and alpha_thread is None:
                    alpha_thread = thread["id"]
                if thread["provider"] == "magpie" and magpie_thread is None:
                    magpie_thread = thread["id"]
            report["threads"] = {
                "alpha": alpha_thread,
                "magpie": magpie_thread,
                "providers": sorted({thread["provider"] for thread in threads}),
            }
            plain = device.run_codex(
                ["exec", "--skip-git-repo-check", "-p", "magpie", "plain magpie session"]
            )
            plain_run = {
                "command": "codex exec --skip-git-repo-check -p magpie 'plain magpie session'",
                "exit": plain.returncode,
            }
            plain_creation = magpie.received()[-1:]

            # Every thread, with the model, the effort, the provider, and
            # the cache key its creation request carried. A resumed turn
            # belongs to the thread whose creation request shares its cache
            # key.
            known = {}
            for label, creation in (
                ("alpha", alpha_creation),
                ("magpie", magpie_creation),
                ("plain", plain_creation),
            ):
                if not creation:
                    continue
                request = creation[-1]
                known[request.get("prompt_cache_key")] = {
                    "label": label,
                    "provider": request.get("label"),
                    "model": request.get("model"),
                    "effort": request.get("effort"),
                    "prompt_cache_key": request.get("prompt_cache_key"),
                }
            report["known_threads"] = known
            report["scenarios"].append(
                {
                    "name": "new-session-defaults",
                    "runs": [alpha_run, magpie_run, plain_run],
                    "received": {
                        "alpha": alpha.received(),
                        "magpie": magpie.received(),
                    },
                }
            )

            # Red: the Magpie profile against a thread that saved another provider.
            client = AppServerClient(
                [str(device.bin / "codex"), "resume", *profile_overrides(magpie.port)],
                device.env({"DOTFILES_CODEX_RESUME_MAGPIE_TOKEN": "probe-placeholder-token"}),
                device.work,
            )
            response = client.resume(alpha_thread, model="gpt-6.1-terra", model_provider="magpie")
            report["scenarios"].append(
                {
                    "name": "red-non-magpie-thread-through-magpie-profile",
                    "command": "codex resume -p magpie <alpha thread> (picker entry)",
                    "error": error_of(response),
                }
            )
            client.close()

            # Red: a Magpie thread without the provider definition.
            client = AppServerClient(
                [str(device.bin / "codex"), "resume"], device.env(), device.work
            )
            response = client.resume(magpie_thread)
            report["scenarios"].append(
                {
                    "name": "red-magpie-thread-without-provider-definition",
                    "command": "codex resume <magpie thread> (picker entry)",
                    "error": error_of(response),
                }
            )
            client.close()

            # Green: the managed command resumes the Magpie thread.
            before = len(magpie.received())
            client = AppServerClient(
                [str(command)], device.env(), device.work
            )
            response = client.resume(magpie_thread)
            resumed = response.get("result", {}) if response else {}
            client.turn(magpie_thread, "resumed magpie turn")
            time.sleep(3)
            client.close()
            received = magpie.received()[before:]
            magpie_cache_key = magpie_creation[-1].get("prompt_cache_key") if magpie_creation else None
            thread_call = thread_request(received, magpie_cache_key, "resumed magpie turn")
            report["scenarios"].append(
                {
                    "name": "green-magpie-thread-through-the-command",
                    "command": "dotfiles-codex-resume <magpie thread>",
                    "resume": {
                        "model": resumed.get("model"),
                        "modelProvider": resumed.get("modelProvider"),
                        "reasoningEffort": (resumed.get("thread") or {}).get("reasoningEffort"),
                    },
                    "received": received,
                    "thread_request": thread_call,
                    "auxiliary": [
                        request
                        for request in received
                        if request is not thread_call
                    ],
                    "command_argv": device.recorded_argv()[-1:],
                }
            )

            # Green: the managed command resumes the thread of another provider.
            before = len(alpha.received())
            client = AppServerClient([str(command)], device.env(), device.work)
            response = client.resume(alpha_thread)
            resumed = response.get("result", {}) if response else {}
            client.turn(alpha_thread, "resumed alpha turn")
            time.sleep(3)
            client.close()
            received = alpha.received()[before:]
            alpha_cache_key = alpha_creation[-1].get("prompt_cache_key") if alpha_creation else None
            thread_call = thread_request(received, alpha_cache_key, "resumed alpha turn")
            report["scenarios"].append(
                {
                    "name": "green-other-provider-thread-through-the-command",
                    "command": "dotfiles-codex-resume <alpha thread>",
                    "resume": {
                        "model": resumed.get("model"),
                        "modelProvider": resumed.get("modelProvider"),
                        "reasoningEffort": (resumed.get("thread") or {}).get("reasoningEffort"),
                    },
                    "received": received,
                    "thread_request": thread_call,
                    "auxiliary": [
                        request
                        for request in received
                        if request is not thread_call
                    ],
                }
            )

            base_after = (device.codex_home / "config.toml").read_bytes()
            report["base_config_unchanged"] = base_before == base_after
            report["other_provider_preserved"] = "[model_providers.other]" in base_after.decode()

            # The picker's own path: the interactive TUI in a pseudo terminal.
            picker = {"name": "picker-in-a-pty"}

            # A target thread of its own, created right before the run, so
            # that the picker lists a thread of its own as well. Which row
            # the picker highlights is the picker's own business: the
            # assertion looks the request of the thread that was actually
            # resumed up, by its cache key, in every provider.
            before_target = len(magpie.received())
            target = device.run_codex(
                [
                    "exec",
                    "--skip-git-repo-check",
                    "-p",
                    "magpie",
                    "-c",
                    "model_reasoning_effort=high",
                    "picker target thread",
                ]
            )
            # The creation request of the target thread is the one that
            # carries its own first prompt.
            target_creation = [
                request
                for request in magpie.received()[before_target:]
                if "picker target thread" in (request.get("user_text") or "")
            ]
            if target_creation:
                request = target_creation[-1]
                known[request.get("prompt_cache_key")] = {
                    "label": "picker-target",
                    "provider": request.get("label"),
                    "model": request.get("model"),
                    "effort": request.get("effort"),
                    "prompt_cache_key": request.get("prompt_cache_key"),
                }
            report["known_threads"] = known
            picker["target"] = {
                "command": "codex exec --skip-git-repo-check -p magpie "
                "-c model_reasoning_effort=high 'picker target thread'",
                "exit": target.returncode,
                "created": bool(target_creation),
            }

            if not report["pty"]["available"]:
                picker["status"] = "blocked"
                picker["error"] = report["pty"]["error"]
                report["scenarios"].append(picker)
            else:
                # Every provider is watched: the row the picker highlights
                # may belong to any of them, and the turn of a thread of
                # another provider reaches that provider's endpoint.
                before = {
                    label: len(provider.received())
                    for label, provider in providers.items()
                }
                try:
                    result = drive_picker(
                        [str(command)],
                        device.env(use_shim=False),
                        device.work,
                        prompt_text="picker turn",
                    )
                except OSError as error:
                    picker["status"] = "blocked"
                    picker["error"] = str(error)
                else:
                    received = []
                    for label, provider in providers.items():
                        start = before[label]
                        received.extend(provider.received()[start:])
                    received.sort(key=lambda request: request.get("seq") or 0)
                    thread_call = resumed_thread_request(
                        received, known, "picker turn"
                    )
                    picker["status"] = result["status"]
                    picker["error"] = result["error"]
                    picker["steps"] = result["steps"]
                    picker["update_prompt_seen"] = result["update_prompt_seen"]
                    picker["received"] = received
                    picker["received_by_provider"] = {
                        label: len(provider.received()) - before[label]
                        for label, provider in providers.items()
                    }
                    picker["thread_request"] = thread_call
                    picker["auxiliary"] = [
                        request
                        for request in received
                        if request is not thread_call
                    ]
                    picker["screen"] = result["screen"]
                report["scenarios"].append(picker)
    finally:
        for provider in (alpha, magpie, other):
            provider.close()
    return report


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    codex_bin = os.environ.get("DOTFILES_TEST_CODEX") or shutil.which("codex")
    if not codex_bin:
        print("codex is not installed")
        return 2
    command = argv[0] if argv else str(
        Path(__file__).resolve().parents[1] / "dot_local/bin/executable_dotfiles-codex-resume"
    )
    report = run_scenarios(codex_bin, command)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
