"""Transactional email (Resend) — the "your advocate report is ready" notice.

Best-effort by design: ``send_profile_ready_email`` swallows and logs every error
and returns a bool, so a mail problem (bad key, network, disabled) can never fail
the scrape that triggered it. Named ``mailer`` (not ``email``) to avoid shadowing
Python's stdlib ``email`` package.

The email is link-only: a branded summary of the advocate's portfolio plus a button
back to the live profile (where the existing client-side "Download PDF" lives). No
attachment, so the worker stays light — no headless browser / PDF engine.
"""

from __future__ import annotations

import html
import logging

import config

logger = logging.getLogger("mailer")

# Brand palette (mirrors web/app/globals.css). Inline-styled + table-based markup
# because email clients ignore <style>/external CSS and most modern layout.
_NAVY = "#0f1b33"
_NAVY_3 = "#1f3361"
_GOLD = "#c8a24b"
_GOLD_2 = "#d8b86a"
_INK = "#1a2236"
_MUTED = "#6b7689"
_BG = "#f5f6fb"
_LINE = "#e6e9f0"
_SURFACE = "#ffffff"


def send_profile_ready_email(to_email: str, profile: dict, profile_url: str) -> bool:
    """Email ``to_email`` that the advocate's report is ready. Returns True if a
    send was attempted successfully, False if skipped (disabled/misconfigured) or
    it failed (logged)."""
    if not (config.EMAIL_ENABLED and config.RESEND_API_KEY and to_email):
        return False
    try:
        import resend  # lazy: keep the dep optional when email is disabled

        resend.api_key = config.RESEND_API_KEY
        name = profile.get("name") or "Your advocate"
        resend.Emails.send({
            "from": config.EMAIL_FROM,
            "to": [to_email],
            "subject": f"{name} — case report is ready",
            "html": _render(profile, profile_url),
        })
        logger.info("sent report-ready email to %s", to_email)
        return True
    except Exception:  # noqa: BLE001 - email must never break the job
        logger.exception("failed to send report email to %s", to_email)
        return False


def _stat_cell(label: str, value) -> str:
    return (
        f'<td align="center" style="padding:10px 6px;">'
        f'<div style="font-family:Georgia,\'Times New Roman\',serif;font-size:26px;'
        f'font-weight:700;color:{_NAVY};line-height:1;">{html.escape(str(value))}</div>'
        f'<div style="font-size:11px;letter-spacing:.04em;text-transform:uppercase;'
        f'color:{_MUTED};margin-top:6px;">{html.escape(label)}</div></td>'
    )


def _render(profile: dict, url: str) -> str:
    name = html.escape(profile.get("name") or "Advocate")
    district = html.escape(profile.get("district") or "")
    stats = profile.get("stats") or {}
    cells = [
        _stat_cell("Total", stats.get("total", 0)),
        _stat_cell("Disposed", stats.get("disposed", 0)),
        _stat_cell("Pending", stats.get("pending", 0)),
        _stat_cell("Granted", stats.get("allowed_granted", 0)),
        _stat_cell("Dismissed", stats.get("rejected_dismissed", 0)),
    ]
    stats_row = "".join(cells)

    # First paragraph of the AI narrative, trimmed — a teaser, not the whole thing.
    summary = (profile.get("ai_summary") or "").strip()
    if summary:
        summary = summary.split("\n\n")[0].strip()
        if len(summary) > 420:
            summary = summary[:420].rsplit(" ", 1)[0] + "…"
        summary_block = (
            f'<tr><td style="padding:4px 28px 22px;">'
            f'<div style="font-size:12px;letter-spacing:.05em;text-transform:uppercase;'
            f'color:{_GOLD};font-weight:700;margin-bottom:8px;">Profile summary</div>'
            f'<div style="font-size:14.5px;line-height:1.6;color:{_INK};">{html.escape(summary)}</div>'
            f"</td></tr>"
        )
    else:
        summary_block = ""

    safe_url = html.escape(url, quote=True)

    return f"""\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:28px 14px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:{_SURFACE};border:1px solid {_LINE};border-radius:16px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

        <!-- header band -->
        <tr><td style="background:linear-gradient(135deg,{_NAVY},{_NAVY_3});padding:26px 28px;">
          <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:{_GOLD_2};font-weight:700;">Report ready</div>
          <div style="font-family:Georgia,'Times New Roman',serif;font-size:24px;color:#ffffff;font-weight:700;margin-top:6px;">{name}</div>
          {f'<div style="font-size:13.5px;color:rgba(255,255,255,.72);margin-top:4px;">{district}</div>' if district else ''}
        </td></tr>

        <!-- intro -->
        <tr><td style="padding:22px 28px 6px;">
          <p style="margin:0;font-size:15px;line-height:1.6;color:{_INK};">
            Your requested case portfolio has finished compiling. Here's a quick snapshot —
            open the full report for every case, outcome breakdown, courts and co-advocates.
          </p>
        </td></tr>

        <!-- stats -->
        <tr><td style="padding:14px 16px 6px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="background:#fafbfe;border:1px solid {_LINE};border-radius:12px;">
            <tr>{stats_row}</tr>
          </table>
        </td></tr>

        {summary_block}

        <!-- CTA button (bulletproof) -->
        <tr><td align="center" style="padding:6px 28px 28px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td align="center" style="border-radius:12px;background:linear-gradient(180deg,{_GOLD_2},{_GOLD});">
              <a href="{safe_url}" target="_blank"
                 style="display:inline-block;padding:13px 26px;font-size:15px;font-weight:700;
                        color:#2a1f06;text-decoration:none;border-radius:12px;">
                View full report &rarr;
              </a>
            </td>
          </tr></table>
        </td></tr>

        <!-- footer -->
        <tr><td style="padding:18px 28px;border-top:1px solid {_LINE};">
          <p style="margin:0;font-size:12px;line-height:1.6;color:{_MUTED};">
            You asked to be emailed when this report was ready. The link opens the live profile,
            where you can download the full PDF. Auto-generated from public eCourts district-court
            records — verify independently before relying on it.
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
