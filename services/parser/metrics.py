"""
metrics.py — verified scoreboard. Numbers match FACEIT (roadmap task 116 gate).

Usage:
    ./.venv/Scripts/python.exe metrics.py <demo.dem> [target_name]
"""

import sys

import core


def main(demo_path: str, target: str | None) -> None:
    p = core.load(demo_path)
    n = len(core.real_round_bounds(p))
    table = core.scoreboard(p)

    print(f"\nReal rounds: {n}\n")
    print("SCOREBOARD  (FA = flash assists)")
    print(table.to_string(index=False))

    if target:
        row = table[table["player"].str.lower() == target.lower()]
        print("\n" + "=" * 52)
        if len(row):
            r = row.iloc[0]
            print(f"  YOU - {r['player']}")
            print(f"  {r['K']}/{r['D']}/{r['A']}"
                  f"{f' (+{r['FA']} FA)' if r['FA'] else ''}"
                  f"   ADR {r['ADR']}   HS {r['HS%']}%   K/D {r['K/D']}")
        else:
            print(f"  '{target}' not found: {', '.join(table['player'])}")
        print("=" * 52 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python metrics.py <demo.dem> [target_name]")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
