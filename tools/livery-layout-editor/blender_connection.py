"""Managed Blender MCP configuration and read-only diagnostics, without bpy."""
from pathlib import Path
import hashlib
import json
import os
import re
import socket

from runtime import APP, SETTINGS

DATA = APP / 'data/blender'
LOCK = APP / 'config/blender-mcp.lock.json'
ADDON = DATA / 'scripts/addons/blender_mcp.py'
PYTHON = APP / '.tools/blender-mcp-env' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
REQUIRED_TOOLS = {'get_scene_info', 'get_object_info', 'execute_blender_code'}


def settings():
    value = {'enabled': True, 'host': '127.0.0.1', 'port': 18876, 'server_name': 'wt_camo_blender'}
    value.update(SETTINGS.get('blender_mcp', {}))
    value['port'] = int(os.environ.get('WT_CAMO_BLENDER_MCP_PORT', value['port']))
    if value['host'] != '127.0.0.1' or not 1024 <= value['port'] <= 65535:
        raise ValueError('Managed Blender MCP requires loopback and a port from 1024 to 65535.')
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,63}', value['server_name']):
        raise ValueError('Invalid Blender MCP server_name.')
    return value


def lock():
    return json.loads(LOCK.read_text(encoding='utf-8'))


def installed():
    manifest = DATA / 'install.json'
    if not manifest.is_file() or not ADDON.is_file() or not PYTHON.is_file():
        return False
    try:
        record = json.loads(manifest.read_text(encoding='utf-8'))
        return (record.get('lock') == lock() and
                record.get('requirements_sha256') == hashlib.sha256((APP / 'requirements-mcp.txt').read_bytes()).hexdigest() and
                hashlib.sha256(ADDON.read_bytes()).hexdigest() == lock()['addon_sha256'])
    except (ValueError, OSError):
        return False


def spec():
    config = settings()
    return {'command': str(PYTHON), 'args': ['-c', 'from blender_mcp.server import main; main()'],
            'env': {'BLENDER_HOST': config['host'], 'BLENDER_PORT': str(config['port']),
                    'DISABLE_TELEMETRY': 'true', 'PYTHONUTF8': '1'},
            'startup_timeout_sec': 30.0, 'tool_timeout_sec': 180.0,
            'enabled_tools': sorted(REQUIRED_TOOLS), 'enabled': bool(config['enabled'])}


def app_server_args():
    # Explicit per-process overrides work in external workspaces without relying on
    # project trust. Global registration is also offered for standalone Codex CLI.
    if not installed():
        return []
    def toml(v):
        if isinstance(v, dict):
            return '{' + ', '.join(k + '=' + toml(x) for k, x in v.items()) + '}'
        return json.dumps(v, ensure_ascii=False)
    return ['-c', 'mcp_servers.' + settings()['server_name'] + '=' + toml(spec())]


def request(command, timeout=2):
    config = settings()
    with socket.create_connection((config['host'], config['port']), timeout=timeout) as connection:
        connection.sendall(json.dumps(command).encode('utf-8'))
        received = bytearray()
        while len(received) < 32 * 1024 * 1024:
            chunk = connection.recv(65536)
            if not chunk:
                break
            received.extend(chunk)
            try:
                return json.loads(received)
            except (ValueError, UnicodeDecodeError):
                continue
    raise RuntimeError('Blender MCP did not return a complete response.')


def status():
    config = settings()
    result = {'installed': installed(), 'enabled': bool(config['enabled']),
              'server_name': config['server_name'], 'port': config['port'], 'connected': False}
    if not result['installed']:
        result['hint'] = 'Run start.cmd -WithBlenderMcp (or scripts/setup-blender-mcp.ps1).'
        return result
    try:
        response = request({'type': 'wt_camo_health'})
        info = response.get('result', {})
        if info.get('application') != 'wt-camo-blender' or Path(info.get('repo', '')).resolve() != APP.resolve():
            raise RuntimeError('Port belongs to a different process/repository; it will not be reused.')
        if info.get('addon_sha256') != lock()['addon_sha256']:
            raise RuntimeError('Running addon differs from the pinned installation. Restart managed Blender.')
        result.update(connected=True, session=info)
    except (OSError, ValueError, RuntimeError) as exc:
        result.update(error=str(exc), hint='Run scripts/start-blender-mcp.ps1; inspect data/blender/host.err.log.')
    return result


def codex_status(bridge):
    """Report only our tool names, never other MCP credentials or resource contents."""
    name = settings()['server_name']
    cursor = None
    while True:
        page = bridge.rpc('mcpServerStatus/list', {'limit': 100, 'serverName': name, **({'cursor': cursor} if cursor else {})})
        for server in page.get('data', []):
            if server.get('name') == name:
                tools = server.get('tools', {})
                names = sorted(tools if isinstance(tools, dict) else [t['name'] for t in tools])
                return {'server_name': name, 'tools': names, 'ready': REQUIRED_TOOLS.issubset(names), 'error': server.get('toolsError')}
        cursor = page.get('nextCursor')
        if not cursor:
            return {'server_name': name, 'tools': [], 'ready': False}
