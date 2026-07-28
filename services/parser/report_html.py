"""
report_html.py — render a round-by-round death review as a shareable page.

Builds the verified per-death pack, generates round-by-round coaching (via
coach.generate), and writes a self-contained HTML page styled like an esports
demo-review readout: the recurring pattern up top, then every death as its own
card — what happened, the mistake, the fix — with factual signal chips pulled
straight from the demo (opening duel, no trade, through smoke, etc.).

Output is body-only HTML (a <title>, <style>, content) — publishable as-is.

Usage:
    ./.venv/Scripts/python.exe report_html.py <demo.dem> <target>
"""

import html
import math
import sys
from pathlib import Path

import coach
import context_pack
import skills as skillmod

PISTOLS = {"glock", "hkp2000", "usp_silencer", "p2000", "p250", "tec9",
           "fiveseven", "cz75a", "deagle", "elite", "revolver"}


def esc(s) -> str:
    return html.escape(str(s))


CSS = """
:root{
  --bg:#0b0e13; --surface:#141821; --surface2:#1b212c; --line:#2a3340;
  --ink:#e6ebf2; --muted:#8a97a8; --faint:#5b6675;
  --ct:#5aa9f0; --t:#e0a53d; --good:#3fb950; --crit:#e5484d;
  --mono:ui-monospace,"Cascadia Code","SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
*{box-sizing:border-box}
.report{
  background:var(--bg); color:var(--ink); font-family:var(--sans);
  min-height:100vh; margin:0; padding:clamp(20px,5vw,56px) 16px; line-height:1.55;
  background-image:linear-gradient(var(--line) 1px,transparent 1px),
    linear-gradient(90deg,var(--line) 1px,transparent 1px);
  background-size:44px 44px; background-position:center;
}
.report::before{content:"";position:fixed;inset:0;background:
  radial-gradient(120% 80% at 50% -10%,transparent 40%,var(--bg) 100%);
  pointer-events:none}
.wrap{max-width:760px;margin:0 auto;position:relative}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.28em;
  text-transform:uppercase;color:var(--ct);margin:0 0 6px}
.ticker{font-family:var(--mono);font-size:13px;color:var(--muted);
  letter-spacing:.04em;margin:0 0 30px}
.ticker b{color:var(--ink);font-weight:600}
.sep{color:var(--faint);padding:0 8px}

.pattern{position:relative;padding:22px 22px 22px 26px;margin:0 0 26px;
  background:linear-gradient(180deg,var(--surface2),var(--surface));
  border:1px solid var(--line);border-radius:10px}
.pattern::before{content:"";position:absolute;left:0;top:14px;bottom:14px;
  width:3px;background:var(--t);border-radius:3px}
.pattern .lab{font-family:var(--mono);font-size:11px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--muted);margin:0 0 8px}
.pattern p{margin:0;font-size:clamp(18px,2.7vw,23px);font-weight:640;
  letter-spacing:-.01em;text-wrap:balance;line-height:1.36}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:10px;
  overflow:hidden;margin:0 0 10px}
.cell{background:var(--surface);padding:14px 12px;text-align:center}
.cell .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.cell .v{font-family:var(--mono);font-size:clamp(19px,3.6vw,25px);font-weight:700;
  font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.verified{font-family:var(--mono);font-size:11.5px;color:var(--good);
  letter-spacing:.03em;margin:0 0 36px;display:flex;align-items:center;gap:7px}
.verified::before{content:"";width:7px;height:7px;border-radius:50%;
  background:var(--good);box-shadow:0 0 8px var(--good)}
.radlegend{display:flex;gap:18px;justify-content:center;font-family:var(--mono);
  font-size:11px;color:var(--muted);margin:6px 0 0}
.radlegend span{display:flex;align-items:center;gap:6px}
.lg-you::before{content:"";width:15px;height:3px;background:var(--ct)}
.lg-goal::before{content:"";width:15px;border-top:2px dashed var(--faint)}

.h{font-family:var(--mono);font-size:12px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--muted);margin:0 0 14px;
  padding-bottom:9px;border-bottom:1px solid var(--line)}
.rounds{display:flex;flex-direction:column;gap:12px;margin:0 0 34px}
.rc{background:var(--surface);border:1px solid var(--line);border-radius:10px;
  padding:16px 18px}
.rc-top{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:0 0 11px}
.rlabel{font-family:var(--mono);font-size:13px;font-weight:700;
  letter-spacing:.02em}
.rlabel .rd{color:var(--ct)}
.rmeta{font-family:var(--mono);font-size:11px;color:var(--faint)}
.loc{color:var(--ct);font-weight:700}
.spacer{flex:1}
.chip{font-family:var(--mono);font-size:10.5px;letter-spacing:.04em;
  text-transform:uppercase;border-radius:5px;padding:2px 7px;
  border:1px solid var(--line);color:var(--muted)}
.chip.t{color:var(--t);border-color:rgba(224,165,61,.4);background:rgba(224,165,61,.08)}
.chip.ct{color:var(--ct);border-color:rgba(90,169,240,.4);background:rgba(90,169,240,.08)}
.chip.crit{color:var(--crit);border-color:rgba(229,72,77,.4);background:rgba(229,72,77,.09)}
.chip.good{color:var(--good);border-color:rgba(63,185,80,.4);background:rgba(63,185,80,.08)}
.what{margin:0 0 12px;font-size:14.5px;color:#cdd5e0}
.line{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:baseline;
  margin:0 0 8px}
.tag{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;padding-top:2px}
.tag.m{color:var(--crit)}
.tag.f{color:var(--good)}
.line p{margin:0;font-size:14px;color:var(--ink)}
.line.fix p{color:#cdd5e0}

.foot{border-top:1px solid var(--line);padding-top:22px;text-align:center}
.cta{font-size:17px;font-weight:650;letter-spacing:-.01em;margin:0 0 6px}
.cta b{color:var(--ct)}
.sub{font-family:var(--mono);font-size:12px;color:var(--muted);margin:0 0 14px}
.credit{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.04em}
@media(max-width:480px){.stats{grid-template-columns:repeat(2,1fr)}}
@media(prefers-reduced-motion:no-preference){
  .wrap>*{animation:rise .45s cubic-bezier(.2,.7,.2,1) backwards}
  .wrap>*:nth-child(2){animation-delay:.04s}
  .wrap>*:nth-child(3){animation-delay:.08s}
  .wrap>*:nth-child(n+4){animation-delay:.12s}
  @keyframes rise{from{opacity:0;transform:translateY(10px)}}}
"""


def _chips(sig: dict) -> str:
    out = []
    kb = sig.get("killed_by")
    won = sig.get("round_won")
    non_combat = sig.get("died_to_non_combat")
    if non_combat and won:
        # died to your own bomb / a fall AFTER winning — not a mistake
        out.append(("Round won", "good"))
        out.append(("Bomb blast" if kb == "the bomb exploding"
                    else "Fall", ""))
    elif kb == "the bomb exploding":
        out.append(("Caught by bomb", "crit"))
    elif kb == "fall/world damage":
        out.append(("Fall damage", "t"))
    else:
        if sig.get("was_round_opening_duel"):
            out.append(("Opening duel", "t"))
        out.append(("Traded", "good") if sig.get("traded_by_teammate")
                   else ("No trade", "crit"))
        if sig.get("killed_through_smoke"):
            out.append(("Through smoke", "ct"))
        if sig.get("wallbang"):
            out.append(("Wallbang", "ct"))
        if sig.get("killer_was_blind"):
            out.append(("Lost flashed duel", "crit"))
        if (sig.get("weapon") or "") in PISTOLS:
            out.append(("Pistol death", "t"))
        if sig.get("headshot"):
            out.append(("HS", ""))
    ma = sig.get("man_advantage")
    if ma is not None and ma < 0 and not sig.get("round_won"):
        out.append(("Round already lost", ""))
    dmg = sig.get("damage_you_did_to_killer")
    if dmg is not None and dmg >= 60:
        out.append((f"Was winning · {dmg} dmg", "ct"))
    if sig.get("flashed_when_you_died"):
        out.append(("Died flashed", "crit"))
    unused = sig.get("unused_grenades_at_death") or []
    if unused:
        out.append((f"Unused: {', '.join(unused)}", "t"))
    return "".join(
        f'<span class="chip {cls}">{esc(txt)}</span>' for txt, cls in out
    )


def radar_svg(scores: dict) -> str:
    """Self-contained radar of the six category scores vs the goal ring."""
    cats = [c for c in skillmod.CATEGORIES if c in scores]
    n = len(cats)
    cx, cy, R = 170, 150, 100

    def pt(i, val):
        a = math.radians(-90 + i * 360 / n)
        rr = R * max(val, 0) / 100
        return cx + rr * math.cos(a), cy + rr * math.sin(a)

    def poly(vals):
        return " ".join(f"{x:.1f},{y:.1f}"
                        for x, y in (pt(i, v) for i, v in enumerate(vals)))

    rings = "".join(
        f'<polygon points="{poly([lvl] * n)}" fill="none" '
        f'stroke="var(--line)" stroke-width="1"/>' for lvl in (25, 50, 75, 100))
    axes = labels = ""
    for i, c in enumerate(cats):
        ex, ey = pt(i, 100)
        axes += (f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" '
                 f'stroke="var(--line)" stroke-width="1"/>')
        lx, ly = pt(i, 120)
        anc = "middle" if abs(lx - cx) < 12 else ("end" if lx < cx else "start")
        labels += (
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anc}" '
            f'dominant-baseline="middle" font-family="var(--mono)" '
            f'font-size="10.5" fill="var(--muted)">{esc(c)} '
            f'<tspan fill="var(--ink)" font-weight="700">{scores[c]}</tspan>'
            f'</text>')
    goal = (f'<polygon points="{poly([skillmod.GOALS[c] for c in cats])}" '
            f'fill="none" stroke="var(--faint)" stroke-width="1.5" '
            f'stroke-dasharray="4 3"/>')
    you = (f'<polygon points="{poly([scores[c] for c in cats])}" '
           f'fill="rgba(90,169,240,.18)" stroke="var(--ct)" stroke-width="2"/>')
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" '
                   f'fill="var(--ct)"/>'
                   for x, y in (pt(i, scores[c]) for i, c in enumerate(cats)))
    return (f'<svg viewBox="0 0 340 300" width="100%" '
            f'style="max-width:400px;display:block;margin:2px auto 0">'
            f'{rings}{axes}{goal}{you}{dots}{labels}</svg>')


def render(pack: dict, report: dict, meta: dict) -> str:
    ident, sb = pack["identity"], pack["your_scoreboard"]
    sigs = {d["round"]: d for d in pack["deaths"]}

    stats = [
        ("K / D / A", f"{sb['kills']}/{sb['deaths']}/{sb['assists']}"),
        ("ADR", f"{sb['adr']}"), ("HS%", f"{sb['headshot_pct']}%"),
        ("K / D", f"{sb['kd_ratio']}"),
    ]
    cells = "".join(f'<div class="cell"><div class="k">{esc(k)}</div>'
                    f'<div class="v">{esc(v)}</div></div>' for k, v in stats)

    sk = pack.get("skills")
    skill_section = ""
    if sk:
        skill_section = (
            '<p class="h">Skill Profile — this match</p>'
            '<div class="card" style="padding:16px 18px 14px">'
            + radar_svg(sk) +
            '<p class="radlegend"><span class="lg-you">You</span>'
            '<span class="lg-goal">Goal</span></p></div>')

    cards = ""
    for note in sorted(report["deaths"], key=lambda x: x["round"]):
        sig = sigs.get(note["round"], {})
        side = sig.get("side", "")
        secs = sig.get("seconds_into_round")
        loc = sig.get("location")
        sit = sig.get("situation_when_you_died")
        tail = f'{side} · {secs}s' if secs is not None else side
        if sit:
            tail += f' · {sit}'
        bits = ([f'<span class="loc">{esc(loc)}</span>'] if loc else []) + \
               [esc(tail)]
        cards += (
            f'<div class="rc"><div class="rc-top">'
            f'<span class="rlabel">ROUND <span class="rd">'
            f'{note["round"]:02d}</span></span>'
            f'<span class="rmeta">{" · ".join(bits)}</span>'
            f'<span class="spacer"></span>{_chips(sig)}</div>'
            f'<p class="what">{esc(note["what_happened"])}</p>'
            f'<div class="line"><span class="tag m">Mistake</span>'
            f'<p>{esc(note["mistake"])}</p></div>'
            f'<div class="line fix"><span class="tag f">Fix</span>'
            f'<p>{esc(note["how_to_improve"])}</p></div></div>'
        )

    return f"""<title>AI CS2 Analyst — {esc(ident['player'])} death review, \
{esc(ident['map'])}</title>
<style>{CSS}</style>
<div class="report"><div class="wrap">
  <p class="eyebrow">AI CS2 Analyst // Death Review</p>
  <p class="ticker"><b>{esc(ident['player'])}</b><span class="sep">/</span>\
{esc(ident['map'])}<span class="sep">/</span>{esc(ident['mode'])}\
<span class="sep">/</span>{esc(ident['rounds_played'])} rounds</p>

  <div class="pattern"><p class="lab">The Pattern</p>
    <p>{esc(report['summary'])}</p></div>

  <div class="stats">{cells}</div>
  <p class="verified">Scoreboard verified against FACEIT's own numbers</p>

  {skill_section}

  <p class="h">Every death, and how to fix it</p>
  <div class="rounds">{cards}</div>

  <div class="foot">
    <p class="cta">Every death you took, diagnosed — <b>what went wrong \
and how to fix it.</b></p>
    <p class="sub">Automated from one .dem file. No stats to decode.</p>
    <p class="credit">AI CS2 Analyst · generated by {esc(meta['label'])}</p>
  </div>
</div></div>"""


def main(demo_path: str, target: str) -> None:
    pack = context_pack.build_pack(demo_path, target)
    print(f"Analyzing {target} on {pack['identity']['map']}...")
    report, meta = coach.generate(pack)

    out_dir = Path(__file__).parents[2] / "reports"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{target}_{pack['identity']['map']}.html"
    out.write_text(render(pack, report, meta), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python report_html.py <demo.dem> <target>")
    main(sys.argv[1], sys.argv[2])
