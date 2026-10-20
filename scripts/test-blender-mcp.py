"""Actual MCP stdio test. Run with .tools/blender-mcp-env/Scripts/python.exe."""
from pathlib import Path
import asyncio
import json
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/livery-layout-editor'))
import blender_connection as connection
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    host = connection.status()
    if not host['connected']:
        raise RuntimeError(host.get('error', host.get('hint')))
    spec = connection.spec()
    params = StdioServerParameters(command=spec['command'], args=spec['args'], env={**os.environ, **spec['env']})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = [tool.name for tool in (await session.list_tools()).tools]
            if not connection.REQUIRED_TOOLS.issubset(names):
                raise RuntimeError('Required Blender tools are missing.')
            scene = await session.call_tool('get_scene_info', {'user_prompt': 'Read-only connection diagnostic.'})
            code = await session.call_tool('execute_blender_code', {'code': "import bpy\nprint({'background': bpy.app.background, 'objects': len(bpy.context.scene.objects), 'addon_enabled': 'blender_mcp' in bpy.context.preferences.addons})", 'user_prompt': 'Read-only connection diagnostic.'})
            for result in (scene, code):
                if result.isError or any(getattr(c, 'text', '').startswith('Error') for c in result.content):
                    raise RuntimeError(str(result.content))
            print(json.dumps({'tool_count': len(names), 'required_tools': sorted(connection.REQUIRED_TOOLS),
                              'scene': [c.text for c in scene.content if hasattr(c, 'text')],
                              'execution': [c.text for c in code.content if hasattr(c, 'text')]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=45))
