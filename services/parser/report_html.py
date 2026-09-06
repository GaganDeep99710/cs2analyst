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
import json
import math
import sys
from pathlib import Path

import coach
import context_pack
import skills as skillmod

_RADAR_DIR = Path(__file__).parents[2] / "radars"


def _calib(map_name: str) -> dict | None:
    try:
        return json.loads((_RADAR_DIR / "calib.json").read_text()).get(map_name)
    except Exception:  # noqa: BLE001
        return None

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

.verdict{font-size:clamp(15px,2.2vw,17px);line-height:1.6;color:#cdd5e0;
  margin:0 0 28px}
.pattern{position:relative;padding:22px 22px 22px 26px;margin:0 0 18px;
  background:linear-gradient(180deg,var(--surface2),var(--surface));
  border:1px solid var(--line);border-radius:10px}
.pattern::before{content:"";position:absolute;left:0;top:14px;bottom:14px;
  width:3px;background:var(--t);border-radius:3px}
.pattern .lab{font-family:var(--mono);font-size:11px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--muted);margin:0 0 8px}
.pattern p{margin:0;font-size:clamp(18px,2.7vw,23px);font-weight:640;
  letter-spacing:-.01em;text-wrap:balance;line-height:1.36}
.leak{position:relative;padding:18px 20px 18px 24px;margin:0 0 14px;
  background:rgba(229,72,77,.06);border:1px solid rgba(229,72,77,.28);
  border-radius:10px}
.leak::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;
  background:var(--crit);border-radius:3px}
.leak .lab{font-family:var(--mono);font-size:11px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--crit);margin:0 0 7px}
.leak p{margin:0;font-size:15px;line-height:1.55;color:var(--ink)}
.win{position:relative;padding:14px 18px;margin:0 0 30px;
  background:rgba(63,185,80,.05);border:1px solid rgba(63,185,80,.25);
  border-radius:10px}
.win .lab{font-family:var(--mono);font-size:11px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--good);margin:0 0 6px}
.win p{margin:0;font-size:14.5px;line-height:1.5;color:#cdd5e0}
.prio{list-style:none;counter-reset:p;margin:0 0 34px;padding:0;
  display:flex;flex-direction:column;gap:10px}
.prio li{counter-increment:p;position:relative;padding:14px 16px 14px 52px;
  background:var(--surface);border:1px solid var(--line);border-radius:10px;
  font-size:14.5px;color:var(--ink);line-height:1.5}
.prio li::before{content:counter(p);position:absolute;left:16px;top:12px;
  width:24px;height:24px;border-radius:6px;background:var(--accent-soft,rgba(90,169,240,.12));
  color:var(--ct);font-family:var(--mono);font-weight:700;font-size:13px;
  display:flex;align-items:center;justify-content:center;
  border:1px solid rgba(90,169,240,.35)}

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


REPLAY_CSS = """
.replay{margin:12px 0 0;border-top:1px dashed var(--line);padding-top:10px}
.replay>summary{list-style:none;cursor:pointer;font-family:var(--mono);
  font-size:12px;letter-spacing:.06em;color:var(--ct);display:inline-flex;
  align-items:center;gap:7px;user-select:none}
.replay>summary::-webkit-details-marker{display:none}
.replay>summary:hover{color:#7dbcf5}
.rp{margin-top:12px}
.rp canvas{width:100%;max-width:420px;aspect-ratio:1;display:block;margin:0 auto;
  border:1px solid var(--line);border-radius:10px;background:#0b0e13}
.rpc{display:flex;align-items:center;gap:12px;max-width:420px;margin:10px auto 0}
.rpplay{flex:0 0 auto;width:38px;height:38px;border-radius:9px;padding:0;font-size:14px}
.rpseek{flex:1;accent-color:var(--ct);height:4px}
.rplegend{font-family:var(--mono);font-size:10.5px;color:var(--muted);
  display:flex;gap:12px;justify-content:center;max-width:420px;margin:8px auto 0}
.rplegend b{display:inline-block;width:9px;height:9px;border-radius:50%;
  margin-right:5px;vertical-align:-1px}
"""

REPLAY_JS = """<script>
(function(){
 var CAL=window.__CALIB, RAD=document.getElementById('_radar');
 if(!CAL||!RAD) return;
 function w2c(x,y,b,S){return [ (x-b[0])/b[2]*S, (b[1]-y)/b[2]*S ];}
 function init(det){
  if(det.__init) return; det.__init=true;
  var D=JSON.parse(det.querySelector('.rpdata').textContent);
  var cv=det.querySelector('canvas'), ctx=cv.getContext('2d'), S=cv.width;
  var seek=det.querySelector('.rpseek'), play=det.querySelector('.rpplay');
  var F=D.f, i=0, playing=false, last=0, trail=[];
  seek.max=F.length-1;
  var sx=(D.bbox[0]-CAL.pos_x)/CAL.scale, sy=(CAL.pos_y-D.bbox[1])/CAL.scale, ss=D.bbox[2]/CAL.scale;
  function draw(){
   ctx.clearRect(0,0,S,S);
   if(RAD.complete&&RAD.naturalWidth) ctx.drawImage(RAD,sx,sy,ss,ss,0,0,S,S);
   ctx.fillStyle='rgba(11,14,19,.32)';ctx.fillRect(0,0,S,S);
   var fr=F[i], t=D.target_i, k=D.killer_i;
   if(t!=null&&fr[t][2]){var q=w2c(fr[t][0],fr[t][1],D.bbox,S);trail.push(q);if(trail.length>16)trail.shift();}
   ctx.strokeStyle='rgba(255,255,255,.35)';ctx.lineWidth=2;ctx.beginPath();
   trail.forEach(function(p,n){n?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);});ctx.stroke();
   fr.forEach(function(p,n){
    var c=w2c(p[0],p[1],D.bbox,S),x=c[0],y=c[1],col=D.roster[n].tm===3?'#5aa9f0':'#e0a53d';
    if(!p[2]){ctx.strokeStyle='rgba(130,140,150,.5)';ctx.lineWidth=2;ctx.beginPath();
      ctx.moveTo(x-4,y-4);ctx.lineTo(x+4,y+4);ctx.moveTo(x+4,y-4);ctx.lineTo(x-4,y+4);ctx.stroke();return;}
    ctx.beginPath();ctx.arc(x,y,6,0,7);ctx.fillStyle=col;ctx.fill();
    if(n===t){ctx.lineWidth=3;ctx.strokeStyle='#fff';ctx.beginPath();ctx.arc(x,y,10,0,7);ctx.stroke();}
    if(n===k){ctx.lineWidth=3;ctx.strokeStyle='#e5484d';ctx.beginPath();ctx.arc(x,y,10,0,7);ctx.stroke();}
   });
   if(i>=F.length-1&&t!=null){var p=F[F.length-1][t],c=w2c(p[0],p[1],D.bbox,S);
    ctx.strokeStyle='#e5484d';ctx.lineWidth=3;ctx.beginPath();ctx.arc(c[0],c[1],14,0,7);ctx.stroke();
    ctx.fillStyle='#e5484d';ctx.font='bold 12px monospace';ctx.fillText('\\u2716 killed here',c[0]+15,c[1]-9);}
   seek.value=i;
  }
  function loop(ts){ if(!playing)return; if(ts-last>90){i++;last=ts;
    if(i>=F.length){i=F.length-1;playing=false;play.textContent='\\u21bb';draw();return;} draw();}
   requestAnimationFrame(loop);}
  play.onclick=function(){ if(i>=F.length-1){i=0;trail.length=0;}
   playing=!playing; play.textContent=playing?'\\u275a\\u275a':'\\u25b6';
   if(playing){last=0;requestAnimationFrame(loop);}};
  seek.oninput=function(){playing=false;play.textContent='\\u25b6';i=+seek.value;trail.length=0;draw();};
  det.addEventListener('toggle',function(){if(det.open){i=0;trail.length=0;draw();}});
  draw();
 }
 function initOpen(){document.querySelectorAll('details.replay[open]').forEach(init);}
 document.querySelectorAll('details.replay').forEach(function(d){
   d.addEventListener('toggle',function(){if(d.open)init(d);});});
 if(RAD.complete) initOpen(); else RAD.addEventListener('load',initOpen);
})();
</script>"""


def _replay_block(rnd: int, data: dict) -> str:
    return (
        '<details class="replay"><summary>&#9654; Watch the mistake</summary>'
        '<div class="rp"><canvas width="560" height="560"></canvas>'
        '<div class="rpc"><button class="rpplay">&#9654;</button>'
        '<input class="rpseek" type="range" min="0" value="0"></div>'
        '<div class="rplegend"><span><b style="background:#5aa9f0"></b>CT</span>'
        '<span><b style="background:#e0a53d"></b>T</span>'
        '<span><b style="background:#fff"></b>You</span>'
        '<span><b style="background:#e5484d"></b>Killer</span></div></div>'
        f'<script class="rpdata" type="application/json">{json.dumps(data)}</script>'
        '</details>')


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
    # widen the viewBox horizontally so long left/right labels (Positioning,
    # Fragging) don't clip off the edges; chart stays centered on cx=170.
    return (f'<svg viewBox="-46 0 432 300" width="100%" '
            f'style="max-width:440px;display:block;margin:2px auto 0">'
            f'{rings}{axes}{goal}{you}{dots}{labels}</svg>')


def render(pack: dict, report: dict, meta: dict,
           replays: dict | None = None, radar_src: str | None = None) -> str:
    ident, sb = pack["identity"], pack["your_scoreboard"]
    sigs = {d["round"]: d for d in pack["deaths"]}
    replays = replays or {}
    map_name = ident["map"]
    calib = _calib(map_name) if replays else None
    if not calib:
        replays = {}  # no calibration for this map -> no replays

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
            f'<p>{esc(note["how_to_improve"])}</p></div>'
            + (_replay_block(note["round"], replays[note["round"]])
               if note["round"] in replays else "")
            + '</div>'
        )

    verdict_html = (f'<p class="verdict">{esc(report["verdict"])}</p>'
                    if report.get("verdict") else "")
    leak_html = (
        f'<div class="leak"><p class="lab">Your biggest leak</p>'
        f'<p>{esc(report["biggest_leak"])}</p></div>'
        if report.get("biggest_leak") else "")
    strength_html = (
        f'<div class="win"><p class="lab">What\'s working</p>'
        f'<p>{esc(report["strength"])}</p></div>'
        if report.get("strength") else "")
    prios = report.get("priorities") or []
    prio_html = ""
    if prios:
        items = "".join(f"<li>{esc(p)}</li>" for p in prios)
        prio_html = (f'<p class="h">Fix these first</p>'
                     f'<ol class="prio">{items}</ol>')

    replay_foot = ""
    if replays:
        src = radar_src or f"/radar/{map_name}.png"
        replay_foot = (
            f'<img id="_radar" src="{src}" alt="" style="display:none"'
            f' crossorigin="anonymous">'
            f'<script>window.__CALIB={json.dumps(calib)}</script>'
            + REPLAY_JS)

    return f"""<title>AI CS2 Analyst — {esc(ident['player'])} death review, \
{esc(ident['map'])}</title>
<style>{CSS}{REPLAY_CSS}</style>
<div class="report"><div class="wrap">
  <p class="eyebrow">AI CS2 Analyst // Death Review</p>
  <p class="ticker"><b>{esc(ident['player'])}</b><span class="sep">/</span>\
{esc(ident['map'])}<span class="sep">/</span>{esc(ident['mode'])}\
<span class="sep">/</span>{esc(ident['rounds_played'])} rounds</p>

  {verdict_html}

  <div class="stats">{cells}</div>
  <p class="verified">Scoreboard verified against FACEIT's own numbers</p>

  {skill_section}

  <div class="pattern"><p class="lab">The Pattern</p>
    <p>{esc(report['summary'])}</p></div>
  {leak_html}
  {strength_html}

  <p class="h">Every death, and how to fix it</p>
  <div class="rounds">{cards}</div>

  {prio_html}

  <div class="foot">
    <p class="cta">Every death you took, diagnosed — <b>what went wrong \
and how to fix it.</b></p>
    <p class="sub">Automated from one .dem file. No stats to decode.</p>
    <p class="credit">AI CS2 Analyst · generated by {esc(meta['label'])}</p>
  </div>
</div></div>{replay_foot}"""


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
