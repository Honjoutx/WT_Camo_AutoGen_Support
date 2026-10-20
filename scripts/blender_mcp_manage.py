"""Install, launch and diagnose the repository-owned Blender MCP session."""
from pathlib import Path
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import venv

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools/livery-layout-editor'))
import blender_connection as connection
from runtime import blender_executable, codex_executable


@contextmanager
def management_lock():
    """OS lock is released on crash; simultaneous launches cannot lose receipts."""
    connection.DATA.mkdir(parents=True, exist_ok=True)
    with (connection.DATA / 'manage.lock').open('a+b') as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Another Blender MCP setup/start/stop is in progress.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def register():
    name = connection.settings()['server_name']
    desired = connection.spec()
    binary = codex_executable()
    result = subprocess.run([binary, 'mcp', 'get', name, '--json'], capture_output=True, text=True, encoding='utf-8', timeout=30)
    current = json.loads(result.stdout) if result.returncode == 0 else None
    receipt_path = connection.DATA / 'registration.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
    if current:
        transport = current.get('transport', {})
        identity = {key: transport.get(key) for key in ('command', 'args', 'env')}
        wanted = {key: desired[key] for key in identity}
        if identity == wanted and current.get('enabled', True):
            write_json(receipt_path, {'name': name, 'spec': wanted})
            return
        if receipt.get('name') != name or identity != receipt.get('spec'):
            raise RuntimeError('MCP name belongs to another configuration. Set a different blender_mcp.server_name in runtime.local.json.')
    config = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'config.toml'
    if config.exists():
        content = config.read_bytes()
        backup = connection.DATA / 'config-backups' / (hashlib.sha256(content).hexdigest() + '.toml')
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(content)
    command = [binary, 'mcp', 'add', name]
    for key, value in desired['env'].items():
        command.extend(['--env', key + '=' + value])
    command.extend(['--', desired['command'], *desired['args']])
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        raise RuntimeError('Codex MCP registration failed; check CLI configuration permissions and version.')
    write_json(receipt_path, {'name': name, 'spec': {key: desired[key] for key in ('command', 'args', 'env')}})


def setup(addon_file=None, no_register=False):
    connection.DATA.mkdir(parents=True, exist_ok=True)
    pinned = connection.lock()
    if not connection.installed():
        if not connection.PYTHON.is_file():
            venv.EnvBuilder(with_pip=True).create(connection.PYTHON.parents[1])
        subprocess.run([str(connection.PYTHON), '-m', 'pip', 'install', '-r', str(REPO / 'requirements-mcp.txt')], check=True)
        if addon_file:
            content = Path(addon_file).read_bytes()
        else:
            with urllib.request.urlopen(pinned['addon_url'], timeout=60) as response:
                content = response.read(2 * 1024 * 1024)
        if hashlib.sha256(content).hexdigest() != pinned['addon_sha256']:
            raise RuntimeError('Addon failed SHA-256 verification. No addon was installed.')
        connection.ADDON.parent.mkdir(parents=True, exist_ok=True)
        temporary = connection.ADDON.with_suffix('.tmp')
        temporary.write_bytes(content)
        temporary.replace(connection.ADDON)
        write_json(connection.DATA / 'install.json', {'lock': pinned,
            'requirements_sha256': hashlib.sha256((REPO / 'requirements-mcp.txt').read_bytes()).hexdigest()})
    if not no_register:
        register()
    license_file = connection.DATA / 'scripts/addons/blender_mcp.LICENSE.txt'
    license_file.parent.mkdir(parents=True, exist_ok=True)
    license_file.write_bytes((REPO / 'config/blender-mcp.LICENSE.txt').read_bytes())
    print('Blender MCP installed and verified. ' + ('Registration skipped; workbench uses local overrides.' if no_register else 'Codex CLI server: ' + connection.settings()['server_name']))


def start(blender=None, model=None):
    if not connection.settings()['enabled']:
        raise RuntimeError('Blender MCP is disabled in runtime.local.json.')
    if not connection.installed():
        setup()
    config = connection.settings()
    existing = connection.status()
    if existing['connected']:
        if model and existing['session'].get('model') != str(Path(model).resolve()):
            raise RuntimeError('Managed Blender has a different scene. Stop it explicitly before opening another model.')
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return
    with socket.socket() as probe:
        probe.settimeout(.5)
        if probe.connect_ex((config['host'], config['port'])) == 0:
            raise RuntimeError('MCP port is occupied. Choose a different blender_mcp.port. Nothing was stopped.')
    binary = str(Path(blender).resolve(strict=True)) if blender else blender_executable()
    if model:
        model = str(Path(model).resolve(strict=True))
        if Path(model).suffix.lower() not in ('.obj', '.fbx', '.gltf', '.glb', '.blend'):
            raise ValueError('Supported models: OBJ, FBX, GLTF/GLB, BLEND.')
    token = uuid.uuid4().hex
    env = dict(os.environ, PYTHONUTF8='1', DISABLE_TELEMETRY='true')
    for key, part in [('BLENDER_USER_CONFIG', 'config'), ('BLENDER_USER_SCRIPTS', 'scripts'),
                      ('BLENDER_USER_EXTENSIONS', 'extensions'), ('BLENDER_USER_DATAFILES', 'datafiles')]:
        path = connection.DATA / part
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    command = [binary, '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
               '--python', str(REPO / 'scripts/blender_mcp_host.py'), '--', '--repo', str(REPO),
               '--port', str(config['port']), '--token', token]
    if model:
        command.extend(['--model', model])
    with (connection.DATA / 'host.out.log').open('w', encoding='utf-8') as stdout, (connection.DATA / 'host.err.log').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    write_json(connection.DATA / 'session.json', {'pid': process.pid, 'token': token, 'port': config['port'], 'repo': str(REPO)})
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(.3)
        result = connection.status()
        if result['connected'] and result['session']['token'] == token:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
    if process.poll() is None:
        process.terminate()
    raise RuntimeError('Managed Blender did not become ready. Inspect data/blender/host.err.log and host.out.log.')


def stop():
    receipt = json.loads((connection.DATA / 'session.json').read_text(encoding='utf-8'))
    # Stop still works after a dependency cleanup/update invalidates the install.
    info = connection.request({'type': 'wt_camo_health'}).get('result', {})
    if (info.get('application') != 'wt-camo-blender' or
        Path(info.get('repo', '')).resolve() != REPO.resolve() or
        any(receipt.get(key) != info.get(key) for key in ('pid', 'token', 'repo'))):
        raise RuntimeError('Session identity differs from launch receipt. Nothing was stopped.')
    (connection.DATA / ('stop-' + info['token'])).touch()
    for _ in range(40):
        time.sleep(.25)
        try:
            still_running = connection.request({'type': 'wt_camo_health'})
        except (OSError, ValueError, RuntimeError):
            print('Managed Blender stopped. Other Blender processes were untouched.')
            return
    raise RuntimeError('Managed Blender is still finishing a command; check its log.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'start', 'stop', 'status'])
    parser.add_argument('--addon-file', help='Offline pinned addon.py; still checked against SHA-256.')
    parser.add_argument('--no-register', action='store_true')
    parser.add_argument('--blender')
    parser.add_argument('--model')
    args = parser.parse_args()
    try:
        if args.action == 'status':
            result = connection.status()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return int(not result['connected'])
        with management_lock():
            if args.action == 'setup': setup(args.addon_file, args.no_register)
            elif args.action == 'start': start(args.blender, args.model)
            elif args.action == 'stop': stop()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
