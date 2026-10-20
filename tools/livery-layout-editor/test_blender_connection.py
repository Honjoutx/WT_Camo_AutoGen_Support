"""Managed MCP regressions, independent of Blender, Codex credentials and user data."""
from pathlib import Path
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import tomllib
import unittest
from unittest.mock import patch
import blender_connection as connection


def script(name):
    spec = importlib.util.spec_from_file_location(name, connection.APP / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = script('blender_mcp_host')
manage = script('blender_mcp_manage')


class BlenderConnectionTests(unittest.TestCase):
    def test_management_lock_rejects_simultaneous_launch_and_releases(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(connection, 'DATA', Path(directory)):
            with manage.management_lock():
                with self.assertRaises(RuntimeError):
                    with manage.management_lock(): pass
            with manage.management_lock(): pass

    def test_fragmented_utf8_and_multiple_commands(self):
        message = json.dumps({'type': 'execute_code', 'params': {'code': 'print("星")'}}, ensure_ascii=False).encode()
        split = message.index('星'.encode()) + 1
        messages, buffer = host.parse_messages(message[:split])
        self.assertEqual(messages, [])
        messages, buffer = host.parse_messages(buffer + message[split:] + b' {"type":"get_scene_info"}')
        self.assertEqual(len(messages), 2)
        self.assertEqual(buffer, b'')

    def test_rejects_oversized_complete_message(self):
        with patch.object(host, 'MAX_MESSAGE', 32):
            with self.assertRaises(ValueError): host.parse_messages(b'{"code":"' + b'x' * 33 + b'"}')

    def test_loopback_and_name_validation(self):
        for config in [{'host': '0.0.0.0'}, {'port': 0}, {'server_name': 'invalid.name'}]:
            with patch.object(connection, 'SETTINGS', {'blender_mcp': config}), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError): connection.settings()

    def test_per_process_override_roundtrips_toml(self):
        with patch.object(connection, 'installed', return_value=True):
            args = connection.app_server_args()
        table = tomllib.loads(args[1])['mcp_servers'][connection.settings()['server_name']]
        self.assertEqual(table, connection.spec())
        self.assertEqual(set(table['enabled_tools']), connection.REQUIRED_TOOLS)

    def test_missing_install_does_not_inject_server(self):
        with patch.object(connection, 'installed', return_value=False):
            self.assertEqual(connection.app_server_args(), [])

    def test_repeated_setup_has_no_download_or_pip(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(connection, 'DATA', Path(directory)), patch.object(connection, 'installed', return_value=True), patch.object(manage, 'register') as register, patch.object(manage.subprocess, 'run') as run, patch.object(manage.urllib.request, 'urlopen') as download:
            manage.setup()
            register.assert_called_once(); run.assert_not_called(); download.assert_not_called()

    def test_invalid_download_does_not_replace_addon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'wrong.py'; source.write_bytes(b'wrong')
            addon = root / 'installed.py'; addon.write_bytes(b'previous')
            with patch.object(connection, 'DATA', root), patch.object(connection, 'ADDON', addon), patch.object(connection, 'PYTHON', Path(__file__)), patch.object(connection, 'installed', return_value=False), patch.object(manage.subprocess, 'run'):
                with self.assertRaises(RuntimeError): manage.setup(str(source), no_register=True)
            self.assertEqual(addon.read_bytes(), b'previous')

    def test_registration_idempotent_and_foreign_name_protected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(connection, 'DATA', Path(directory)), patch.object(manage, 'codex_executable', return_value='codex'):
            spec = connection.spec()
            same = {'enabled': True, 'transport': {k: spec[k] for k in ('command', 'args', 'env')}}
            with patch.object(manage.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(same))) as call:
                manage.register(); self.assertEqual(call.call_count, 1)
            foreign = {'transport': {'command': 'someone-else', 'args': [], 'env': {}}}
            with patch.object(manage.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(foreign))) as call:
                with self.assertRaises(RuntimeError): manage.register()
                self.assertEqual(call.call_count, 1)

    def test_occupied_port_never_launches_or_kills(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            config = {**connection.settings(), 'port': listener.getsockname()[1]}
            with patch.object(connection, 'settings', return_value=config), patch.object(connection, 'installed', return_value=True), patch.object(connection, 'status', return_value={'connected': False}), patch.object(manage.subprocess, 'Popen') as launch:
                with self.assertRaises(RuntimeError): manage.start()
                launch.assert_not_called()

    def test_stop_rejects_foreign_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'session.json').write_text(json.dumps({'pid': 123, 'token': 'ours', 'repo': str(manage.REPO)}))
            with patch.object(connection, 'DATA', root), patch.object(connection, 'request', return_value={'result': {'application': 'someone-else', 'pid': 123, 'token': 'ours', 'repo': str(manage.REPO)}}):
                with self.assertRaises(RuntimeError): manage.stop()
            self.assertFalse((root / 'stop-ours').exists())

    def test_two_persistent_clients_on_host(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / 'stop'
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1', 0)); port = reserve.getsockname()[1]
            worker = threading.Thread(target=host.serve, args=(lambda command: {'status': 'success', 'result': command}, {'application': 'test'}, stop, port), daemon=True)
            worker.start()
            first = None
            try:
                for _ in range(50):
                    try: first = socket.create_connection(('127.0.0.1', port), timeout=1); break
                    except ConnectionRefusedError: time.sleep(.02)
                self.assertIsNotNone(first)
                first.sendall(b'{"type":"get_scene_info"}')
                self.assertEqual(json.loads(first.recv(65536))['result']['type'], 'get_scene_info')
                with socket.create_connection(('127.0.0.1', port), timeout=2) as second:
                    second.sendall(b'{"type":"wt_camo_health"}')
                    self.assertEqual(json.loads(second.recv(65536))['result']['application'], 'test')
                first.sendall(b'{"type":"get_scene_info"}')
                self.assertEqual(json.loads(first.recv(65536))['status'], 'success')
            finally:
                if first: first.close()
                stop.touch(); worker.join(3)
            self.assertFalse(worker.is_alive())


if __name__ == '__main__': unittest.main()
