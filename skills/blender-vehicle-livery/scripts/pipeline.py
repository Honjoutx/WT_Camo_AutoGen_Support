import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_livery_core import run_pipeline


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main():
    parser = argparse.ArgumentParser(description="Apply a preset vehicle livery in Blender")
    parser.add_argument("--model", required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(blender_args())
    report = run_pipeline(args.model, args.preset, args.output)
    print("CAMO_PIPELINE_JSON=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
