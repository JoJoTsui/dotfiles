"""Native adapters for the existing public discovery and stdio MCP probes."""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

from fixtures.processes import stop_client


def verify_clients(case, source, environment):
    # The same public protocols as ticket05/06 exercise native executables.
    from test_agent_payload import AgentPayloadTests
    from test_codegraph import CodeGraphTests
    names = ('codegraph', 'codex', 'claude', 'kimi', 'opencode')
    overrides = {"DOTFILES_TEST_" + name.upper(): str(case.home / f'.bun/bin/{name}.cmd') for name in names}
    overrides.update(DOTFILES_TEST_NODE=str(case.home / '.pixi/bin/node.exe'),
                     DOTFILES_TEST_PI_MODULE=str(case.home / '.bun/managed/pi/node_modules/@earendil-works/pi-coding-agent/dist/index.js'))
    saved = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    original_deploy = case.deploy
    case.deploy = lambda *args: original_deploy('-ApplyOnly', *args)
    case.diagnostic_env = lambda: environment.copy()
    try:
        for method in ('test_pinned_codex_reads_shared_instructions_and_automatic_skills',
                       'test_pinned_pi_resource_loader_reads_the_full_library_and_global_instructions',
                       'test_pinned_opencode_discovers_skills_without_a_model_request',
                       'test_pinned_claude_and_kimi_advertise_manual_and_automatic_skill_commands'):
            getattr(AgentPayloadTests, method)(case)
        pi_script = """
const {createBashTool,SettingsManager}=await import(process.argv[1]);
const settings=SettingsManager.create(process.cwd(),process.env.PI_CODING_AGENT_DIR);
const result=await createBashTool(process.cwd(),{shellPath:settings.getShellPath()}).execute('native-fixture',
 {command:'printf "pi-native-git-bash-token\\n"; printf "%s\\n" "$BASH"; command -v nu',timeout:15});
console.log(JSON.stringify(result));
"""
        pi = subprocess.run([overrides['DOTFILES_TEST_NODE'], '--input-type=module', '-e', pi_script,
                             Path(overrides['DOTFILES_TEST_PI_MODULE']).as_uri()],
                            cwd=case.home, env=environment, capture_output=True, text=True, timeout=45)
        case.assertEqual(pi.returncode, 0, pi.stderr)
        case.assertIn('pi-native-git-bash-token', pi.stdout)
        case.assertIn('dotfiles/git-bash', pi.stdout.replace('\\\\', '/').replace('\\', '/'))
        CodeGraphTests.test_managed_mcp_command_explores_only_an_explicitly_indexed_temporary_fixture(case)
        project = case.root / 'native-client-unindexed'
        project.mkdir()
        command = json.loads((case.home / '.kimi-code/mcp.json').read_text())['mcpServers']['codegraph']
        codex = subprocess.run([overrides['DOTFILES_TEST_CODEX'], 'mcp', 'get', 'codegraph', '--json'],
                               cwd=project, env=environment, capture_output=True, text=True, timeout=45)
        case.assertEqual(codex.returncode, 0, codex.stderr)
        server = json.loads(codex.stdout)
        case.assertTrue(server['enabled'])
        case.assertEqual(server['transport']['command'], command['command'])
        case.assertEqual(server['transport']['args'], command['args'])
        claude = subprocess.run([overrides['DOTFILES_TEST_CLAUDE'], 'mcp', 'get', 'codegraph'],
                                cwd=project, env=environment, capture_output=True, text=True, timeout=45)
        case.assertEqual(claude.returncode, 0, claude.stderr)
        case.assertIn('Connected', claude.stdout)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for client in ('kimi', 'opencode'):
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            env = dict(environment, OPENCODE_SERVER_PASSWORD='synthetic-native-mcp')
            arguments = (['web', '--host', '127.0.0.1', '--port', str(port), '--no-open', '--dangerous-bypass-auth']
                         if client == 'kimi' else ['serve', '--hostname', '127.0.0.1', '--port', str(port)])
            def api(path, data=None):
                request = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
                    data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
                if client == 'opencode':
                    request.add_header('Authorization', 'Basic ' + base64.b64encode(b'opencode:synthetic-native-mcp').decode())
                return json.loads(opener.open(request, timeout=5).read())
            with (case.root / f'native-{client}.private.log').open('w') as log:
                process = subprocess.Popen([overrides['DOTFILES_TEST_' + client.upper()], *arguments],
                                           cwd=project, env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 60
                    record = None
                    while time.monotonic() < deadline:
                        try:
                            records = api('/api/v2/mcp/servers' if client == 'kimi' else '/api/mcp')['data']
                            record = next((item for item in records if item['name'] == 'codegraph'), None)
                            if record and (client == 'kimi' or record['status']['status'] == 'connected'):
                                break
                        except OSError:
                            pass
                        time.sleep(0.1)
                    case.assertIsNotNone(record)
                    if client == 'kimi':
                        case.assertEqual(record['config']['command'], command['command'])
                        case.assertEqual(record['config']['args'], command['args'])
                        checked = api('/api/v2/mcp/servers:test', {'name': 'codegraph'})['data']
                        case.assertTrue(checked['success'], checked)
                        case.assertIn('codegraph_explore', checked['output'])
                    else:
                        case.assertEqual(record['status']['status'], 'connected')
                finally:
                    stop_client(process)
        case.assertFalse((project / '.codegraph').exists())
        case.assertFalse((source / '.codegraph').exists())
    finally:
        case.deploy = original_deploy
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
