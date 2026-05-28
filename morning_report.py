#!/usr/bin/env python3
"""
morning_report.py  ─  MAYASAHOURY/maya-life-os
════════════════════════════════════════════════════════════════════
Maya's personal life OS — Telegram intelligence reports.

This repo (maya-life-os) MONITORS aura-glossy. It does NOT live
inside aura-glossy. Keep them separate.

PART 1  Full Morning Report  →  08:00 Jerusalem  (once per day)
PART 2  Daytime Reminders   →  Short & clean, only when useful

MODES (auto-detected from Jerusalem clock):
  08:00  morning          Full premium dashboard report
  09:00  email_check      Silent — only fires if important email arrived
  12:30  midday           Short nudge before study block
  13:00  study_reminder   Study session starts now
  16:00  afternoon        Short afternoon check-in
  20:00  apple            Apple 90-min reminder
  21:30  evening          Evening wrap

REPOS:
  SITE_REPO       MAYASAHOURY/aura-glossy    ← monitored (the website)
  AUTOMATION_REPO MAYASAHOURY/maya-life-os   ← this repo (the automation)

SECRETS (set in maya-life-os repo settings):
  TELEGRAM_BOT_TOKEN  TELEGRAM_CHAT_ID
  GMAIL_ADDRESS       GMAIL_APP_PASSWORD
  MOODLE_USERNAME     MOODLE_PASSWORD
  NETLIFY_TOKEN       (optional)
  GITHUB_TOKEN        (optional — needed only if repos are private)
════════════════════════════════════════════════════════════════════
"""

import os, re, sys, email, imaplib
from datetime import datetime, timedelta
from email.header import decode_header

import pytz, requests


# ════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT   = os.environ["TELEGRAM_CHAT_ID"]
GMAIL_ADDRESS   = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_PASS      = os.environ.get("GMAIL_APP_PASSWORD", "")
MOODLE_URL      = "https://moodle.kinneret.ac.il"
MOODLE_USER     = os.environ.get("MOODLE_USERNAME", "")
MOODLE_PASS     = os.environ.get("MOODLE_PASSWORD", "")
NETLIFY_TOKEN   = os.environ.get("NETLIFY_TOKEN", "")
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")

# The website/project being monitored
SITE_REPO       = "MAYASAHOURY/aura-glossy"
WEBSITE_URL     = "https://auraglossy.com"
LOGIN_URL       = "https://auraglossy.com"   # update if login lives on a sub-path

# This automation repo (for workflow self-check)
AUTOMATION_REPO = "MAYASAHOURY/maya-life-os"

JERUSALEM_TZ    = pytz.timezone("Asia/Jerusalem")

PRIORITY_SENDERS = [
    "imerit", "telus", "transperfect", "mercor",
    "github", "google", "kinneret", "moodle",
]
URGENT_KEYWORDS = [
    "urgent", "interview", "offer", "security", "alert",
    "verify", "assignment", "deadline", "action required",
]
CAREER_PLATFORMS = {          # overwritten live when matching email found
    "iMerit":        "Waiting for assignments",
    "TELUS Digital": "In review",
    "TransPerfect":  "Applied",
    "Mercor":        "Pending",
}
SENDER_ICONS = {
    "google":"🔴","github":"⚫","imerit":"🔵",
    "telus":"🟡","transperfect":"🟠","mercor":"🟤",
    "moodle":"🟣","kinneret":"🟣",
}

DEFAULT_TASKS = [
    {"n":1,"task":"Deep Learning Project 1 – Object Detection","priority":"high"},
    {"n":2,"task":"SIS Engineering Forum Response",            "priority":"high"},
    {"n":3,"task":"Aura Glossy – Build Stable AI Income",      "priority":"medium"},
]
DEFAULT_STUDY = [
    {"time":"13:00 – 14:00","subject":"Deep Learning",      "topic":"Project 1  (Object Detection)"},
    {"time":"14:15 – 15:15","subject":"Systems Engineering","topic":"Review & Practice"},
    {"time":"15:30 – 16:30","subject":"Coding Practice",    "topic":"Problem Solving"},
]
STUDY_FOCUS = "Deep Learning Project 1  (due 30/05)"
STUDY_HOURS = 2.0

# ── Weekly university timetable (Kinneret College) ────────────────
# Keys: 0=Monday … 6=Sunday  (Python weekday())
WEEKLY_SCHEDULE = {
    0: [  # Monday
        {"time": "08:00", "course": "Algorithms",            "type": "שיעור"},
        {"time": "10:00", "course": "Algorithms",            "type": "תרגול"},
        {"time": "12:00", "course": "Engineering Economics", "type": "שיעור"},
        {"time": "16:30", "course": "Deep Learning",         "type": "שיעור"},
    ],
    1: [  # Tuesday
        {"time": "10:00", "course": "Engineering Economics", "type": "תרגול"},
        {"time": "13:00", "course": "HCI (Human-Computer Interaction)", "type": "שיעור"},
    ],
    2: [  # Wednesday
        {"time": "16:00", "course": "IoT",                   "type": "שיעור"},
    ],
    3: [  # Thursday
        {"time": "10:00", "course": "SIS Engineering",       "type": "שיעור"},
    ],
    4: [],  # Friday   — free
    5: [],  # Saturday — free
    6: [],  # Sunday   — free
}


# ════════════════════════════════════════════════════════════════════
# TIMEZONE + MODE
# ════════════════════════════════════════════════════════════════════

def now_j() -> datetime:
    return datetime.now(JERUSALEM_TZ)

def detect_mode(now: datetime = None):
    now = now or now_j()
    h, m = now.hour, now.minute
    if h == 8  and m < 20:        return "morning"
    if h == 9  and m < 20:        return "email_check"
    if h == 12 and 25 <= m < 50:  return "midday"
    if h == 13 and m < 20:        return "study_reminder"
    if h == 16 and m < 20:        return "afternoon"
    if h == 20 and m < 20:        return "apple"
    if h == 21 and 25 <= m < 55:  return "evening"
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return os.environ.get("REPORT_MODE", "morning")
    return None   # wrong-DST duplicate — exit silently

def _greeting(now: datetime) -> str:
    h = now.hour
    if h < 12: return "Good morning"
    if h < 18: return "Good afternoon"
    return "Good evening"

def _mins_until(h: int, m: int, now: datetime) -> int:
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now: t += timedelta(days=1)
    return int((t - now).total_seconds() / 60)


# ════════════════════════════════════════════════════════════════════
# DATA COLLECTORS
# ════════════════════════════════════════════════════════════════════

def check_url(url: str) -> tuple:
    """Live HTTP check — returns (status_code, latency_str)."""
    try:
        r = requests.get(url, timeout=10)
        return r.status_code, f"{round(r.elapsed.total_seconds(), 2)}s"
    except Exception:
        return "ERR", "—"


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def get_site_repo_data() -> dict:
    """
    Live GitHub API — checks SITE_REPO (aura-glossy):
      - Last 4 commits + messages
      - Open issue count
    """
    hdrs = _gh_headers()
    out  = {"last_commit": "—", "issues": 0, "new_items": []}
    try:
        r = requests.get(
            f"https://api.github.com/repos/{SITE_REPO}/commits?per_page=4",
            headers=hdrs, timeout=10)
        if r.ok:
            c = r.json()
            if c:
                out["last_commit"] = c[0]["sha"][:7]
                out["new_items"]   = [
                    x["commit"]["message"].split("\n")[0][:58]
                    for x in c[:4]
                ]
        r = requests.get(
            f"https://api.github.com/repos/{SITE_REPO}/issues?state=open&per_page=1",
            headers=hdrs, timeout=10)
        if r.ok:
            lk = r.headers.get("Link", "")
            m  = re.search(r'page=(\d+)>; rel="last"', lk)
            out["issues"] = int(m.group(1)) if m else len(r.json())
    except Exception:
        pass
    return out


def get_automation_workflow_status() -> str:
    """
    Live GitHub API — checks THIS repo (maya-life-os) for the last
    morning_report.yml run status. Shown in Aura Glossy section.
    Returns: 'ok' | 'failed' | 'unknown'
    """
    try:
        r = requests.get(
            f"https://api.github.com/repos/{AUTOMATION_REPO}"
            f"/actions/workflows/morning_report.yml/runs?per_page=1",
            headers=_gh_headers(), timeout=10)
        if r.ok:
            runs = r.json().get("workflow_runs", [])
            if runs:
                c = runs[0].get("conclusion", "unknown") or "unknown"
                return "ok" if c == "success" else ("failed" if c == "failure" else "unknown")
    except Exception:
        pass
    return "unknown"


def check_netlify() -> tuple:
    """Live Netlify API — checks auraglossy deploy status."""
    if not NETLIFY_TOKEN:
        return False, "Token not set"
    try:
        r = requests.get(
            "https://api.netlify.com/api/v1/sites",
            headers={"Authorization": f"Bearer {NETLIFY_TOKEN}"},
            timeout=10)
        if r.ok:
            for site in r.json():
                if "auraglossy" in (site.get("name","") + site.get("url","")).lower():
                    st = site.get("published_deploy", {}).get("state", "?")
                    return st == "ready", st
            return True, "ok"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:28]


def _dstr(raw: str) -> str:
    parts = decode_header(raw or "")
    return " ".join(
        p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p
        for p, enc in parts
    )


def fetch_emails(limit: int = 10) -> tuple:
    """
    Live Gmail IMAP — fetches unread messages, returns
    (important_list, total_unread_count).
    Only includes emails from priority senders or with urgent keywords.
    """
    if not GMAIL_ADDRESS or not GMAIL_PASS:
        return [], 0
    items, unread = [], 0
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(GMAIL_ADDRESS, GMAIL_PASS)
        m.select("INBOX")
        _, d = m.search(None, "UNSEEN")
        ids   = d[0].split()
        unread = len(ids)
        for eid in reversed(ids[-30:]):
            _, md  = m.fetch(eid, "(RFC822)")
            msg    = email.message_from_bytes(md[0][1])
            sender  = _dstr(msg.get("From", ""))
            subject = _dstr(msg.get("Subject", "(no subject)"))
            date_s  = msg.get("Date", "")[:16]
            prev    = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            prev = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            pass
                        break
            else:
                try:
                    prev = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
            prev  = re.sub(r"\s+", " ", prev).strip()[:80]
            sl    = sender.lower()
            sub_l = subject.lower()
            is_p  = any(p in sl or p in sub_l for p in PRIORITY_SENDERS)
            is_u  = any(w in sub_l for w in URGENT_KEYWORDS)
            if is_p or is_u:
                items.append({
                    "sender":  sender[:45],
                    "subject": subject[:55],
                    "preview": prev,
                    "time":    date_s,
                    "urgent":  is_u,
                })
                if len(items) >= limit:
                    break
        m.logout()
    except Exception:
        pass
    return items, unread


def get_moodle_deadlines() -> list:
    """
    Live Moodle API (moodle.kinneret.ac.il) — fetches upcoming
    calendar events within the next 7 days.
    """
    dl = []
    if not MOODLE_USER or not MOODLE_PASS:
        return dl
    try:
        r = requests.post(
            f"{MOODLE_URL}/login/token.php",
            data={"username": MOODLE_USER, "password": MOODLE_PASS,
                  "service": "moodle_mobile_app"},
            timeout=15)
        tok = r.json().get("token")
        if not tok:
            return dl
        def ws(fn, **kw):
            return requests.post(
                f"{MOODLE_URL}/webservice/rest/server.php",
                data={"wstoken": tok, "wsfunction": fn,
                      "moodlewsrestformat": "json", **kw},
                timeout=15).json()
        if not ws("core_webservice_get_site_info").get("userid"):
            return dl
        now_ts  = int(datetime.now().timestamp())
        week_ts = now_ts + 7 * 86400
        evs = ws("core_calendar_get_calendar_upcoming_view") \
                .get("events", {}).get("events", [])
        for ev in evs[:15]:
            ts = ev.get("timestart", 0)
            if now_ts <= ts <= week_ts:
                dt = datetime.fromtimestamp(ts, tz=JERUSALEM_TZ)
                dl.append({
                    "title":  ev.get("name", "")[:52],
                    "course": ev.get("course", {}).get("shortname", ""),
                    "due":    dt.strftime("%a %d %b  %H:%M"),
                    "ts":     ts,
                })
        dl.sort(key=lambda x: x["ts"])
    except Exception:
        pass
    return dl


# ─── Helpers ──────────────────────────────────────────────────────

def _career_status(emails: list) -> dict:
    """Overlay live email subjects onto static default statuses."""
    status = dict(CAREER_PLATFORMS)
    for e in emails:
        sl = e["sender"].lower()
        for platform, key in [
            ("imerit", "iMerit"), ("telus", "TELUS Digital"),
            ("transperfect", "TransPerfect"), ("mercor", "Mercor"),
        ]:
            if platform in sl:
                status[key] = e["subject"][:40]
    return status

def _email_priority_split(emails: list) -> tuple:
    high, med, low = [], [], []
    for e in emails:
        sl = e["sender"].lower()
        if e.get("urgent") or any(k in sl for k in ["google", "github", "security"]):
            high.append(e)
        elif any(k in sl for k in ["imerit", "telus", "transperfect", "mercor", "moodle", "kinneret"]):
            med.append(e)
        else:
            low.append(e)
    return high, med, low

def _sender_icon(sender: str) -> str:
    sl = sender.lower()
    return next((ic for k, ic in SENDER_ICONS.items() if k in sl), "📨")


# ════════════════════════════════════════════════════════════════════
# ░░  PART 1 — FULL MORNING REPORT FORMATTERS  ░░
# Sent once at 08:00 Jerusalem time.
# ════════════════════════════════════════════════════════════════════

DIV    = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
LINE   = "──────────────────────────────"
P_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}

def _sec(title: str, body: str) -> str:
    return f"<b>{title}</b>\n{LINE}\n{body}"


def _p1_header(now: datetime) -> str:
    return (
        f"{DIV}\n"
        f"✨ <b>{_greeting(now)}, Maya!</b> ☀️\n"
        f"Here is your smart update for today 💜\n"
        f"📅 {now.strftime('%A, %d %B %Y')}  ·  🕐 {now.strftime('%I:%M %p')}\n"
        f"{DIV}"
    )


def _p1_today_classes(now: datetime) -> str:
    """Show today's university classes — only on days that have them."""
    classes = WEEKLY_SCHEDULE.get(now.weekday(), [])
    if not classes:
        return ""   # free day — skip section entirely

    rows = []
    for c in classes:
        rows.append(f"🕐 <b>{c['time']}</b>   {c['course']}  <i>({c['type']})</i>")

    day_name = now.strftime("%A")
    return _sec(f"🎓 TODAY'S CLASSES  ·  {day_name}", "\n".join(rows))


def _p1_quick_summary(unread: int, high_count: int, deadline_count: int, now: datetime) -> str:
    mins  = _mins_until(13, 0, now)
    h_str = f"{mins//60}h {mins%60}m" if mins >= 60 else f"{mins} min"
    body  = (
        f"📧  <b>{unread}</b> New Emails  ·  🔴 <b>{high_count} Important</b>\n"
        f"📌  <b>{deadline_count}</b> Deadline{'s' if deadline_count != 1 else ''}  ·  "
        + ("⚠️ Urgent" if deadline_count else "✅ Clear") + "\n"
        f"📖  Next Study: <b>13:00</b>  (in {h_str})\n"
        f"🍎  Focus Block: <b>90 min</b>  Apple Time"
    )
    return _sec("◆ QUICK SUMMARY", body)


def _p1_email_check(emails: list, unread: int) -> str:
    high, med, low = _email_priority_split(emails)
    summary = (
        f"🔴 <b>{len(high)}</b> High  ·  "
        f"🟠 <b>{len(med)}</b> Medium  ·  "
        f"🟢 <b>{len(low)}</b> Low"
    )
    if not emails:
        body = f"{summary}\n\nNo important emails right now."
    else:
        rows = []
        for e in (high + med + low)[:6]:
            icon    = _sender_icon(e["sender"])
            urgmark = "  🔴" if e.get("urgent") else ""
            name    = e["sender"].split("<")[0].strip()[:22]
            subj    = e["subject"][:32]
            t       = e.get("time", "")[-5:] or "—"
            rows.append(f"{icon} {name}  —  {subj}{urgmark}   <i>{t}</i>")
        body = summary + "\n" + LINE + "\n" + "\n".join(rows)
    header = f"📬 EMAIL CHECK  —  {unread} new  🔴" if unread else "📬 EMAIL CHECK"
    return f"<b>{header}</b>\n{LINE}\n{body}"


def _p1_priorities(deadlines: list) -> str:
    tasks = list(DEFAULT_TASKS)
    for d in deadlines[:2]:
        tasks.insert(0, {"n": 0,
                         "task": f"{d['title']}  (due {d['due']})",
                         "priority": "high"})
    tasks = tasks[:3]
    rows = []
    for i, t in enumerate(tasks, 1):
        icon = P_ICONS.get(t["priority"], "⚪")
        rows.append(f"<b>{i}</b>  {t['task']}  {icon} <i>{t['priority'].title()}</i>")
    return _sec("🎯 TODAY'S PRIORITIES", "\n".join(rows))


def _p1_study_plan() -> str:
    rows = [f"🕐 {s['time']}   {s['subject']}  ·  {s['topic']}" for s in DEFAULT_STUDY]
    rows.append(f"\n⭐ Focus: <b>{STUDY_FOCUS}</b>")
    return _sec(f"🎓 STUDY PLAN  ·  Min. {STUDY_HOURS}h today", "\n".join(rows))


def _p1_aura_glossy(ws: tuple, lg: tuple, gh: dict,
                     wf_status: str, net_ok: bool) -> str:
    bugs_icon = "✅" if gh["issues"] == 0 else ("⚠️" if gh["issues"] < 6 else "🔴")
    wf_icon   = {"ok": "✅", "failed": "🔴", "unknown": "⚠️"}.get(wf_status, "⚠️")
    wf_txt    = "Running" if wf_status == "ok" else wf_status.upper()
    net_txt   = "Deploy OK  ✅" if net_ok else "Token not set  ⚠️"
    ws_icon   = "✅" if str(ws[0]).startswith("2") else "❌"
    lg_icon   = "✅" if str(lg[0]).startswith("2") else "❌"
    rows = [
        f"🌐 Website      <code>{ws[0]}</code> ({ws[1]})  {ws_icon}",
        f"🔐 Login        <code>{lg[0]}</code> ({lg[1]})  {lg_icon}",
        f"🐛 Bugs         <b>{gh['issues']}</b> Open  {bugs_icon}",
        f"⚙️ Automation   {wf_txt}  {wf_icon}",
        f"📦 Last Commit  <code>{gh['last_commit']}</code>",
        f"☁️ Netlify       {net_txt}",
    ]
    if gh["new_items"]:
        rows.append("\n📝 <b>What's new:</b>")
        for item in gh["new_items"][:3]:
            rows.append(f"  ·  {item}")
    return _sec("🚀 AURA GLOSSY UPDATE", "\n".join(rows))


def _p1_reminders(now: datetime) -> str:
    mins  = _mins_until(13, 0, now)
    h_str = f"{mins//60}h {mins%60}m" if mins >= 60 else f"{mins} min"
    rows = [
        f"🕐 Study starts        <b>13:00</b>  (in {h_str})",
        f"📧 Email auto-check    <b>09:00</b>  automatic",
        f"🧠 Deep work block     <b>13:00 – 16:00</b>",
        f"🍎 Apple Ecosystem     <b>Plan 90 min today</b>",
    ]
    return _sec("🔔 REMINDERS &amp; ALERTS", "\n".join(rows))


def _p1_career(emails: list) -> str:
    status = _career_status(emails)
    rows   = [f"◦ {k:<18}{v}" for k, v in status.items()]
    rows.append("\n➡️ Follow up by 31/05")
    return _sec("💼 CAREER &amp; JOBS UPDATE", "\n".join(rows))


def _p1_apple_footer() -> str:
    return (
        f"{DIV}\n"
        f"🍎 <b>DAILY APPLE REMINDER</b> 🍎\n"
        f"{LINE}\n"
        f"Don't forget your 90 minutes with Apple today!\n"
        f"Build. Learn. Create. Innovate. ✨\n\n"
        f"▶ START APPLE TIME — 90 min session\n"
        f"{DIV}\n"
        f"⭐ You're building your future,\n"
        f"   one deep work session at a time. 💜\n"
        f"{DIV}"
    )


def build_morning_report(now: datetime) -> str:
    ws              = check_url(WEBSITE_URL)
    lg              = check_url(LOGIN_URL)
    gh              = get_site_repo_data()
    wf_status       = get_automation_workflow_status()
    net_ok, _       = check_netlify()
    emails, unread  = fetch_emails(limit=8)
    deadlines       = get_moodle_deadlines()
    high, _, _      = _email_priority_split(emails)

    sections = [
        _p1_header(now),
        _p1_today_classes(now),
        _p1_quick_summary(unread, len(high), len(deadlines), now),
        _p1_email_check(emails, unread),
        _p1_priorities(deadlines),
        _p1_study_plan(),
        _p1_aura_glossy(ws, lg, gh, wf_status, net_ok),
        _p1_reminders(now),
        _p1_career(emails),
        _p1_apple_footer(),
    ]
    return "\n\n".join(s for s in sections if s and s.strip())


# ════════════════════════════════════════════════════════════════════
# ░░  PART 2 — DAYTIME REMINDER BUILDERS  ░░
# Short, clean, actionable. Never repeat the full report.
# ════════════════════════════════════════════════════════════════════

def _r_header(icon: str, title: str, now: datetime) -> str:
    return f"{icon} <b>{title}</b>  <i>{now.strftime('%I:%M %p')}</i>\n{LINE}"

def _r_footer(text: str) -> str:
    return f"{LINE}\n{text}"


def build_email_check(now: datetime):
    """09:00 — Only fires if important email arrived since morning."""
    emails, unread = fetch_emails(limit=5)
    if not emails:
        return None
    high, med, _ = _email_priority_split(emails)
    rows = []
    for e in emails[:4]:
        icon    = _sender_icon(e["sender"])
        name    = e["sender"].split("<")[0].strip()[:20]
        subj    = e["subject"][:38]
        urgmark = "  🔴" if e.get("urgent") else ""
        rows.append(f"{icon} {name}  —  {subj}{urgmark}")
    summary = f"🔴 {len(high)} High  ·  🟠 {len(med)} Medium" if (high or med) else f"{unread} unread"
    tip     = "💡 Review before your 13:00 study block." if high else "💡 Review when you have a moment."
    return (
        f"{_r_header('📬', 'EMAIL ALERT', now)}\n"
        f"{summary}\n\n"
        f"\n".join(rows) + "\n\n"
        f"{_r_footer(tip)}"
    )


def build_midday(now: datetime) -> str:
    """12:30 — Short nudge 30 min before study block."""
    deadlines = get_moodle_deadlines()
    soon      = [d for d in deadlines if d["ts"] - datetime.now().timestamp() < 48 * 3600]
    lines     = [
        _r_header("☀️", "MIDDAY NUDGE", now),
        f"Study block starts in <b>30 min</b>  📖",
        f"3 sessions planned  ·  3h total",
        f"Focus: <b>{STUDY_FOCUS.split('(')[0].strip()}</b>",
    ]
    if soon:
        lines.append("\n⚠️ Due soon:")
        for d in soon[:2]:
            lines.append(f"   📌 {d['title']}  ·  {d['due']}")
    lines.append(_r_footer("⭐ You've got this, Maya!"))
    return "\n".join(lines)


def build_study_reminder(now: datetime) -> str:
    """13:00 — Study session start alert."""
    return (
        f"{_r_header('🎓', 'STUDY SESSION — NOW', now)}\n"
        f"<b>Session 1</b>  ·  13:00 – 14:00\n"
        f"   Deep Learning  ·  Object Detection\n\n"
        f"<b>Session 2</b>  ·  14:15 – 15:15\n"
        f"   Systems Engineering  ·  Review\n\n"
        f"<b>Session 3</b>  ·  15:30 – 16:30\n"
        f"   Coding Practice  ·  Problem Solving\n\n"
        f"{_r_footer('Minimum: <b>2 focused hours</b> today. 💜')}"
    )


def build_afternoon(now: datetime) -> str:
    """16:00 — Short afternoon check-in."""
    emails, _  = fetch_emails(limit=3)
    gh         = get_site_repo_data()
    wf_status  = get_automation_workflow_status()
    wf         = "✅ OK" if wf_status == "ok" else "⚠️ Check"
    lines      = [
        _r_header("🌤", "AFTERNOON CHECK", now),
        f"🚀 Aura Glossy  ·  <code>{gh['last_commit']}</code>  ·  Automation {wf}",
    ]
    if emails:
        names      = [e["sender"].split("<")[0].strip()[:18] for e in emails[:3]]
        urgent_any = any(e.get("urgent") for e in emails)
        lines.append(
            f"📧 {len(emails)} new email{'s' if len(emails)!=1 else ''}"
            + (" 🔴 URGENT" if urgent_any else "") +
            f":  {', '.join(names)}"
        )
    lines += [
        "",
        "<b>Remaining today:</b>",
        "  ○ Follow ups &amp; Tasks  (now)",
        "  ○ Deep work session     (20:00)",
        "  ○ Apple ecosystem       (90 min)",
    ]
    lines.append(_r_footer("Stay strong through the finish line. 💪"))
    return "\n".join(lines)


def build_apple(now: datetime) -> str:
    """20:00 — Apple ecosystem 90-min reminder."""
    return (
        f"{DIV}\n"
        f"🍎 <b>APPLE TIME</b>  ·  90 min\n"
        f"{LINE}\n"
        f"Start your Apple session now!\n"
        f"Build  ·  Learn  ·  Create  ·  Innovate ✨\n\n"
        f"Ideas:\n"
        f"  •  SwiftUI component\n"
        f"  •  Xcode / Instruments\n"
        f"  •  Apple Developer docs\n"
        f"  •  Test on real device\n"
        f"{DIV}"
    )


def build_evening(now: datetime) -> str:
    """21:30 — Evening wrap."""
    deadlines = get_moodle_deadlines()
    tomorrow  = (now + timedelta(days=1)).strftime("%A, %d %B")
    due_soon  = [d for d in deadlines
                 if d["ts"] < (datetime.now() + timedelta(days=2)).timestamp()]
    lines     = [
        _r_header("🌙", "EVENING WRAP", now),
        f"Tomorrow: <b>{tomorrow}</b>\n",
        "Before you sleep:",
        "  ✓ Reviewed tomorrow's priorities?",
        "  ✓ Studied at least 2 hours?",
        "  ✓ Done your Apple 90-min session?",
    ]
    if due_soon:
        lines.append("\n⚠️ <b>Due soon:</b>")
        for d in due_soon[:3]:
            lines.append(f"   📌 {d['title']}  ·  {d['due']}")
    lines.append(_r_footer("Sleep well, Maya 💜"))
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# SEND
# ════════════════════════════════════════════════════════════════════

def send(message: str) -> None:
    api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX = 4096
    chunks, cur = [], ""
    for part in message.split("\n\n"):
        candidate = (cur + "\n\n" + part).lstrip("\n")
        if len(candidate) <= MAX:
            cur = candidate
        else:
            if cur:
                chunks.append(cur)
            cur = part
    if cur:
        chunks.append(cur)
    for chunk in chunks:
        r = requests.post(api, json={
            "chat_id":                  TELEGRAM_CHAT,
            "text":                     chunk,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        r.raise_for_status()


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════

MODE_MAP = {
    "morning":        build_morning_report,
    "email_check":    build_email_check,
    "midday":         build_midday,
    "study_reminder": build_study_reminder,
    "afternoon":      build_afternoon,
    "apple":          build_apple,
    "evening":        build_evening,
}

def main() -> None:
    now  = now_j()
    mode = detect_mode(now)
    print(f"[{now.strftime('%Y-%m-%d %H:%M')} Jerusalem]  mode={mode}")

    if mode is None:
        print("Wrong-DST trigger — skipping silently.")
        sys.exit(0)

    builder = MODE_MAP.get(mode)
    if not builder:
        print(f"Unknown mode '{mode}'.")
        sys.exit(1)

    message = builder(now)
    if message is None:
        print(f"Mode '{mode}' — nothing important to send.")
        sys.exit(0)

    send(message)
    print(f"Sent '{mode}' successfully.")

if __name__ == "__main__":
    main()
