"""
callouts.py — resolve a world position to its CS2 callout.

Uses callouts.json (extracted from the game's own env_cs_place entities by
extract_callouts.py). Nearest-centroid over every callout volume's origin;
validated against bomb-plant ground truth (A/B plants resolve to the right
site with zero errors). Keeping all sub-volumes per callout improves accuracy.
"""

import json
import re
from pathlib import Path

_DATA = json.loads(
    (Path(__file__).parents[2] / "callouts" / "callouts.json")
    .read_text(encoding="utf-8")
)

_PRETTY = {
    "BombsiteA": "A site", "BombsiteB": "B site",
    "CTSpawn": "CT spawn", "TSpawn": "T spawn",
    "SecondMid": "Second Mid", "TopofMid": "Top Mid",
    "LowerMid": "Lower Mid", "BackAlley": "Back Alley", "TRamp": "T Ramp",
}


def prettify(name: str) -> str:
    if name in _PRETTY:
        return _PRETTY[name]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name)  # camelCase -> spaced


def resolve(map_name: str, x, y, z, pretty: bool = True) -> str | None:
    pts = _DATA.get(map_name)
    if not pts or x is None:
        return None
    best = min(pts, key=lambda c: (c["x"] - x) ** 2
               + (c["y"] - y) ** 2 + (c["z"] - z) ** 2)
    return prettify(best["name"]) if pretty else best["name"]


def has_map(map_name: str) -> bool:
    return map_name in _DATA
