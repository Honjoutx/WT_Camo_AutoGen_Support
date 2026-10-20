"""Persistent language/config behavior and frozen resource/data separation."""
from pathlib import Path
import copy
import importlib.util
import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import app_settings
import runtime
import workflow
import external_process


class DesktopSettingsTests(unittest.TestCase):
    def test_language_persists_and_rejects_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app_settings,'PREFERENCES',Path(directory)/'prefs.json'):
            self.assertIsNone(app_settings.preferences()['language'])
            self.assertEqual(app_settings.save_preferences({'language':'en'}),{'language':'en'})
            with self.assertRaises(ValueError):app_settings.save_preferences({'language':'other'})
            self.assertEqual(app_settings.preferences(),{'language':'en'})

    def test_settings_preserve_unrelated_values_and_flag_workspace_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'runtime.local.json';exe=root/'fake.exe';exe.touch()
            config.write_text(json.dumps({'render':{'samples':37},'blender_mcp':{'port':18879}}))
            values={}
            with patch.object(app_settings,'CONFIG',config),patch.object(app_settings,'SETTINGS',values):
                result=app_settings.save({'codex':str(exe),'blender':'','workspace':str(root)})
            saved=json.loads(config.read_text())
            self.assertEqual(saved['render']['samples'],37)
            self.assertEqual(saved['blender_mcp']['port'],18879)
            self.assertTrue(result['restart_required'])
            self.assertEqual(values['codex'],str(exe.resolve()))

    def test_frozen_runtime_keeps_projects_outside_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'application/_internal';data=root/'user-data'
            env={k:v for k,v in os.environ.items() if k not in ('WT_CAMO_CONFIG','WT_CAMO_WORKSPACE')}
            env['WT_CAMO_APP_DATA']=str(data)
            with patch.dict(os.environ,env,clear=True),patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(bundle),create=True):
                spec=importlib.util.spec_from_file_location('test_frozen_runtime',runtime.HERE/'runtime.py')
                loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
            self.assertEqual(loaded.HERE,bundle/'tools/livery-layout-editor')
            self.assertEqual(loaded.ROOT,data/'workspace')
            self.assertEqual(loaded.CONFIG,data/'config/runtime.local.json')
            self.assertFalse(bundle.exists())

    def test_english_workflow_and_reply_language(self):
        english=workflow.catalogue('en');chinese=workflow.catalogue('zh-CN')
        self.assertEqual([s['id'] for s in english['stages']],[s['id'] for s in chinese['stages']])
        self.assertIn('Design sketch',english['stages'][2]['title'])
        self.assertIn('Preserve original',english['guide'])
        manager=SimpleNamespace(config=lambda pid:{'directory':'projects/test','type':'boards'})
        text=workflow.context(manager,'test',stage='sketch',language='en')
        self.assertIn('Reply in English',text)
        self.assertNotIn('除非用户另有要求，以中文交流',text)

    def test_external_process_path_excludes_bundle_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'bundle';system=Path(directory)/'system'
            with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(base),create=True):
                env=external_process.environment({'PATH':os.pathsep.join([str(base),str(base/'lib'),str(system)]),'KEEP':'value'})
            self.assertEqual(env['PATH'],str(system));self.assertEqual(env['KEEP'],'value')


if __name__=='__main__':unittest.main()
