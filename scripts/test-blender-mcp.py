import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER = PROJECT_ROOT / ".tools" / "blender-mcp-env" / "Scripts" / "blender-mcp.exe"


async def main() -> None:
    env = dict(os.environ)
    env.update(
        {
            "BLENDER_HOST": "localhost",
            "BLENDER_PORT": "9876",
            "DISABLE_TELEMETRY": "true",
        }
    )
    params = StdioServerParameters(command=str(SERVER), args=[], env=env)
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            scene = await session.call_tool(
                "get_scene_info",
                arguments={"user_prompt": "Integration smoke test; return scene metadata only."},
            )
            panel = await session.call_tool(
                "execute_blender_code",
                arguments={
                    "code": (
                        "import bpy\n"
                        "settings = bpy.context.scene.camo_livery\n"
                        "material = bpy.data.materials.get(settings.material_name)\n"
                        "noise = material.node_tree.nodes.get('CAMO_MainNoise') if material else None\n"
                        "print({'panel_registered': hasattr(bpy.types.Scene, 'camo_livery'), "
                        "'preset_path': settings.preset_path, 'status': settings.status, "
                        "'pattern_scale': float(noise.inputs['Scale'].default_value) if noise else None})"
                    ),
                    "user_prompt": "Verify the project-local livery panel and report live state only.",
                },
            )
            anime_panel = await session.call_tool(
                "execute_blender_code",
                arguments={
                    "code": (
                        "import bpy\n"
                        "settings = bpy.context.scene.anime_livery\n"
                        "projectors = [obj.name for obj in bpy.data.objects "
                        "if obj.name.startswith('ANIME_Projector_')]\n"
                        "print({'panel_registered': hasattr(bpy.types.Scene, 'anime_livery'), "
                        "'project_path': settings.project_path, 'status': settings.status, "
                        "'active_layer': settings.active_layer_name, "
                        "'projectors': projectors})"
                    ),
                    "user_prompt": "Verify the layered anime livery panel and report live state only.",
                },
            )
            print(
                json.dumps(
                    {
                        "tool_count": len(names),
                        "tools": names,
                        "scene_result": [
                            getattr(item, "text", str(item)) for item in scene.content
                        ],
                        "panel_result": [
                            getattr(item, "text", str(item)) for item in panel.content
                        ],
                        "anime_panel_result": [
                            getattr(item, "text", str(item)) for item in anime_panel.content
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
