"""Native adapters for the existing public discovery and stdio MCP probes."""
import base64
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

from fixtures.processes import stop_client
from fixtures.skills import skill_fixture_inventory


def verify_clients(case, source, environment):
    """Exercise the public protocols using the native installation under test."""
    from test_agent_payload import (
        verify_codex_discovery, verify_command_catalogs, verify_opencode_discovery, verify_pi_discovery,
    )
    from test_codegraph import verify_codegraph_indexing

    names = ('codegraph', 'codex', 'claude', 'kimi', 'opencode')
    overrides = {"DOTFILES_TEST_" + name.upper(): str(case.home / f'.bun/bin/{name}.cmd') for name in names}
    overrides.update(DOTFILES_TEST_NODE=str(case.home / '.pixi/bin/node.exe'),
                     DOTFILES_TEST_PI_MODULE=str(case.home / '.bun/managed/pi/node_modules/@earendil-works/pi-coding-agent/dist/index.js'),
                     DOTFILES_TEST_HOME=str(case.home),
                     DOTFILES_TEST_TEMP_ROOT=str(case.root),
                     DOTFILES_TEST_SOURCE=str(source),
                     DOTFILES_TEST_RUNNER_HOME=str(Path(case.env.get('HOME', str(case.root))).resolve()),
                     CODEGRAPH_NO_DAEMON='1')
    environment = dict(environment, **overrides)
    expected, disabled = skill_fixture_inventory(
        source, Path(case.env['DOTFILES_SKILLS_DIR']), case.env.get('DOTFILES_SKILLS', ''),
    )
    verify_codex_discovery(case, overrides['DOTFILES_TEST_CODEX'], environment)
    verify_pi_discovery(case, overrides['DOTFILES_TEST_NODE'], overrides['DOTFILES_TEST_PI_MODULE'],
                        environment, expected)
    verify_opencode_discovery(case, overrides['DOTFILES_TEST_OPENCODE'], environment, expected)
    verify_command_catalogs(case, {name: overrides['DOTFILES_TEST_' + name.upper()] for name in ('claude', 'kimi')},
                            environment, expected, disabled)
    pi_script = """
const {createBashTool,SettingsManager}=await import(process.argv[1]);
const settings=SettingsManager.create(process.cwd(),process.env.PI_CODING_AGENT_DIR);
const result=await createBashTool(process.cwd(),{shellPath:settings.getShellPath()}).execute('native-fixture',
 {command:'printf "pi-native-git-bash-token\\n"; printf "%s\\n" "$BASH"; command -v nu',timeout:15});
console.log(JSON.stringify({shellPath:settings.getShellPath(),result}));
"""
    pi = subprocess.run([overrides['DOTFILES_TEST_NODE'], '--input-type=module', '-e', pi_script,
                         Path(overrides['DOTFILES_TEST_PI_MODULE']).as_uri()],
                        cwd=case.home, env=environment, capture_output=True, text=True, timeout=45)
    case.assertEqual(pi.returncode, 0, pi.stderr)
    pi_result = json.loads(pi.stdout)
    expected_bash = case.home / '.local/share/dotfiles/git-bash/bin/bash.exe'
    case.assertEqual(Path(pi_result['shellPath']), expected_bash)
    output = pi_result['result'].get('structuredContent', {}).get('output', '')
    case.assertIn('pi-native-git-bash-token', output)
    # Git Bash presents its internal POSIX path in $BASH, while Nu still
    # resolves through the target device's managed Windows PATH.
    case.assertIn('/usr/bin/bash', output)
    expected_nu = str(case.home / '.pixi/bin/nu').replace('\\', '/')
    drive, marker, suffix = expected_nu.partition(':/')
    if marker:
        expected_nu = f'/{drive.lower()}/{suffix}'
    case.assertIn(expected_nu, output.replace('\\', '/'))
    verify_codegraph_indexing(case, overrides['DOTFILES_TEST_CODEGRAPH'], environment, source)
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
        endpoint = '/api/v1/mcp/servers' if client == 'kimi' else '/api/mcp'
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
                last_error = 'no transport error'
                while time.monotonic() < deadline:
                    try:
                        records = api(endpoint)['data']
                        record = next((item for item in records if item['name'] == 'codegraph'), None)
                        if record and (client == 'kimi' or record['status']['status'] == 'connected'):
                            break
                    except OSError as error:
                        last_error = f'{type(error).__name__}: {error}'
                    time.sleep(0.1)
                case.assertIsNotNone(record, f'{client} GET {endpoint} did not list CodeGraph; last transport failure: {last_error}')
                if client == 'kimi':
                    case.assertEqual(record['config']['command'], command['command'])
                    case.assertEqual(record['config']['args'], command['args'])
                    test_endpoint = '/api/v1/mcp/servers:test'
                    try:
                        checked = api(test_endpoint, {'name': 'codegraph'})['data']
                    except OSError as error:
                        case.fail(f'{client} POST {test_endpoint}: {type(error).__name__}: {error}')
                    case.assertTrue(checked['success'], checked)
                    case.assertIn('codegraph_explore', checked['output'])
                else:
                    case.assertEqual(record['status']['status'], 'connected',
                                     f'{client} GET {endpoint}; last transport failure: {last_error}')
            finally:
                stop_client(process)
    case.assertFalse((project / '.codegraph').exists())
    case.assertFalse((source / '.codegraph').exists())
