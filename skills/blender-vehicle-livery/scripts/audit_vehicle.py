import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_livery_core import audit_scene, clear_scene, import_model


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main():
    parser = argparse.ArgumentParser(description="Audit a vehicle model in Blender")
    parser.add_argument("--model", required=True)
    parser.add_argument("--report")
    args = parser.parse_args(blender_args())
    clear_scene()
    import_model(args.model)
    report = audit_scene()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    print("CAMO_AUDIT_JSON=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
