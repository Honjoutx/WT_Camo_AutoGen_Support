import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_livery_core import audit_scene, clear_scene, import_model


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main():
    parser = argparse.ArgumentParser(description="Open a vehicle in the portable Blender MCP session")
    parser.add_argument("--model", required=True)
    args = parser.parse_args(blender_args())
    clear_scene()
    objects = import_model(args.model)
    for obj in objects:
        obj.select_set(True)
    if objects:
        import bpy

        bpy.context.view_layer.objects.active = objects[0]
    print("CAMO_OPENED=" + str(Path(args.model).resolve()))
    print("CAMO_SCENE=" + str(audit_scene()))


if __name__ == "__main__":
    main()
