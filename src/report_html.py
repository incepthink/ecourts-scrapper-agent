"""Render a single self-contained HTML summary for one advocate.

Everything the scraper learns about an advocate already lives in the DB
(advocates / cases / case_advocates / orders). This module aggregates it into
*one* human-readable page — their full case portfolio, outcomes, courts/judges,
orders (linked to the downloaded PDFs) and frequent co-advocates — replacing the
pile of per-complex / per-case intermediate HTML files.

The page is a premium, self-contained "legal dossier": a navy + gold themed
profile (think auto-generated lawyer resume) with animated stat cards, an outcome
visualisation, an AI profile section, and rich, filterable case cards. It uses
Google Fonts when online and falls back to system fonts offline; no other
external assets are required, so the file stays small and emailable.

Kept dependency-light (no network / bharat-courts imports) so it runs standalone:
    python src/report_html.py "Tanveer Nizam"
"""

from __future__ import annotations

import html
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

import ai_summary
import config
from profile_data import (
    _OUTCOME_LABEL,
    _ai_aggregates,
    _case_digests,
    _compute_stats,
    _disposition,
    _load_cases,
    _matching_advocates,
    _outcome_class,
)
from store import Advocate, Case, CaseAdvocate, Order, Session, normalize_name


def _slug(text: str) -> str:
    """Filesystem-safe slug (matches pipeline._slug)."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return s or "x"


def _e(value) -> str:
    """HTML-escape any value (None -> '')."""
    return html.escape(str(value) if value is not None else "")


def _pdf_href(pdf_local_path: str) -> str | None:
    """A link relative to DATA_DIR (where the summary lives), or None."""
    if not pdf_local_path:
        return None
    try:
        rel = os.path.relpath(pdf_local_path, config.DATA_DIR)
    except ValueError:  # e.g. different drive on Windows
        rel = pdf_local_path
    return rel.replace(os.sep, "/")


def _initials(name: str) -> str:
    """Monogram initials: first + last word initial (or first two letters)."""
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# ---- assets (fonts, icons, style, script) ---------------------------------

_FONTS_LINK = (
    "<link rel='preconnect' href='https://fonts.googleapis.com'>"
    "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
    "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?"
    "family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,500&"
    "family=Inter:wght@400;500;600;700&display=swap'>"
)

# Minimal lucide-style stroke icons (24x24, currentColor).
_ICONS = {
    "scale": '<path d="M12 3v18"/><path d="M5 7h14l-3 0"/><path d="M7 7l-3.5 7a3.5 3.5 0 0 0 7 0z"/>'
             '<path d="M17 7l-3.5 7a3.5 3.5 0 0 0 7 0z"/><path d="M7.5 21h9"/>',
    "gavel": '<path d="m14 13-7.5 7.5a2.12 2.12 0 0 1-3-3L11 10"/><path d="m16 16 5-5"/>'
             '<path d="m8 8 5-5"/><path d="m9 7 8 8"/><path d="m21 11-8-8"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="M6 6l12 12"/>',
    "minus": '<path d="M5 12h14"/>',
    "building": '<path d="M3 21h18"/><path d="M5 21V6l7-3 7 3v15"/>'
                '<path d="M9 9h.01M15 9h.01M9 13h.01M15 13h.01M11 21v-4h2v4"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "sparkle": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>'
               '<path d="M19 4.5v3M17.5 6h3" />',
    "download": '<path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>',
    "print": '<path d="M6 9V3h12v6"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
             '<rect x="6" y="13" width="12" height="8" rx="1"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.85"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
}


def _icon(name: str, cls: str = "") -> str:
    inner = _ICONS.get(name, "")
    c = f" class='{cls}'" if cls else ""
    return (
        f"<svg{c} viewBox='0 0 24 24' fill='none' stroke='currentColor' "
        f"stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round' "
        f"aria-hidden='true'>{inner}</svg>"
    )


_STYLE = """
:root{
  --ink:#0F1B33; --ink-2:#14264a; --ink-3:#26406e;
  --gold:#C8A24B; --gold-2:#E4C77B; --gold-deep:#9B7826;
  --paper:#F6F2E9; --paper-2:#FBF9F3; --surface:#ffffff;
  --text:#1B2233; --muted:#5B6478; --faint:#8A93A6;
  --line:#E7E1D3; --line-2:#EEEAE0;
  --won:#1A7F37; --won-bg:#E8F6EC; --won-line:#BFE6C9;
  --lost:#B42318; --lost-bg:#FDECEA; --lost-line:#F4C7C1;
  --other:#5B6478; --other-bg:#EEF0F3; --other-line:#DDE1E8;
  --disposed:#1D4ED8; --disposed-bg:#E7EDFC; --disposed-line:#C7D5F6;
  --pending:#8A5A06; --pending-bg:#FBF0D6; --pending-line:#F0DCA8;
  --unknown:#5B6478; --unknown-bg:#EEF0F3; --unknown-line:#DDE1E8;
  --radius:16px; --radius-sm:11px;
  --shadow-sm:0 1px 2px rgba(15,27,51,.05), 0 2px 5px rgba(15,27,51,.05);
  --shadow:0 10px 28px -14px rgba(15,27,51,.30), 0 3px 8px rgba(15,27,51,.06);
  --shadow-lg:0 28px 64px -28px rgba(15,27,51,.45);
  --maxw:1080px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; color:var(--text); font-size:15px; line-height:1.5;
  font-family:'Inter',-apple-system,'Segoe UI',Roboto,Arial,sans-serif;
  background:
    radial-gradient(1100px 520px at 50% -260px, #ffffff, rgba(255,255,255,0)),
    var(--paper);
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
}
.serif{font-family:'Fraunces','Iowan Old Style','Georgia',serif;}
svg{display:block}
a{color:inherit}

/* ---------- top bar ---------- */
.topbar{position:sticky; top:0; z-index:60; backdrop-filter:saturate(150%) blur(10px);
  background:rgba(13,23,44,.82); border-bottom:1px solid rgba(200,162,75,.28);}
.topbar .inner{max-width:var(--maxw); margin:0 auto; padding:10px 24px;
  display:flex; align-items:center; gap:12px;}
.topbar .tb-name{color:#fff; font-weight:600; font-size:14px; letter-spacing:.01em;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.topbar .tb-sub{color:#b9c2d6; font-size:12px; margin-left:2px;}
.spacer{flex:1}
.mono{display:grid; place-items:center; border-radius:50%; flex:none;
  font-family:'Fraunces',serif; font-weight:600; letter-spacing:.02em; color:var(--ink);
  background:linear-gradient(135deg, var(--gold-2), var(--gold));
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.45);}
.mono-sm{width:30px; height:30px; font-size:13px;}
.mono-lg{width:100px; height:100px; font-size:36px;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.5), 0 0 0 5px rgba(200,162,75,.16),
             0 18px 34px -14px rgba(0,0,0,.65);}
.btn{display:inline-flex; align-items:center; gap:7px; cursor:pointer; font:inherit;
  font-size:13px; font-weight:600; border-radius:10px; padding:8px 13px; transition:.18s;}
.btn svg{width:15px; height:15px;}
.btn-gold{color:var(--ink); background:linear-gradient(180deg, var(--gold-2), var(--gold));
  border:1px solid var(--gold-deep);}
.btn-gold:hover{transform:translateY(-1px); box-shadow:0 8px 18px -8px rgba(200,162,75,.7);}
.btn-ghost{color:#f3e9cf; background:rgba(200,162,75,.12); border:1px solid rgba(200,162,75,.4);}
.btn-ghost:hover{background:rgba(200,162,75,.22);}

/* ---------- hero ---------- */
.hero{position:relative; overflow:hidden; color:#fff;
  background:linear-gradient(135deg,#0b1730 0%, #14264a 52%, #0b1730 100%);
  border-bottom:1px solid rgba(200,162,75,.34);}
.hero::before{content:""; position:absolute; inset:-45% -12% auto -12%; height:150%; pointer-events:none;
  background:radial-gradient(600px 320px at 18% 8%, rgba(200,162,75,.26), transparent 62%),
            radial-gradient(520px 300px at 86% 24%, rgba(120,160,255,.16), transparent 60%);
  animation:drift 20s ease-in-out infinite alternate;}
.hero .watermark{position:absolute; right:-30px; bottom:-44px; width:280px; height:280px;
  color:#fff; opacity:.05; pointer-events:none;}
.hero .inner{position:relative; max-width:var(--maxw); margin:0 auto; padding:46px 24px 56px;
  display:flex; gap:26px; align-items:center;}
.hero .id{min-width:0}
.hero .kicker{font-size:11px; font-weight:700; letter-spacing:.22em; text-transform:uppercase;
  color:var(--gold-2); margin-bottom:10px;}
.hero h1{margin:0; font-weight:600; line-height:1.03; letter-spacing:-.015em;
  font-size:clamp(30px, 5.2vw, 48px);}
.hero .role{margin-top:10px; color:#cdd6ea; font-size:15px;}
.hero .role b{color:#fff; font-weight:600;}
.chips{display:flex; flex-wrap:wrap; gap:8px; margin-top:18px;}
.chip{display:inline-flex; align-items:center; gap:7px; font-size:12.5px; color:#e8ecf6;
  background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.16);
  border-radius:999px; padding:6px 12px;}
.chip svg{width:14px; height:14px; opacity:.85}
.pill-gold{color:#f0dca0; background:rgba(200,162,75,.13); border:1px solid rgba(200,162,75,.4);}
.variants{margin-top:14px; display:flex; flex-wrap:wrap; gap:7px; align-items:center;}
.variants .lbl{font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:#9fb0cf;}

/* ---------- layout ---------- */
main{max-width:var(--maxw); margin:0 auto; padding:0 24px 60px;}
section{margin-top:38px;}
.sec-head{display:flex; align-items:center; gap:12px; margin:0 0 16px;}
.sec-head h2{font-family:'Fraunces',serif; font-weight:600; font-size:23px; margin:0;
  color:var(--ink); letter-spacing:-.01em;}
.sec-head .badge{font-size:12px; color:var(--muted); background:var(--surface);
  border:1px solid var(--line); border-radius:999px; padding:3px 10px; font-weight:600;}
.sec-head .rule{flex:1; height:1px; background:linear-gradient(90deg, var(--line), transparent);}

/* reveal — gated behind .js so the page is fully visible without JavaScript */
.js .reveal{opacity:0; transform:translateY(18px);}
.js .reveal.in{opacity:1; transform:none;
  transition:opacity .6s ease, transform .6s cubic-bezier(.2,.7,.2,1);
  transition-delay:var(--d, 0s);}

/* ---------- stat cards ---------- */
.stats{display:grid; grid-template-columns:repeat(auto-fit, minmax(152px, 1fr)); gap:14px;
  margin-top:-44px; position:relative; z-index:5;}
.stat{position:relative; overflow:hidden; background:var(--surface); border:1px solid var(--line);
  border-radius:var(--radius); padding:18px 16px 16px; box-shadow:var(--shadow);
  transition:transform .25s ease, box-shadow .25s ease;}
.stat:hover{transform:translateY(-5px); box-shadow:var(--shadow-lg);}
.stat::after{content:""; position:absolute; left:0; top:0; height:3px; width:100%;
  background:var(--accent, var(--gold));}
.stat .ic{width:40px; height:40px; border-radius:11px; display:grid; place-items:center;
  color:var(--accent, var(--gold-deep)); background:var(--accent-bg, #f1eee5); margin-bottom:12px;}
.stat .ic svg{width:21px; height:21px;}
.stat .num{font-family:'Fraunces',serif; font-weight:600; font-size:34px; line-height:1;
  color:var(--ink); font-variant-numeric:tabular-nums;}
.stat .lab{margin-top:7px; font-size:11px; font-weight:700; letter-spacing:.05em;
  text-transform:uppercase; color:var(--muted);}

/* ---------- outcome viz ---------- */
.panel{background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
  padding:22px 24px; box-shadow:var(--shadow-sm);}
.viz .vrow{margin-top:20px}
.viz .vrow:first-child{margin-top:0}
.viz .vtop{display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px;}
.viz .vtop .t{font-size:13.5px; font-weight:600; color:var(--text);}
.viz .vtop .n{font-size:12.5px; color:var(--muted);}
.bar{height:13px; border-radius:999px; background:#ECE6D6; overflow:hidden; display:flex;
  box-shadow:inset 0 1px 2px rgba(15,27,51,.07);}
.bar > span{height:100%; width:var(--w); display:block; transition:width 1.1s cubic-bezier(.2,.7,.2,1);}
.js .bar > span{width:0;}
.js .reveal.in .bar > span{width:var(--w);}
.seg-disposed{background:linear-gradient(90deg,#3b6ae0,#1D4ED8);}
.seg-pending{background:linear-gradient(90deg,#e9c168,#C8A24B);}
.seg-unknown{background:#cfd5de;}
.seg-won{background:linear-gradient(90deg,#3fae63,#1A7F37);}
.seg-lost{background:linear-gradient(90deg,#d8584a,#B42318);}
.seg-other{background:#cfd5de;}
.legend{display:flex; flex-wrap:wrap; gap:14px; margin-top:13px;}
.legend span{display:inline-flex; align-items:center; gap:7px; font-size:12.5px; color:var(--muted);}
.dot{width:11px; height:11px; border-radius:3px; display:inline-block;}

/* ---------- AI section ---------- */
.ai{position:relative; overflow:hidden; border:1px solid var(--line); border-radius:var(--radius);
  padding:26px 28px 22px; box-shadow:var(--shadow);
  background:linear-gradient(180deg,#FFFDF7, #ffffff);}
.ai::before{content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
  background:linear-gradient(180deg, var(--gold-2), var(--gold-deep));}
.ai .ai-head{display:flex; align-items:center; gap:11px; margin-bottom:12px;}
.ai .spark{width:38px; height:38px; border-radius:11px; display:grid; place-items:center; flex:none;
  color:var(--gold-deep); background:radial-gradient(circle at 30% 30%, #fbe6bd, #f1d488);}
.ai .spark svg{width:21px; height:21px;}
.ai h2{font-family:'Fraunces',serif; font-weight:600; font-size:21px; margin:0; color:var(--ink);}
.ai-badge{position:relative; overflow:hidden; font-size:10.5px; font-weight:700; letter-spacing:.06em;
  text-transform:uppercase; color:var(--gold-deep); background:#fbf2da;
  border:1px solid #ecd9a4; border-radius:999px; padding:3px 9px; margin-left:2px;}
.ai-badge::after{content:""; position:absolute; inset:0; transform:translateX(-100%);
  background:linear-gradient(110deg, transparent 35%, rgba(255,255,255,.85) 50%, transparent 65%);
  animation:shimmer 3.4s ease-in-out infinite;}
.ai-body p{margin:0 0 13px; line-height:1.7; font-size:15px; color:#283044;
  text-align:left;}
.ai-body p:first-child{font-size:15.5px;}
.ai-body p:last-child{margin-bottom:0;}
.ai-note{margin:16px 0 0; padding-top:14px; border-top:1px dashed var(--line);
  color:var(--faint); font-size:12px; line-height:1.55;}

/* ---------- toolbar ---------- */
.toolbar{display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-bottom:18px;}
.search{position:relative; flex:1; min-width:230px;}
.search svg{position:absolute; left:13px; top:50%; transform:translateY(-50%);
  width:16px; height:16px; color:var(--faint);}
.search input{width:100%; padding:11px 14px 11px 38px; font:inherit; font-size:14px; color:var(--text);
  border:1px solid var(--line); border-radius:11px; background:#fff; box-shadow:var(--shadow-sm);
  transition:.18s;}
.search input::placeholder{color:var(--faint);}
.search input:focus{outline:none; border-color:var(--gold);
  box-shadow:0 0 0 3px rgba(200,162,75,.2);}
.filters{display:flex; flex-wrap:wrap; gap:8px;}
.fchip{cursor:pointer; user-select:none; border:1px solid var(--line); background:#fff;
  color:var(--muted); padding:8px 13px; border-radius:999px; font-size:13px; font-weight:600;
  transition:.16s; display:inline-flex; align-items:center; gap:6px;}
.fchip:hover{border-color:var(--gold); color:var(--ink);}
.fchip.active{background:var(--ink); color:#fff; border-color:var(--ink);}
.fchip .c{opacity:.6; font-variant-numeric:tabular-nums;}
.fchip.active .c{opacity:.8;}

/* ---------- case cards ---------- */
.cases{display:flex; flex-direction:column; gap:14px;}
.case{position:relative; overflow:hidden; background:var(--surface); border:1px solid var(--line);
  border-radius:var(--radius); padding:18px 20px 18px 25px; box-shadow:var(--shadow-sm);
  transition:transform .2s ease, box-shadow .2s ease, border-color .2s ease;}
.case::before{content:""; position:absolute; left:0; top:0; bottom:0; width:5px; background:var(--accent, var(--gold));}
.case:hover{transform:translateY(-2px); box-shadow:var(--shadow); border-color:var(--line-2);}
.case[data-outcome=won]{--accent:var(--won);}
.case[data-outcome=lost]{--accent:var(--lost);}
.case[data-outcome=other]{--accent:var(--gold);}
.case.is-hidden{display:none;}
.chead{display:flex; align-items:flex-start; gap:12px; flex-wrap:wrap;}
.chead .cno{font-weight:700; font-size:15.5px; color:var(--ink); letter-spacing:.005em;}
.chead .ctype{font-size:12px; color:var(--faint); margin-top:3px;}
.chead .right{margin-left:auto; display:flex; align-items:center; gap:9px; flex-wrap:wrap; justify-content:flex-end;}
.decided{font-size:12.5px; color:var(--muted); display:inline-flex; align-items:center; gap:5px; white-space:nowrap;}
.decided svg{width:14px; height:14px; color:var(--faint);}
.parties{display:flex; align-items:center; gap:16px; margin:15px 0 4px; flex-wrap:wrap;}
.party{flex:1; min-width:160px;}
.party .role{font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
  color:var(--faint); margin-bottom:3px;}
.party .nm{font-size:15.5px; font-weight:600; color:var(--text); line-height:1.32;}
.vs{flex:none; width:36px; height:36px; border-radius:50%; display:grid; place-items:center;
  background:var(--paper-2); border:1px solid var(--line);
  font-family:'Fraunces',serif; font-style:italic; color:var(--gold-deep); font-size:13px;}
.metas{display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;}
.meta{display:inline-flex; align-items:center; gap:7px; font-size:12.5px; color:var(--muted);
  background:var(--paper-2); border:1px solid var(--line-2); border-radius:9px; padding:5px 11px; max-width:100%;}
.meta svg{width:14px; height:14px; color:var(--gold-deep); flex:none;}
.meta span{overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
.cfoot{display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-top:15px;
  padding-top:14px; border-top:1px dashed var(--line);}
.coadv{font-size:12.5px; color:var(--muted);}
.coadv b{color:var(--text); font-weight:600;}
.orders{display:flex; flex-wrap:wrap; gap:8px; margin-left:auto;}
.order-btn{display:inline-flex; align-items:center; gap:7px; font-size:12.5px; font-weight:600;
  color:var(--ink); text-decoration:none; padding:7px 12px; border-radius:9px;
  background:linear-gradient(180deg,#FDF6E5,#F7ECCD); border:1px solid var(--gold);
  box-shadow:var(--shadow-sm); transition:.18s;}
.order-btn:hover{transform:translateY(-1px); background:linear-gradient(180deg,#FBEEC8,#F2E1B2);
  box-shadow:0 8px 16px -8px rgba(200,162,75,.6);}
.order-btn svg{width:14px; height:14px; color:var(--gold-deep);}
.order-none{display:inline-flex; align-items:center; gap:6px; font-size:12px; color:var(--faint);
  background:var(--paper-2); border:1px solid var(--line-2); border-radius:9px; padding:6px 11px;}

/* tags */
.tag{display:inline-flex; align-items:center; gap:5px; padding:3px 10px; border-radius:999px;
  font-size:11.5px; font-weight:700; letter-spacing:.02em; border:1px solid transparent; white-space:nowrap;}
.tag svg{width:12px; height:12px;}
.tag.won{color:var(--won); background:var(--won-bg); border-color:var(--won-line);}
.tag.lost{color:var(--lost); background:var(--lost-bg); border-color:var(--lost-line);}
.tag.other{color:var(--other); background:var(--other-bg); border-color:var(--other-line);}
.tag.disposed{color:var(--disposed); background:var(--disposed-bg); border-color:var(--disposed-line);}
.tag.pending{color:var(--pending); background:var(--pending-bg); border-color:var(--pending-line);}
.tag.unknown{color:var(--unknown); background:var(--unknown-bg); border-color:var(--unknown-line);}

.no-results{display:none; text-align:center; color:var(--muted); padding:34px;
  border:1px dashed var(--line); border-radius:var(--radius); background:var(--paper-2);}

/* ---------- co-advocates ---------- */
.coadv-list{display:flex; flex-direction:column; gap:13px;}
.coadv-row .lab{display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px;}
.coadv-row .nm{font-weight:600; color:var(--text); font-size:13.5px;}
.coadv-row .ct{color:var(--muted); font-size:12px;}
.track{height:9px; border-radius:999px; background:#ECE6D6; overflow:hidden;}
.track > span{display:block; height:100%; width:var(--w); border-radius:999px;
  background:linear-gradient(90deg, var(--gold-2), var(--gold-deep)); transition:width 1s cubic-bezier(.2,.7,.2,1);}
.js .track > span{width:0;}
.js .reveal.in .track > span{width:var(--w);}

/* ---------- empty state ---------- */
.empty{margin-top:40px; text-align:center; background:var(--surface); border:1px solid var(--line);
  border-radius:var(--radius); padding:48px 30px; box-shadow:var(--shadow-sm);}
.empty .ic{width:56px; height:56px; border-radius:50%; display:grid; place-items:center; margin:0 auto 16px;
  color:var(--gold-deep); background:#f5edd7;}
.empty .ic svg{width:26px; height:26px;}
.empty h2{font-family:'Fraunces',serif; margin:0 0 6px; color:var(--ink);}
.empty p{margin:0; color:var(--muted);}

/* ---------- footer ---------- */
footer{max-width:var(--maxw); margin:34px auto 0; padding:24px; text-align:center;
  border-top:1px solid var(--line); color:var(--faint); font-size:12.5px; line-height:1.7;}
footer .brand{color:var(--muted); font-weight:600;}

/* ---------- responsive ---------- */
@media (max-width:640px){
  .hero .inner{flex-direction:column; text-align:center; align-items:center;}
  .chips, .variants{justify-content:center;}
  .parties{flex-direction:column; align-items:stretch;}
  .vs{align-self:center;}
  .chead .right{margin-left:0;}
  .orders{margin-left:0;}
  .ai{padding:22px 18px 18px;}
  .ai-body p{font-size:14px; line-height:1.65;}
  .ai-body p:first-child{font-size:14.5px;}
}

/* ---------- reduced motion ---------- */
@media (prefers-reduced-motion: reduce){
  *{animation:none !important; transition:none !important;}
  .reveal{opacity:1 !important; transform:none !important;}
  .bar > span, .track > span{width:var(--w) !important;}
  .hero::before{animation:none !important;}
}

/* ---------- print / PDF ---------- */
@page{margin:14mm;}
@media print{
  /* Core fix: browsers strip background colours/gradients in print/PDF unless
     an element opts in. Force every accent (bars, tags, dots, stripes, buttons)
     to render — print-color-adjust is inherited, so ::before/::after stripes are
     covered via their host elements, and Chrome prints them even without the
     dialog's "Background graphics" ticked. */
  *{-webkit-print-color-adjust:exact !important; print-color-adjust:exact !important;}

  /* drop interactive-only chrome and on-screen motion */
  .topbar, .toolbar, .btn, .hero::before, .hero .watermark{display:none !important;}
  .reveal{opacity:1 !important; transform:none !important;}
  .bar > span, .track > span{width:var(--w) !important;}
  .case.is-hidden{display:block !important;}
  html, body{background:#fff !important;}
  main{padding-top:18px;}

  /* lighten the dark navy hero for paper: navy ink on white, keep gold avatar */
  .hero{background:#fff !important; color:var(--ink) !important;
    border-bottom:2px solid var(--gold); overflow:visible;}
  .hero .inner{padding:24px 24px 26px;}
  .hero .kicker{color:var(--gold-deep) !important;}
  .hero .role{color:var(--muted) !important;}
  .hero .role b{color:var(--ink) !important;}
  .hero .chip{color:var(--muted) !important; background:#fff !important;
    border:1px solid var(--line) !important;}
  .hero .pill-gold{color:var(--gold-deep) !important; background:#FBF2DA !important;
    border:1px solid #ECD9A4 !important;}
  .variants .lbl{color:var(--muted) !important;}
  .mono-lg{box-shadow:inset 0 0 0 1px rgba(255,255,255,.5),
    0 0 0 4px rgba(200,162,75,.18) !important;}

  /* sit stat cards below the now-light hero instead of overlapping it */
  .stats{margin-top:18px;}

  /* tidy ink: flatten shadows, keep borders/accents */
  .stat, .case, .ai, .panel, .order-btn, .search input{box-shadow:none !important;}

  /* keep blocks intact across page breaks */
  .sec-head{break-after:avoid; page-break-after:avoid;}
  .hero, .stat, .case, .ai, .panel, .coadv-row{break-inside:avoid; page-break-inside:avoid;}
}

@keyframes drift{from{transform:translate3d(-2%,-1%,0) scale(1);}
                 to{transform:translate3d(3%,2%,0) scale(1.08);}}
@keyframes shimmer{0%{transform:translateX(-100%);} 55%,100%{transform:translateX(100%);}}
"""


_SCRIPT = """
<script>
(function(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function countUp(el){
    var target = parseInt(el.getAttribute('data-count') || '0', 10);
    if(reduce || !target){ el.textContent = String(target || 0); return; }
    var dur = 950, start = null;
    function step(ts){
      if(!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(eased * target);
      if(p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  var revealEls = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
  function activate(el){
    el.classList.add('in');
    Array.prototype.forEach.call(el.querySelectorAll('[data-count]'), countUp);
  }
  if('IntersectionObserver' in window){
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if(e.isIntersecting){ activate(e.target); io.unobserve(e.target); }
      });
    }, { threshold: 0.16, rootMargin: '0px 0px -40px 0px' });
    revealEls.forEach(function(el){ io.observe(el); });
  } else {
    revealEls.forEach(activate);
  }

  // ----- case filtering -----
  var search = document.getElementById('caseSearch');
  var chips  = Array.prototype.slice.call(document.querySelectorAll('.fchip'));
  var cards  = Array.prototype.slice.call(document.querySelectorAll('.case'));
  var noRes  = document.getElementById('noResults');
  var active = 'all';

  function matchFilter(card){
    if(active === 'all') return true;
    if(active === 'disposed' || active === 'pending') return card.getAttribute('data-status') === active;
    return card.getAttribute('data-outcome') === active; // won / lost
  }
  function apply(){
    var q = (search && search.value || '').trim().toLowerCase();
    var shown = 0;
    cards.forEach(function(c){
      var ok = matchFilter(c) && (!q || (c.getAttribute('data-text') || '').indexOf(q) !== -1);
      c.classList.toggle('is-hidden', !ok);
      if(ok) shown++;
    });
    if(noRes) noRes.style.display = shown ? 'none' : 'block';
  }
  chips.forEach(function(ch){
    ch.addEventListener('click', function(){
      chips.forEach(function(x){ x.classList.remove('active'); });
      ch.classList.add('active');
      active = ch.getAttribute('data-filter') || 'all';
      apply();
    });
  });
  if(search) search.addEventListener('input', apply);

  // ----- print -----
  Array.prototype.forEach.call(document.querySelectorAll('[data-print]'), function(b){
    b.addEventListener('click', function(){ window.print(); });
  });
})();
</script>
"""


# ---- rendering components -------------------------------------------------


def _topbar(advocate_name: str) -> str:
    return (
        "<div class='topbar'><div class='inner'>"
        f"<div class='mono mono-sm'>{_e(_initials(advocate_name))}</div>"
        f"<div class='tb-name'>{_e(advocate_name)}</div>"
        "<div class='spacer'></div>"
        f"<button class='btn btn-ghost' data-print type='button'>{_icon('print')} Save as PDF</button>"
        "</div></div>"
    )


def _hero(advocate_name: str, matches: list, num_cases: int, generated: str) -> str:
    variants = ""
    if matches and len(matches) > 1:
        pills = "".join(
            f"<span class='chip pill-gold'>{_e(a.name)}</span>" for a in matches
        )
        variants = (
            "<div class='variants'><span class='lbl'>Also filed as</span>" + pills + "</div>"
        )
    variant_chip = ""
    if len(matches) > 1:
        variant_chip = f"<span class='chip'>{_icon('users')}{len(matches)} name variants</span>"
    meta = (
        f"<span class='chip'>{_icon('layers')}{num_cases} case(s)</span>"
        f"{variant_chip}"
        f"<span class='chip'>{_icon('calendar')}Generated {_e(generated)}</span>"
    )
    return (
        "<header class='hero'>"
        f"<div class='watermark'>{_icon('scale')}</div>"
        "<div class='inner'>"
        f"<div class='mono mono-lg'>{_e(_initials(advocate_name))}</div>"
        "<div class='id'>"
        "<div class='kicker'>Advocate Profile</div>"
        f"<h1 class='serif'>{_e(advocate_name)}</h1>"
        f"<div class='role'>Practising before <b>{_e(config.DISTRICT_NAME)}</b></div>"
        f"<div class='chips'>{meta}</div>"
        f"{variants}"
        "</div></div></header>"
    )


# Stat card spec: label, stat key, icon, accent colour, accent tint.
_STAT_SPEC = [
    ("Total cases", "total", "layers", "#9B7826", "#F3EBD6"),
    ("Disposed", "disposed", "gavel", "#1D4ED8", "#E7EDFC"),
    ("Pending", "pending", "clock", "#8A5A06", "#FBF0D6"),
    ("Granted", "allowed_granted", "check", "#1A7F37", "#E8F6EC"),
    ("Dismissed", "rejected_dismissed", "x", "#B42318", "#FDECEA"),
    ("Courts / establishments", "courts_establishments", "building", "#5B54C9", "#ECEBFA"),
]


def _stat_cards(stats: dict) -> str:
    cards = []
    for i, (label, key, icon, accent, tint) in enumerate(_STAT_SPEC):
        cards.append(
            f"<div class='stat reveal' style='--d:{i * 0.05:.2f}s; --accent:{accent}; --accent-bg:{tint}'>"
            f"<div class='ic'>{_icon(icon)}</div>"
            f"<div class='num' data-count='{int(stats[key])}'>{int(stats[key])}</div>"
            f"<div class='lab'>{_e(label)}</div></div>"
        )
    return f"<div class='stats'>{''.join(cards)}</div>"


def _outcome_viz(stats: dict) -> str:
    total = stats["total"]
    if not total:
        return ""

    def pct(v: int) -> str:
        return f"{(v / total * 100):.1f}"

    unknown = max(total - stats["disposed"] - stats["pending"], 0)
    disp_segs = (
        f"<span class='seg-disposed' style='--w:{pct(stats['disposed'])}%'></span>"
        f"<span class='seg-pending' style='--w:{pct(stats['pending'])}%'></span>"
        f"<span class='seg-unknown' style='--w:{pct(unknown)}%'></span>"
    )
    out_segs = (
        f"<span class='seg-won' style='--w:{pct(stats['allowed_granted'])}%'></span>"
        f"<span class='seg-lost' style='--w:{pct(stats['rejected_dismissed'])}%'></span>"
        f"<span class='seg-other' style='--w:{pct(stats['other_unknown'])}%'></span>"
    )
    return (
        "<section class='reveal'>"
        "<div class='sec-head'><h2>At a glance</h2><div class='rule'></div></div>"
        "<div class='panel viz reveal'>"
        # progress row 1 — lifecycle
        "<div class='vrow'>"
        f"<div class='vtop'><span class='t'>Case lifecycle</span>"
        f"<span class='n'>{stats['disposed']} disposed &middot; {stats['pending']} pending"
        f"{(' &middot; ' + str(unknown) + ' unknown') if unknown else ''}</span></div>"
        f"<div class='bar'>{disp_segs}</div>"
        "<div class='legend'>"
        "<span><i class='dot' style='background:#1D4ED8'></i>Disposed</span>"
        "<span><i class='dot' style='background:#C8A24B'></i>Pending</span>"
        + ("<span><i class='dot' style='background:#cfd5de'></i>Unknown</span>" if unknown else "")
        + "</div></div>"
        # progress row 2 — outcomes
        "<div class='vrow'>"
        f"<div class='vtop'><span class='t'>Outcome mix</span>"
        f"<span class='n'>{stats['allowed_granted']} allowed &middot; "
        f"{stats['rejected_dismissed']} rejected &middot; {stats['other_unknown']} other</span></div>"
        f"<div class='bar'>{out_segs}</div>"
        "<div class='legend'>"
        "<span><i class='dot' style='background:#1A7F37'></i>Granted</span>"
        "<span><i class='dot' style='background:#B42318'></i>Dismissed</span>"
        "<span><i class='dot' style='background:#cfd5de'></i>Other / Unknown</span>"
        "</div></div>"
        "<p class='ai-note' style='border-top:0; padding-top:14px'>Outcomes are derived from each "
        "case&rsquo;s <b>Nature of Disposal</b>, which reflects the case result &mdash; not necessarily "
        "a win for this advocate, who may represent either party.</p>"
        "</div></section>"
    )


def _ai_section(ai_text: str) -> str:
    """Render the AI narrative as a styled section. Splits on blank lines into
    paragraphs and HTML-escapes the model output."""
    paras = []
    for p in re.split(r"\n\s*\n", ai_text.strip()):
        p = p.strip()
        if p:
            paras.append("<p>" + _e(p).replace("\n", "<br>") + "</p>")
    if not paras:
        return ""
    return (
        "<section class='reveal'>"
        "<div class='ai'>"
        "<div class='ai-head'>"
        f"<div class='spark'>{_icon('sparkle')}</div>"
        "<h2 class='serif'>AI Profile</h2>"
        "<span class='ai-badge'>AI generated</span>"
        "</div>"
        f"<div class='ai-body'>{''.join(paras)}</div>"
        "<p class='ai-note'>AI-generated from the case data below and may contain errors. "
        "Outcomes reflect each case&rsquo;s nature of disposal, not necessarily a win for this advocate.</p>"
        "</div></section>"
    )


def _orders_buttons(orders) -> str:
    if not orders:
        return ""
    bits = []
    for o in orders:
        label = _e(f"{o.label or 'Order'} ({o.order_date})") if o.order_date else _e(o.label or "Order")
        href = _pdf_href(o.pdf_local_path) if o.downloaded else None
        if href:
            bits.append(
                f"<a class='order-btn' href='{_e(href)}' target='_blank' rel='noopener'>"
                f"{_icon('download')}{label}</a>"
            )
        else:
            bits.append(f"<span class='order-none'>{_icon('print')}{label}</span>")
    return f"<div class='orders'>{''.join(bits)}</div>"


_OUTCOME_ICON = {"won": "check", "lost": "x", "other": "minus"}
_STATUS_ICON = {"disposed": "gavel", "pending": "clock", "unknown": "clock"}


def _case_card(x: dict, idx: int) -> str:
    c = x["case"]
    oc = _outcome_class(c.nature_of_disposal)
    disp = _disposition(c)
    disp_key = disp.lower()

    status_tag = f"<span class='tag {disp_key}'>{_icon(_STATUS_ICON.get(disp_key, 'clock'))}{_e(disp)}</span>"
    decided = (
        f"<span class='decided'>{_icon('calendar')}{_e(c.decision_date)}</span>"
        if c.decision_date else ""
    )
    disposal_tag = (
        f"<span class='tag {oc}'>{_icon(_OUTCOME_ICON[oc])}{_e(c.nature_of_disposal)}</span>"
        if c.nature_of_disposal else ""
    )
    ctype = f"<div class='ctype'>{_e(c.case_type)}</div>" if c.case_type else ""

    metas = []
    if c.establishment:
        metas.append(f"<span class='meta'>{_icon('building')}<span>{_e(c.establishment)}</span></span>")
    if c.judge:
        metas.append(f"<span class='meta'>{_icon('gavel')}<span>{_e(c.judge)}</span></span>")
    if disposal_tag:
        metas.append(disposal_tag)
    metas_html = f"<div class='metas'>{''.join(metas)}</div>" if metas else ""

    co = x["co_advocates"]
    co_html = (
        f"<div class='coadv'>Alongside <b>{_e(', '.join(co))}</b></div>"
        if co else "<div class='coadv'>Sole advocate on record</div>"
    )
    orders_html = _orders_buttons(x["orders"])
    foot = (
        f"<div class='cfoot'>{co_html}{orders_html}</div>"
        if (co or x["orders"]) else ""
    )

    search_text = " ".join(
        str(v) for v in (
            c.case_number_full, c.case_type, c.petitioner, c.respondent,
            c.establishment, c.judge, c.nature_of_disposal, disp, c.decision_date,
            *co,
        ) if v
    ).lower()

    return (
        f"<article class='case reveal' data-status='{disp_key}' data-outcome='{oc}' "
        f"data-text='{_e(search_text)}' style='--d:{min(idx * 0.04, 0.4):.2f}s'>"
        "<div class='chead'>"
        f"<div><div class='cno'>{_e(c.case_number_full)}</div>{ctype}</div>"
        f"<div class='right'>{status_tag}{decided}</div>"
        "</div>"
        "<div class='parties'>"
        f"<div class='party'><div class='role'>Petitioner</div>"
        f"<div class='nm'>{_e(c.petitioner) or '&mdash;'}</div></div>"
        "<div class='vs'>vs</div>"
        f"<div class='party'><div class='role'>Respondent</div>"
        f"<div class='nm'>{_e(c.respondent) or '&mdash;'}</div></div>"
        "</div>"
        f"{metas_html}{foot}"
        "</article>"
    )


def _cases_section(cases: list[dict]) -> str:
    if not cases:
        return (
            "<section class='reveal'>"
            "<div class='sec-head'><h2>Cases</h2><div class='rule'></div></div>"
            "<div class='no-results' style='display:block'>No cases found for this advocate "
            "in the database.</div></section>"
        )

    # Filter chips with live counts.
    n_total = len(cases)
    n_disp = sum(1 for x in cases if _disposition(x["case"]) == "Disposed")
    n_pend = sum(1 for x in cases if _disposition(x["case"]) == "Pending")
    n_won = sum(1 for x in cases if _outcome_class(x["case"].nature_of_disposal) == "won")
    n_lost = sum(1 for x in cases if _outcome_class(x["case"].nature_of_disposal) == "lost")
    chip_spec = [
        ("all", "All", n_total),
        ("disposed", "Disposed", n_disp),
        ("pending", "Pending", n_pend),
        ("won", "Granted", n_won),
        ("lost", "Dismissed", n_lost),
    ]
    chips = "".join(
        f"<button type='button' class='fchip{' active' if key == 'all' else ''}' "
        f"data-filter='{key}'>{_e(label)} <span class='c'>{n}</span></button>"
        for key, label, n in chip_spec
    )
    toolbar = (
        "<div class='toolbar'>"
        "<div class='search'>" + _icon("search") +
        "<input id='caseSearch' type='search' autocomplete='off' "
        "placeholder='Search cases, parties, courts, judges&hellip;'></div>"
        f"<div class='filters'>{chips}</div>"
        "</div>"
    )
    cards = "".join(_case_card(x, i) for i, x in enumerate(cases))
    return (
        "<section class='reveal'>"
        f"<div class='sec-head'><h2>Cases</h2><span class='badge'>{n_total}</span><div class='rule'></div></div>"
        f"{toolbar}"
        f"<div class='cases'>{cards}</div>"
        "<div class='no-results' id='noResults'>No cases match your search.</div>"
        "</section>"
    )


def _co_advocate_section(cases: list[dict]) -> str:
    counts: dict[str, int] = {}
    for x in cases:
        for name in x["co_advocates"]:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return ""
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top = max(n for _, n in ordered)
    rows = "".join(
        "<div class='coadv-row'>"
        f"<div class='lab'><span class='nm'>{_e(name)}</span>"
        f"<span class='ct'>{n} shared case{'s' if n != 1 else ''}</span></div>"
        f"<div class='track'><span style='--w:{(n / top * 100):.1f}%'></span></div>"
        "</div>"
        for name, n in ordered
    )
    return (
        "<section class='reveal'>"
        "<div class='sec-head'><h2>Frequent co-advocates</h2>"
        f"<span class='badge'>{len(ordered)}</span><div class='rule'></div></div>"
        f"<div class='panel coadv-list reveal'>{rows}</div>"
        "</section>"
    )


def render_advocate_summary(session, advocate_name: str, *, ai_text: str | None = None) -> str:
    """Return a self-contained HTML page summarizing one advocate.

    Pass ``ai_text`` (e.g. the cached ``Advocate.ai_summary``) to reuse a
    previously generated narrative instead of calling OpenAI again; leave it
    ``None`` (the CLI path) to generate on the fly."""
    matches = _matching_advocates(session, advocate_name)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not matches:
        body = (
            _hero(advocate_name, [], 0, generated)
            + "<main><div class='empty'>"
            + f"<div class='ic'>{_icon('search')}</div>"
            + "<h2 class='serif'>No records found</h2>"
            + f"<p>No matching advocate for &ldquo;{_e(advocate_name)}&rdquo; in "
            + f"{_e(config.DISTRICT_NAME)} yet.</p></div></main>"
        )
    else:
        cases = _load_cases(session, [a.id for a in matches])
        stats = _compute_stats(cases)
        if ai_text is None:
            ai_text = ai_summary.generate_advocate_summary(
                advocate_name, stats, _case_digests(cases),
                aggregates=_ai_aggregates(cases),
            )
        ai_html = _ai_section(ai_text) if ai_text else ""
        body = (
            _hero(advocate_name, matches, len(cases), generated)
            + "<main>"
            + _stat_cards(stats)
            + _outcome_viz(stats)
            + ai_html
            + _cases_section(cases)
            + _co_advocate_section(cases)
            + "</main>"
            + "<footer>"
            + "<div class='brand'>Generated by ecourts-scraper</div>"
            + f"Compiled {_e(generated)} from public eCourts district-court records "
            + f"({_e(config.DISTRICT_NAME)}). Coverage is limited to the configured district. "
            + "This profile is auto-generated and intended for verification before sharing."
            + "</footer>"
        )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Advocate profile &mdash; {_e(advocate_name)}</title>"
        # Mark JS available *before* body paints so reveal animations enable without
        # a flash of hidden content; without JS the .js-gated rules never apply and
        # the full report stays visible.
        "<script>document.documentElement.className+=' js';</script>"
        f"{_FONTS_LINK}<style>{_STYLE}</style></head><body>"
        f"{_topbar(advocate_name)}{body}{_SCRIPT}"
        "</body></html>"
    )


def write_advocate_summary(advocate_name: str) -> Path:
    """Render and write the summary to data/<slug>_summary.html. Returns its path."""
    with Session() as session:
        out_html = render_advocate_summary(session, advocate_name)
    path = config.DATA_DIR / f"{_slug(advocate_name)}_summary.html"
    path.write_text(out_html, encoding="utf-8")
    return path


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print('usage: python src/report_html.py "<advocate name>"')
        raise SystemExit(2)
    name = " ".join(sys.argv[1:])
    path = write_advocate_summary(name)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
