"""
extract_callouts.py — pull env_cs_place callouts from CS2 map files.

Runs the ValveResourceFormat CLI to decompile each map's entity lump, parses
the env_cs_place entities (Valve's own callout regions), and writes
callouts.json: {map: [{name, x, y, z}, ...]}. The origin of each env_cs_place
is the callout centre — enough to classify any position by nearest callout.

Usage:
    python extract_callouts.py            # all maps
    python extract_callouts.py de_inferno # one map
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
CLI = ROOT / "tools" / "Source2Viewer-CLI.exe"
CS2_MAPS = Path(
    "C:/Program Files (x86)/Steam/steamapps/common/"
    "Counter-Strike Global Offensive/game/csgo/maps"
)
EXTRACT = ROOT / "callouts" / "extract"

ACTIVE = ["de_inferno", "de_mirage", "de_nuke", "de_ancient",
          "de_anubis", "de_dust2", "de_overpass", "de_train", "de_vertigo"]

_ORIGIN = re.compile(r"\[\s*(-?[\d.]+),\s*(-?[\d.]+),\s*(-?[\d.]+)\s*\]")


def _decompile(map_name: str) -> Path:
    """Decompile <map>'s entity lump if not already done; return the .vents."""
    out = (EXTRACT / "maps" / map_name / "entities" / "default_ents.vents")
    if out.exists():
        return out
    vpk = CS2_MAPS / f"{map_name}.vpk"
    subprocess.run(
        [str(CLI), "-i", str(vpk), "-f",
         f"maps/{map_name}/entities/default_ents.vents_c",
         "-d", "-o", str(EXTRACT)],
        check=True, capture_output=True, text=True,
    )
    return out


def parse_callouts(vents_path: Path) -> list[dict]:
    """Parse env_cs_place entities into {name, x, y, z}."""
    text = vents_path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"={4,}\d+={4,}", text)
    out = []
    for b in blocks:
        if 'classname' not in b or '"env_cs_place"' not in b:
            continue
        name_m = re.search(r'place_name\s+"([^"]+)"', b)
        orig_m = re.search(r"origin\s+" + _ORIGIN.pattern, b)
        if not (name_m and orig_m):
            continue
        out.append({
            "name": name_m.group(1),
            "x": float(orig_m.group(1)),
            "y": float(orig_m.group(2)),
            "z": float(orig_m.group(3)),
        })
    return out


def main(maps: list[str]) -> None:
    if not CLI.exists():
        sys.exit(f"VRF CLI not found at {CLI}")
    result = {}
    for m in maps:
        vpk = CS2_MAPS / f"{m}.vpk"
        if not vpk.exists():
            print(f"  skip {m}: no vpk")
            continue
        print(f"  extracting {m}...", end=" ", flush=True)
        try:
            callouts = parse_callouts(_decompile(m))
            result[m] = callouts
            print(f"{len(callouts)} callouts")
        except subprocess.CalledProcessError as e:
            print(f"FAILED ({e.stderr[:80] if e.stderr else e})")

    out = ROOT / "callouts" / "callouts.json"
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"\nWrote {out} ({sum(len(v) for v in result.values())} total)")


if __name__ == "__main__":
    main(sys.argv[1:] or ACTIVE)
