"""Run upstream addon command handlers on Blender's main thread in --background.

The upstream threaded UI server relies on bpy.app.timers; background Blender does
not pump those timers. This host uses selectors on the main thread instead. No
user preferences, existing Blender process or source model are modified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import selectors
import socket
import sys

MAX_MESSAGE = 32 * 1024 * 1024


def parse_messages(buffer):
    """Decode complete JSON objects, retaining fragmented UTF-8 / JSON bytes."""
    if len(buffer) > MAX_MESSAGE:
        raise ValueError('Request is too large')
    messages = []
    while buffer:
        try:
            text = buffer.decode('utf-8')
        except UnicodeDecodeError as exc:
            if exc.reason == 'unexpected end of data':
                break
            raise ValueError('Invalid UTF-8') from exc
        stripped = text.lstrip()
        if not stripped:
            return messages, b''
        if not stripped.startswith('{'):
            raise ValueError('Expected a JSON object')
        try:
            message, end = json.JSONDecoder().raw_decode(stripped)
        except json.JSONDecodeError:
            break
        consumed = len(text) - len(stripped) + end
        messages.append(message)
        buffer = text[consumed:].encode('utf-8')
    if len(buffer) > MAX_MESSAGE:
        raise ValueError('Request is too large')
    return messages, buffer


def serve(execute, health, stop_file, port):
    selector = selectors.DefaultSelector()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Exclusive bind prevents silently sharing an occupied port on Windows.
    if os.name == 'nt':
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', port))
    listener.listen(16)
    listener.setblocking(False)
    selector.register(listener, selectors.EVENT_READ)
    try:
        while not stop_file.exists():
            for key, mask in selector.select(timeout=.25):
                client = key.fileobj
                if client is listener:
                    connection, _ = listener.accept()
                    connection.setblocking(False)
                    selector.register(connection, selectors.EVENT_READ, {'input': b'', 'output': b''})
                    continue
                state = key.data
                try:
                    if mask & selectors.EVENT_READ:
                        chunk = client.recv(65536)
                        if not chunk:
                            selector.unregister(client); client.close(); continue
                        messages, state['input'] = parse_messages(state['input'] + chunk)
                        for command in messages:
                            if command.get('type') == 'wt_camo_health':
                                response = {'status': 'success', 'result': health}
                            elif command.get('type') == 'get_viewport_screenshot':
                                response = {'status': 'error', 'message': 'Headless session: use execute_code to render a camera image to a file.'}
                            else:
                                response = execute(command)
                            state['output'] += json.dumps(response, ensure_ascii=False).encode('utf-8')
                        if len(state['output']) > MAX_MESSAGE:
                            raise ValueError('Response is too large')
                    if mask & selectors.EVENT_WRITE and state['output']:
                        state['output'] = state['output'][client.send(state['output']):]
                    selector.modify(client, selectors.EVENT_READ | (selectors.EVENT_WRITE if state['output'] else 0), state)
                except (OSError, ValueError):
                    selector.unregister(client); client.close()
    finally:
        for key in list(selector.get_map().values()):
            key.fileobj.close()
        selector.close()


def main():
    import bpy
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--token', required=True)
    parser.add_argument('--model')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    repo = Path(args.repo).resolve()
    data = repo / 'data/blender'
    addon = data / 'scripts/addons/blender_mcp.py'
    expected = json.loads((repo / 'config/blender-mcp.lock.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(addon.read_bytes()).hexdigest()
    if digest != expected['addon_sha256']:
        raise RuntimeError('Addon checksum mismatch; rerun setup-blender-mcp.ps1.')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if args.model:
        path = Path(args.model).resolve(strict=True)
        if path.suffix.lower() == '.blend':
            bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
        elif path.suffix.lower() == '.obj':
            bpy.ops.wm.obj_import(filepath=str(path))
        elif path.suffix.lower() == '.fbx':
            bpy.ops.import_scene.fbx(filepath=str(path))
        elif path.suffix.lower() in ('.glb', '.gltf'):
            bpy.ops.import_scene.gltf(filepath=str(path))
        else:
            raise ValueError('Supported models: OBJ, FBX, GLB/GLTF, BLEND.')
    sys.path.insert(0, str(addon.parent))
    bpy.ops.preferences.addon_enable(module='blender_mcp')
    import blender_mcp
    scene = bpy.context.scene
    scene.blendermcp_auto_start_server = False
    scene.blendermcp_port = args.port
    scene.blendermcp_server_running = True
    for feature in ('polyhaven', 'hyper3d', 'sketchfab', 'hunyuan3d'):
        setattr(scene, 'blendermcp_use_' + feature, False)
    executor = blender_mcp.BlenderMCPServer(host='127.0.0.1', port=args.port)
    info = {'application': 'wt-camo-blender', 'repo': str(repo), 'pid': os.getpid(),
            'token': args.token, 'blender': bpy.app.version_string, 'background': bpy.app.background,
            'addon_sha256': digest, 'addon_enabled': 'blender_mcp' in bpy.context.preferences.addons,
            'model': args.model, 'object_count': len(scene.objects)}
    stop_file = data / ('stop-' + args.token)
    print(json.dumps(info), flush=True)
    serve(executor.execute_command, info, stop_file, args.port)
    stop_file.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
