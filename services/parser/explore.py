"""
explore.py — the 'eyeball' tool.

Point it at a CS2 .dem file and it prints a human-readable summary:
match header, round count + final score, top fraggers, event inventory.

The entire point is trust: you read this output, compare it to what you
remember from the actual match, and confirm the parser sees reality before
we build a single metric on top of it. (Roadmap task 71.)

Usage:
    ./.venv/Scripts/python.exe explore.py ../../demos/yourmatch.dem
"""

import sys
from collections import Counter
from pathlib import Path

from demoparser2 import DemoParser


def main(demo_path: str) -> None:
    path = Path(demo_path)
    if not path.exists():
        sys.exit(f"No such file: {path}")

    print(f"\n{'=' * 60}")
    print(f"  {path.name}  ({path.stat().st_size / 1_048_576:.1f} MB)")
    print(f"{'=' * 60}")

    parser = DemoParser(str(path))

    # --- header -----------------------------------------------------------
    header = parser.parse_header()
    print("\n[HEADER]")
    for key in ("map_name", "server_name", "demo_version_name",
                "network_protocol", "playback_frames", "playback_ticks"):
        if key in header:
            print(f"  {key:20} {header[key]}")

    # --- event inventory --------------------------------------------------
    # What can this demo actually tell us? Everything downstream is a
    # selection from this list, so we print it once and study it.
    try:
        events = parser.list_game_events()
        print(f"\n[GAME EVENTS AVAILABLE]  ({len(events)})")
        # print in columns
        events = sorted(events)
        for i in range(0, len(events), 4):
            print("  " + "".join(f"{e:<22}" for e in events[i:i + 4]))
    except Exception as exc:  # noqa: BLE001
        print(f"\n[GAME EVENTS] could not list: {exc}")

    # --- rounds & score ---------------------------------------------------
    try:
        rounds = parser.parse_event("round_end")
        print(f"\n[ROUNDS]  {len(rounds)} round_end events")
        if len(rounds) and "winner" in rounds.columns:
            winners = Counter(rounds["winner"].tolist())
            for team, n in winners.items():
                print(f"  winner={team:<8} {n} rounds")
        if len(rounds) and "reason" in rounds.columns:
            reasons = Counter(rounds["reason"].tolist())
            print("  end reasons:", dict(reasons))
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ROUNDS] could not parse round_end: {exc}")

    # --- kills / top fraggers --------------------------------------------
    try:
        deaths = parser.parse_event("player_death")
        print(f"\n[KILLS]  {len(deaths)} player_death events")
        if len(deaths) and "attacker_name" in deaths.columns:
            frags = Counter(
                a for a in deaths["attacker_name"].tolist() if a
            )
            print("  top fraggers:")
            for name, n in frags.most_common(12):
                print(f"    {n:3}  {name}")
        if len(deaths) and "headshot" in deaths.columns:
            hs = deaths["headshot"].sum()
            print(f"  headshots: {hs} / {len(deaths)} "
                  f"({100 * hs / max(len(deaths), 1):.0f}%)")
        if len(deaths) and "weapon" in deaths.columns:
            weapons = Counter(deaths["weapon"].tolist())
            print("  top weapons:",
                  dict(Counter(weapons).most_common(6)))
    except Exception as exc:  # noqa: BLE001
        print(f"\n[KILLS] could not parse player_death: {exc}")

    # --- grenades (utility is our differentiator, confirm it's here) ------
    for ev in ("flashbang_detonate", "hegrenade_detonate",
               "smokegrenade_detonate", "molotov_detonate"):
        try:
            df = parser.parse_event(ev)
            print(f"\n[{ev}]  {len(df)} events"
                  + (f"  cols={list(df.columns)}" if len(df) else ""))
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{ev}] not available: {exc}")

    print(f"\n{'=' * 60}")
    print("  If the map, round count and top fraggers match your memory")
    print("  of this match, the parser sees reality. Next: metrics.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python explore.py <path-to-demo.dem>")
    main(sys.argv[1])
