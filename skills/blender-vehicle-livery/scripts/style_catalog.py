import argparse
import json
from pathlib import Path


STYLE_VERSION = 1
SURFACE_CHANNELS = ("roughness", "metallic", "coat_weight", "coat_roughness")


def default_library():
    return Path(__file__).resolve().parents[1] / "assets" / "styles"


def load_cards(library=None):
    library = Path(library or default_library()).resolve()
    cards = []
    for path in sorted(library.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        validate_card(card, path)
        cards.append((path, card))
    ids = [card["id"] for _, card in cards]
    if len(ids) != len(set(ids)):
        raise ValueError("style library contains duplicate style ids")
    return cards


def _unit_interval(value, label):
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be in [0, 1]")


def validate_card(card, path="<memory>"):
    if int(card.get("version", 0)) != STYLE_VERSION:
        raise ValueError(f"{path}: style version must be {STYLE_VERSION}")
    for field in ("id", "name", "summary"):
        if not str(card.get(field, "")).strip():
            raise ValueError(f"{path}: style card requires {field}")
    if not isinstance(card.get("tags"), list) or not card["tags"]:
        raise ValueError(f"{path}: style card requires non-empty tags")
    palette = card.get("palette")
    if not isinstance(palette, dict) or not palette:
        raise ValueError(f"{path}: style card requires a palette object")
    for role, color in palette.items():
        if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
            raise ValueError(f"{path}: palette.{role} must be #RRGGBB")
        int(color[1:], 16)
    roles = card.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError(f"{path}: style card requires ordered roles")
    role_ids = set()
    for role in roles:
        role_id = str(role.get("id", "")).strip()
        if not role_id or role_id in role_ids:
            raise ValueError(f"{path}: every role requires a unique id")
        role_ids.add(role_id)
        surface = role.get("surface", {})
        if not isinstance(surface, dict):
            raise ValueError(f"{path}: role {role_id} surface must be an object")
        for channel in SURFACE_CHANNELS:
            if channel in surface:
                _unit_interval(surface[channel], f"{path}: role {role_id} surface.{channel}")
    provenance = card.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("kind"):
        raise ValueError(f"{path}: style card requires provenance.kind")
    return card


def catalog_summary(cards):
    return [
        {
            "id": card["id"],
            "name": card["name"],
            "tags": card["tags"],
            "summary": card["summary"],
            "path": str(path),
        }
        for path, card in cards
    ]


def main():
    parser = argparse.ArgumentParser(description="List, inspect, and validate livery style cards")
    parser.add_argument("command", choices=("list", "show", "validate"))
    parser.add_argument("style_id", nargs="?")
    parser.add_argument("--library", default=str(default_library()))
    args = parser.parse_args()
    cards = load_cards(args.library)
    if args.command == "list":
        result = catalog_summary(cards)
    elif args.command == "validate":
        result = {"valid": True, "styles": len(cards), "library": str(Path(args.library).resolve())}
    else:
        if not args.style_id:
            parser.error("show requires style_id")
        result = next((card for _, card in cards if card["id"] == args.style_id), None)
        if result is None:
            raise SystemExit(f"unknown style id: {args.style_id}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
