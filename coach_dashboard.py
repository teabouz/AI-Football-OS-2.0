"""
Coach Dashboard — Phase 3.

A small, self-contained Flask app for everything that's genuinely easier as
a web form than a Telegram conversation: training session planning (with
optional AI generation), player notes, medical/fitness tracking, match
reports, club finance, and equipment inventory. Attendance itself is taken
in the bot (handlers/attendance.py) since that's a "phone in hand on the
pitch" action — this dashboard shows the results.

Auth: magic-link only (see handlers/team.py: dashboard_command). No
passwords to manage. Sessions are Flask's signed cookie sessions, keyed off
FLASK_SECRET_KEY. This is scoped as a small pilot tool for one coach's own
team, not a hardened multi-tenant SaaS — if this grows into something with
real financial/medical data at scale, add CSRF protection (flask-wtf) and
proper audit logging before wider rollout.

Run:
    python coach_dashboard.py
Then in the bot, a coach/academy account runs /dashboard to get a login link.
"""
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Flask, request, session as flask_session, redirect, url_for, render_template_string
from markupsafe import escape as esc

from anthropic import Anthropic, APIError

from database import SessionLocal, init_db
from models import (
    User, UserRole, Team, TeamMembership, TrainingSession, AttendanceRecord,
    PlayerNote, MedicalRecord, MedicalStatus, MatchReport, FinanceEntry,
    FinanceEntryType, EquipmentItem, EquipmentCondition, DashboardToken,
    PlayerScoutingReport, ScoutingProspect, ProspectStatus, VideoAnalysis,
    DevelopmentPlan, Opportunity, OpportunityApplication, ListingType,
    ListingStatus, ApplicationStatus, EquipmentListing, EquipmentInterest,
    EquipmentListingStatus,
)
import config
import notifications

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None


# ============================================================
# Layout / shared chrome
# ============================================================

STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0b1120; color:#e5e7eb; margin:0; }
header { background:#111827; padding:1rem 2rem; border-bottom:1px solid #1f2937; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;}
header h1 { color:#22c55e; margin:0; font-size:1.3rem; }
nav a { color:#9ca3af; text-decoration:none; margin-right:1rem; font-size:0.9rem; }
nav a:hover { color:#22c55e; }
main { padding:1.5rem 2rem; max-width:1000px; margin:0 auto; }
h2 { color:#e5e7eb; font-size:1.1rem; border-bottom:1px solid #1f2937; padding-bottom:0.5rem;}
.card { background:#111827; border:1px solid #1f2937; border-radius:10px; padding:1.25rem; margin-bottom:1.25rem; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:0.5rem 0.6rem; border-bottom:1px solid #1f2937; font-size:0.9rem; }
th { color:#9ca3af; text-transform:uppercase; font-size:0.72rem; }
tr:hover { background:#1a2333; }
input, select, textarea { background:#0b1120; border:1px solid #374151; color:#e5e7eb; border-radius:6px; padding:0.5rem; width:100%; box-sizing:border-box; margin-bottom:0.6rem; font-family:inherit; }
label { font-size:0.8rem; color:#9ca3af; display:block; margin-bottom:0.2rem; }
button { background:#22c55e; color:#052e16; border:none; border-radius:6px; padding:0.55rem 1.1rem; font-weight:600; cursor:pointer; }
button:hover { background:#4ade80; }
button.secondary { background:#374151; color:#e5e7eb; }
.badge { padding:2px 8px; border-radius:999px; font-size:0.72rem; display:inline-block; }
.badge.fit { background:#14532d; color:#4ade80; }
.badge.doubtful { background:#78350f; color:#fbbf24; }
.badge.injured { background:#7f1d1d; color:#f87171; }
.badge.good { background:#14532d; color:#4ade80; }
.badge.fair { background:#78350f; color:#fbbf24; }
.badge.poor, .badge.needs_replacement { background:#7f1d1d; color:#f87171; }
.badge.watching { background:#1e3a5f; color:#60a5fa; }
.badge.trial_invited { background:#78350f; color:#fbbf24; }
.badge.passed { background:#374151; color:#9ca3af; }
.badge.signed { background:#14532d; color:#4ade80; }
.badge.open { background:#14532d; color:#4ade80; }
.badge.closed { background:#374151; color:#9ca3af; }
.badge.pending { background:#78350f; color:#fbbf24; }
.badge.reviewed { background:#1e3a5f; color:#60a5fa; }
.badge.accepted { background:#14532d; color:#4ade80; }
.badge.rejected { background:#7f1d1d; color:#f87171; }
.badge.available { background:#14532d; color:#4ade80; }
.badge.reserved { background:#78350f; color:#fbbf24; }
.badge.sold { background:#374151; color:#9ca3af; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px,1fr)); gap:1rem; margin-bottom:1.5rem;}
.stat .num { font-size:1.6rem; font-weight:700; color:#22c55e; }
.stat .label { font-size:0.8rem; color:#9ca3af; }
.muted { color:#9ca3af; font-size:0.85rem; }
.error { color:#f87171; background:#1f1414; border:1px solid #7f1d1d; padding:0.75rem; border-radius:6px; margin-bottom:1rem; }
.notice { color:#93c5fd; background:#0f1f30; border:1px solid #1e3a5f; padding:0.75rem; border-radius:6px; margin-bottom:1rem; font-size:0.85rem; }
a.link { color:#22c55e; }
"""

NAV = [
    ("/coach/", "🏠 Home"),
    ("/coach/roster", "👥 Roster"),
    ("/coach/sessions", "📅 Sessions"),
    ("/coach/notes", "📝 Notes"),
    ("/coach/medical", "🩺 Medical"),
    ("/coach/matches", "⚽ Matches"),
    ("/coach/finance", "💰 Finance"),
    ("/coach/equipment", "🎒 Equipment"),
    ("/coach/scouting", "🔍 Scouting"),
    ("/coach/marketplace", "🧩 Marketplace"),
]

LAYOUT = """
<!doctype html><html><head><meta charset="utf-8"><title>{{ title }} — Coach Dashboard</title>
<style>""" + STYLE + """</style></head>
<body>
<header>
  <h1>🏆 {{ team_name or 'Coach Dashboard' }}</h1>
  <nav>{% for href, label in nav %}<a href="{{ href }}">{{ label }}</a>{% endfor %}<a href="/coach/logout">🚪 Logout</a></nav>
</header>
<main>{{ body|safe }}</main>
</body></html>
"""


def render(title, body, team_name=None):
    return render_template_string(LAYOUT, title=title, body=body, team_name=team_name, nav=NAV)


def naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


# ============================================================
# Auth
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not flask_session.get("user_id"):
            return redirect("/coach/login")
        return f(*args, **kwargs)
    return decorated


def current_user_and_team(session):
    user = session.query(User).filter_by(id=flask_session["user_id"]).first()
    team = session.query(Team).filter_by(owner_user_id=user.id).first() if user else None
    return user, team


@app.route("/coach/login")
def login():
    token = request.args.get("token", "")
    next_path = request.args.get("next", "/coach/")
    if not next_path.startswith("/coach/"):  # guard against open-redirect via a crafted `next`
        next_path = "/coach/"
    session = SessionLocal()
    try:
        record = session.query(DashboardToken).filter_by(token=token).first()
        if not record or record.used or record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            return render(
                "Login", '<div class="card error">This link is invalid or has expired. '
                'Go back to Telegram and run /dashboard for a new one.</div>'
            ), 401
        record.used = True
        session.commit()
        flask_session["user_id"] = record.user_id
        flask_session.permanent = False
        return redirect(next_path)
    finally:
        session.close()


@app.route("/coach/logout")
def logout():
    flask_session.clear()
    return redirect("/coach/login")


# ============================================================
# Home
# ============================================================

@app.route("/coach/")
@login_required
def home():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return render("Dashboard", '<div class="card">No team yet — create one from the bot with '
                                        '<code>/createteam &lt;name&gt;</code>, then reopen this link.</div>')

        members = [m for m in team.members if m.active]
        recent_sessions = (
            session.query(TrainingSession).filter_by(team_id=team.id)
            .order_by(TrainingSession.session_date.desc()).limit(5).all()
        )
        injured = []
        for m in members:
            latest = (
                session.query(MedicalRecord).filter_by(membership_id=m.id)
                .order_by(MedicalRecord.updated_at.desc()).first()
            )
            if latest and latest.status != MedicalStatus.FIT:
                injured.append((m, latest))

        income = sum(e.amount_kobo for e in team.finance_entries if e.entry_type == FinanceEntryType.INCOME)
        expense = sum(e.amount_kobo for e in team.finance_entries if e.entry_type == FinanceEntryType.EXPENSE)

        body = f"""
        <div class="grid">
          <div class="card stat"><div class="num">{len(members)}</div><div class="label">Players on roster</div></div>
          <div class="card stat"><div class="num">{len(team.training_sessions)}</div><div class="label">Training sessions logged</div></div>
          <div class="card stat"><div class="num">{len(injured)}</div><div class="label">Players not 100% fit</div></div>
          <div class="card stat"><div class="num">{naira(income - expense)}</div><div class="label">Club balance</div></div>
        </div>
        <div class="card">
          <h2>Recent sessions</h2>
          {"".join(f'<p><a class="link" href="/coach/sessions/{s.id}">{s.session_date.strftime("%d %b %Y")}</a> — {esc(s.focus) if s.focus else "no focus set"} {"⭐" * (s.evaluation_rating or 0)}</p>' for s in recent_sessions) or '<p class="muted">No sessions yet.</p>'}
        </div>
        <div class="card">
          <h2>Fitness watchlist</h2>
          {"".join(f'<p><a class="link" href="/coach/medical">{esc(m.display_name())}</a> — <span class="badge {r.status.value}">{r.status.value}</span> {esc(r.description) if r.description else ""}</p>' for m, r in injured) or '<p class="muted">Everyone fit. 🎉</p>'}
        </div>
        """
        return render("Dashboard", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# Roster
# ============================================================

@app.route("/coach/roster", methods=["GET", "POST"])
@login_required
def roster():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip().lstrip("@")
            guest_name = request.form.get("guest_name", "").strip()
            if username:
                player = session.query(User).filter_by(username=username, role=UserRole.PLAYER).first()
                if not player:
                    error = f"No registered player found with username @{esc(username)}."
                else:
                    dupe = session.query(TeamMembership).filter_by(team_id=team.id, player_user_id=player.id).first()
                    if dupe:
                        error = f"{esc(player.display_name())} is already on the roster."
                    else:
                        session.add(TeamMembership(team_id=team.id, player_user_id=player.id))
                        session.commit()
            elif guest_name:
                session.add(TeamMembership(team_id=team.id, guest_name=guest_name))
                session.commit()
            else:
                error = "Enter a username or a guest name."

        members = [m for m in team.members if m.active]
        rows = "".join(
            f"<tr><td>{esc(m.display_name())}</td><td>{'Registered' if m.player_user_id else 'Guest'}</td>"
            f"<td>{m.joined_at.strftime('%d %b %Y')}</td>"
            f'<td><form method="post" action="/coach/roster/remove/{m.id}" style="margin:0;">'
            f'<button class="secondary" type="submit">Remove</button></form></td></tr>'
            for m in members
        )

        body = f"""
        {f'<div class="error">{error}</div>' if error else ''}
        <div class="card">
          <h2>Add a player</h2>
          <form method="post">
            <label>Username (if they're on the bot)</label>
            <input name="username" placeholder="@username">
            <label>Or guest name (if not on the bot yet)</label>
            <input name="guest_name" placeholder="Full name">
            <button type="submit">Add to roster</button>
          </form>
        </div>
        <div class="card">
          <h2>Roster ({len(members)})</h2>
          <table><tr><th>Name</th><th>Type</th><th>Joined</th><th></th></tr>{rows or '<tr><td colspan=4 class="muted">No players yet.</td></tr>'}</table>
        </div>
        """
        return render("Roster", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/roster/remove/<int:membership_id>", methods=["POST"])
@login_required
def roster_remove(membership_id):
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        m = session.query(TeamMembership).filter_by(id=membership_id, team_id=team.id if team else -1).first()
        if m:
            m.active = False
            session.commit()
        return redirect("/coach/roster")
    finally:
        session.close()


# ============================================================
# Training Sessions (planning + evaluation; attendance is bot-side)
# ============================================================

def _generate_session_plan(focus: str) -> str:
    if _client is None:
        return "(AI not configured — set ANTHROPIC_API_KEY to enable plan generation.)"
    prompt = (
        f"Create a single football training session plan (60-90 minutes) focused on: {focus}.\n"
        "Include: warm-up (10 min), a main technical/tactical block with 2-3 specific drills, "
        "a small-sided game idea, and a cool-down. Practical for a youth academy setting. "
        "Plain text, short headers, under 300 words."
    )
    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=500,
            system="You are a UEFA-licensed football coach writing practical training session plans.",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except APIError:
        return "(Couldn't generate a plan right now — you can write one manually below.)"


@app.route("/coach/sessions", methods=["GET", "POST"])
@login_required
def sessions():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            session_date = request.form.get("session_date") or date.today().isoformat()
            focus = request.form.get("focus", "").strip()
            plan_text = _generate_session_plan(focus) if request.form.get("generate_plan") and focus else None
            new_session = TrainingSession(
                team_id=team.id,
                session_date=datetime.strptime(session_date, "%Y-%m-%d").date(),
                focus=focus or None,
                plan_text=plan_text,
            )
            session.add(new_session)
            session.commit()
            return redirect(f"/coach/sessions/{new_session.id}")

        rows_list = (
            session.query(TrainingSession).filter_by(team_id=team.id)
            .order_by(TrainingSession.session_date.desc()).all()
        )
        rows = "".join(
            f'<tr><td><a class="link" href="/coach/sessions/{s.id}">{s.session_date.strftime("%d %b %Y")}</a></td>'
            f'<td>{esc(s.focus) if s.focus else "—"}</td><td>{"⭐" * (s.evaluation_rating or 0) or "—"}</td></tr>'
            for s in rows_list
        )

        body = f"""
        <div class="card">
          <h2>New session</h2>
          <form method="post">
            <label>Date</label>
            <input type="date" name="session_date" value="{date.today().isoformat()}">
            <label>Focus</label>
            <input name="focus" placeholder="e.g. Defensive shape and pressing triggers">
            <label><input type="checkbox" name="generate_plan" value="1" style="width:auto; display:inline-block; margin-right:0.4rem;">Generate an AI plan from the focus</label>
            <button type="submit">Create session</button>
          </form>
        </div>
        <div class="card">
          <h2>All sessions</h2>
          <table><tr><th>Date</th><th>Focus</th><th>Rating</th></tr>{rows or '<tr><td colspan=3 class="muted">No sessions yet.</td></tr>'}</table>
        </div>
        """
        return render("Sessions", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/sessions/<int:session_id>", methods=["GET", "POST"])
@login_required
def session_detail(session_id):
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        train_session = session.query(TrainingSession).filter_by(id=session_id, team_id=team.id if team else -1).first()
        if not train_session:
            return redirect("/coach/sessions")

        if request.method == "POST":
            train_session.plan_text = request.form.get("plan_text", "").strip() or None
            rating = request.form.get("evaluation_rating")
            train_session.evaluation_rating = int(rating) if rating else None
            train_session.evaluation_notes = request.form.get("evaluation_notes", "").strip() or None
            session.commit()

        records = (
            session.query(AttendanceRecord).filter_by(session_id=train_session.id).all()
        )
        present = sum(1 for r in records if r.present)
        attendance_rows = "".join(
            f'<tr><td>{esc(r.membership.display_name())}</td><td>{"✅ Present" if r.present else "⬜ Absent"}</td></tr>'
            for r in records
        )

        rating_options = "".join(
            f'<option value="{i}" {"selected" if train_session.evaluation_rating == i else ""}>{"⭐" * i}</option>'
            for i in range(1, 6)
        )

        body = f"""
        <div class="card">
          <h2>{train_session.session_date.strftime('%A, %d %b %Y')}</h2>
          <p class="muted">Focus: {esc(train_session.focus) if train_session.focus else '—'}</p>
          <form method="post">
            <label>Plan</label>
            <textarea name="plan_text" rows="8">{esc(train_session.plan_text) if train_session.plan_text else ''}</textarea>
            <label>Session rating</label>
            <select name="evaluation_rating"><option value="">—</option>{rating_options}</select>
            <label>Evaluation notes</label>
            <textarea name="evaluation_notes" rows="4">{esc(train_session.evaluation_notes) if train_session.evaluation_notes else ''}</textarea>
            <button type="submit">Save</button>
          </form>
        </div>
        <div class="card">
          <h2>Attendance ({present}/{len(records)})</h2>
          <p class="muted">Taken via the bot's /attendance command on the day.</p>
          <table><tr><th>Player</th><th>Status</th></tr>{attendance_rows or '<tr><td colspan=2 class="muted">No attendance taken yet — run /attendance in the bot.</td></tr>'}</table>
        </div>
        <p><a class="link" href="/coach/sessions">&larr; All sessions</a></p>
        """
        return render("Session", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# Player Notes
# ============================================================

@app.route("/coach/notes", methods=["GET", "POST"])
@login_required
def notes():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        members = [m for m in team.members if m.active]
        member_ids = {m.id for m in members}
        selected_id = request.form.get("membership_id") or request.args.get("member_id")
        selected_id = int(selected_id) if selected_id else (members[0].id if members else None)

        if request.method == "POST" and request.form.get("note_text"):
            note_membership_id = int(request.form["membership_id"])
            # Never trust an ID from form data alone -- confirm it's actually
            # one of this coach's own roster members before writing a note.
            if note_membership_id in member_ids:
                session.add(PlayerNote(
                    membership_id=note_membership_id,
                    author_user_id=user.id,
                    note_text=request.form["note_text"].strip(),
                ))
                session.commit()

        options = "".join(
            f'<option value="{m.id}" {"selected" if m.id == selected_id else ""}>{esc(m.display_name())}</option>'
            for m in members
        )

        player_notes = []
        if selected_id:
            player_notes = (
                session.query(PlayerNote).filter_by(membership_id=selected_id)
                .order_by(PlayerNote.created_at.desc()).all()
            )
        notes_html = "".join(
            f'<div class="card"><p>{esc(n.note_text)}</p><p class="muted">{n.created_at.strftime("%d %b %Y %H:%M")}</p></div>'
            for n in player_notes
        )

        body = f"""
        <div class="card">
          <h2>Player notes</h2>
          <form method="get" style="margin-bottom:1rem;">
            <label>Player</label>
            <select name="member_id" onchange="this.form.submit()">{options}</select>
          </form>
          <form method="post">
            <input type="hidden" name="membership_id" value="{selected_id or ''}">
            <label>New note</label>
            <textarea name="note_text" rows="3" placeholder="Coach-only — never shown to the player"></textarea>
            <button type="submit">Add note</button>
          </form>
        </div>
        {notes_html or '<p class="muted">No notes for this player yet.</p>'}
        """
        return render("Notes", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# Medical / Fitness
# ============================================================

@app.route("/coach/medical", methods=["GET", "POST"])
@login_required
def medical():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            membership_id = int(request.form["membership_id"])
            # Never trust an ID from form data alone -- confirm it's actually
            # one of this coach's own roster members before writing a medical record.
            valid_membership = session.query(TeamMembership).filter_by(id=membership_id, team_id=team.id).first()
            if valid_membership:
                expected_return = request.form.get("expected_return_date") or None
                session.add(MedicalRecord(
                    membership_id=membership_id,
                    status=MedicalStatus(request.form["status"]),
                    description=request.form.get("description", "").strip() or None,
                    expected_return_date=datetime.strptime(expected_return, "%Y-%m-%d").date() if expected_return else None,
                    updated_by_user_id=user.id,
                ))
                session.commit()

        members = [m for m in team.members if m.active]
        rows = []
        for m in members:
            latest = (
                session.query(MedicalRecord).filter_by(membership_id=m.id)
                .order_by(MedicalRecord.updated_at.desc()).first()
            )
            status = latest.status.value if latest else "fit"
            desc = latest.description if latest else ""
            status_opts = "".join(
                f'<option value="{s.value}" {"selected" if s.value == status else ""}>{s.value.title()}</option>'
                for s in MedicalStatus
            )
            rows.append(f"""
            <tr>
              <td>{esc(m.display_name())}</td>
              <td><span class="badge {status}">{status}</span> {esc(desc) if desc else ''}</td>
              <td>
                <form method="post" style="display:flex; gap:0.4rem; flex-wrap:wrap; margin:0;">
                  <input type="hidden" name="membership_id" value="{m.id}">
                  <select name="status" style="width:auto;">{status_opts}</select>
                  <input name="description" placeholder="Note" style="width:140px;">
                  <input type="date" name="expected_return_date" style="width:150px;">
                  <button type="submit">Update</button>
                </form>
              </td>
            </tr>
            """)

        body = f"""
        <div class="card">
          <h2>Fitness &amp; medical status</h2>
          <table><tr><th>Player</th><th>Current status</th><th>Update</th></tr>{"".join(rows) or '<tr><td colspan=3 class="muted">No players yet.</td></tr>'}</table>
        </div>
        """
        return render("Medical", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# Match Reports
# ============================================================

def _generate_tactical_summary(match: MatchReport) -> str:
    if _client is None:
        return "(AI not configured — set ANTHROPIC_API_KEY to enable summary generation.)"
    summary_input = (
        f"Opponent: {match.opponent}\n"
        f"Competition: {match.competition or 'n/a'}\n"
        f"Score: {match.score_for if match.score_for is not None else '?'} - "
        f"{match.score_against if match.score_against is not None else '?'}\n"
        f"Formation used: {match.formation or 'not specified'}\n"
        f"Key moments (coach's notes): {match.key_moments or 'none logged'}\n"
        f"General notes: {match.notes or 'none'}"
    )
    prompt = (
        "A coach has logged the details below from a match they watched. Based ONLY on what they've "
        "written — you were not able to watch the match or any video of it — write a short tactical "
        "summary: 1) what likely worked (given the result and their notes), 2) what to address in "
        "training this week, 3) one specific thing to watch for against similar opponents. "
        "Be clear this is drawing on the coach's own account, not independent analysis. "
        "Plain text, under 200 words.\n\n" + summary_input
    )
    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=400,
            system="You are an assistant tactical analyst helping a coach reflect on a match "
                   "using only the notes they provide.",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except APIError:
        return "(Couldn't generate a summary right now — try again shortly.)"


@app.route("/coach/matches", methods=["GET", "POST"])
@login_required
def matches():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            new_match = MatchReport(
                team_id=team.id,
                match_date=datetime.strptime(request.form["match_date"], "%Y-%m-%d").date(),
                opponent=request.form["opponent"].strip(),
                competition=request.form.get("competition", "").strip() or None,
                score_for=int(request.form["score_for"]) if request.form.get("score_for") else None,
                score_against=int(request.form["score_against"]) if request.form.get("score_against") else None,
                formation=request.form.get("formation", "").strip() or None,
                key_moments=request.form.get("key_moments", "").strip() or None,
                notes=request.form.get("notes", "").strip() or None,
                created_by_user_id=user.id,
            )
            session.add(new_match)
            session.commit()
            return redirect(f"/coach/matches/{new_match.id}")

        match_list = (
            session.query(MatchReport).filter_by(team_id=team.id)
            .order_by(MatchReport.match_date.desc()).all()
        )
        rows = "".join(
            f'<tr><td><a class="link" href="/coach/matches/{m.id}">{m.match_date.strftime("%d %b %Y")}</a></td>'
            f'<td>{esc(m.opponent)}</td>'
            f'<td>{m.score_for if m.score_for is not None else "-"} : {m.score_against if m.score_against is not None else "-"}</td>'
            f'<td>{esc(m.competition) if m.competition else "—"}</td></tr>'
            for m in match_list
        )

        body = f"""
        <div class="card">
          <h2>Log a match</h2>
          <form method="post">
            <label>Date</label>
            <input type="date" name="match_date" value="{date.today().isoformat()}">
            <label>Opponent</label>
            <input name="opponent" required>
            <label>Competition</label>
            <input name="competition" placeholder="e.g. League, Friendly">
            <div style="display:flex; gap:1rem;">
              <div style="flex:1;"><label>Goals for</label><input type="number" name="score_for" min="0"></div>
              <div style="flex:1;"><label>Goals against</label><input type="number" name="score_against" min="0"></div>
            </div>
            <label>Formation</label>
            <input name="formation" placeholder="e.g. 4-3-3">
            <label>Key moments</label>
            <textarea name="key_moments" rows="2" placeholder="Goals, cards, subs, turning points"></textarea>
            <label>Notes</label>
            <textarea name="notes" rows="3"></textarea>
            <button type="submit">Save match</button>
          </form>
        </div>
        <div class="card">
          <h2>Match history</h2>
          <table><tr><th>Date</th><th>Opponent</th><th>Score</th><th>Competition</th></tr>{rows or '<tr><td colspan=4 class="muted">No matches logged yet.</td></tr>'}</table>
        </div>
        """
        return render("Matches", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/matches/<int:match_id>", methods=["GET", "POST"])
@login_required
def match_detail(match_id):
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        match = session.query(MatchReport).filter_by(id=match_id, team_id=team.id if team else -1).first()
        if not match:
            return redirect("/coach/matches")

        if request.method == "POST":
            match.formation = request.form.get("formation", "").strip() or None
            match.key_moments = request.form.get("key_moments", "").strip() or None
            match.notes = request.form.get("notes", "").strip() or None
            if request.form.get("generate_summary"):
                match.tactical_summary = _generate_tactical_summary(match)
            session.commit()

        body = f"""
        <div class="card">
          <h2>{esc(match.opponent)} — {match.match_date.strftime('%d %b %Y')}</h2>
          <p class="muted">
            {match.score_for if match.score_for is not None else '-'} : {match.score_against if match.score_against is not None else '-'}
            {' · ' + esc(match.competition) if match.competition else ''}
          </p>
          <form method="post">
            <label>Formation</label>
            <input name="formation" value="{esc(match.formation) if match.formation else ''}" placeholder="e.g. 4-3-3">
            <label>Key moments</label>
            <textarea name="key_moments" rows="3">{esc(match.key_moments) if match.key_moments else ''}</textarea>
            <label>Notes</label>
            <textarea name="notes" rows="4">{esc(match.notes) if match.notes else ''}</textarea>
            <label><input type="checkbox" name="generate_summary" value="1" style="width:auto; display:inline-block; margin-right:0.4rem;">Generate/regenerate AI tactical summary from the above</label>
            <button type="submit">Save</button>
          </form>
        </div>
        <div class="card">
          <h2>Tactical summary</h2>
          <p class="muted">Written by the AI from your notes above — not from independent video or tracking analysis.</p>
          {f'<p style="white-space:pre-line;">{esc(match.tactical_summary)}</p>' if match.tactical_summary else '<p class="muted">None yet — fill in some notes above and check the generate box.</p>'}
        </div>
        <p><a class="link" href="/coach/matches">&larr; All matches</a></p>
        """
        return render("Match", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# Club Finance
# ============================================================

@app.route("/coach/finance", methods=["GET", "POST"])
@login_required
def finance():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            amount_naira = float(request.form["amount"])
            session.add(FinanceEntry(
                team_id=team.id,
                entry_type=FinanceEntryType(request.form["entry_type"]),
                amount_kobo=round(amount_naira * 100),
                category=request.form.get("category", "").strip() or None,
                description=request.form.get("description", "").strip() or None,
                entry_date=datetime.strptime(request.form["entry_date"], "%Y-%m-%d").date(),
                created_by_user_id=user.id,
            ))
            session.commit()

        entries = (
            session.query(FinanceEntry).filter_by(team_id=team.id)
            .order_by(FinanceEntry.entry_date.desc()).all()
        )
        income = sum(e.amount_kobo for e in entries if e.entry_type == FinanceEntryType.INCOME)
        expense = sum(e.amount_kobo for e in entries if e.entry_type == FinanceEntryType.EXPENSE)

        rows = "".join(
            f'<tr><td>{e.entry_date.strftime("%d %b %Y")}</td>'
            f'<td>{"➕ Income" if e.entry_type == FinanceEntryType.INCOME else "➖ Expense"}</td>'
            f'<td>{esc(e.category) if e.category else "—"}</td><td>{naira(e.amount_kobo)}</td><td>{esc(e.description) if e.description else ""}</td></tr>'
            for e in entries
        )

        body = f"""
        <div class="grid">
          <div class="card stat"><div class="num">{naira(income)}</div><div class="label">Total income</div></div>
          <div class="card stat"><div class="num">{naira(expense)}</div><div class="label">Total expense</div></div>
          <div class="card stat"><div class="num">{naira(income - expense)}</div><div class="label">Balance</div></div>
        </div>
        <div class="card">
          <h2>Add an entry</h2>
          <form method="post">
            <label>Type</label>
            <select name="entry_type"><option value="income">Income</option><option value="expense">Expense</option></select>
            <label>Amount (₦)</label>
            <input type="number" step="0.01" name="amount" required>
            <label>Category</label>
            <input name="category" placeholder="e.g. Kit, Fees, Transport">
            <label>Date</label>
            <input type="date" name="entry_date" value="{date.today().isoformat()}">
            <label>Description</label>
            <input name="description">
            <button type="submit">Add entry</button>
          </form>
        </div>
        <div class="card">
          <h2>Ledger</h2>
          <table><tr><th>Date</th><th>Type</th><th>Category</th><th>Amount</th><th>Description</th></tr>{rows or '<tr><td colspan=5 class="muted">No entries yet.</td></tr>'}</table>
        </div>
        """
        return render("Finance", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# Equipment / Inventory
# ============================================================

@app.route("/coach/equipment", methods=["GET", "POST"])
@login_required
def equipment():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            session.add(EquipmentItem(
                team_id=team.id,
                name=request.form["name"].strip(),
                quantity=int(request.form.get("quantity") or 1),
                condition=EquipmentCondition(request.form.get("condition", "good")),
                notes=request.form.get("notes", "").strip() or None,
            ))
            session.commit()

        items = session.query(EquipmentItem).filter_by(team_id=team.id).order_by(EquipmentItem.name).all()
        rows = "".join(
            f'<tr><td>{esc(i.name)}</td><td>{i.quantity}</td>'
            f'<td><span class="badge {i.condition.value}">{i.condition.value.replace("_"," ")}</span></td>'
            f'<td>{esc(i.notes) if i.notes else ""}</td></tr>'
            for i in items
        )
        condition_opts = "".join(f'<option value="{c.value}">{c.value.replace("_"," ").title()}</option>' for c in EquipmentCondition)

        body = f"""
        <div class="card">
          <h2>Add equipment</h2>
          <form method="post">
            <label>Name</label>
            <input name="name" placeholder="e.g. Match balls" required>
            <label>Quantity</label>
            <input type="number" name="quantity" value="1" min="0">
            <label>Condition</label>
            <select name="condition">{condition_opts}</select>
            <label>Notes</label>
            <input name="notes">
            <button type="submit">Add item</button>
          </form>
        </div>
        <div class="card">
          <h2>Inventory</h2>
          <table><tr><th>Item</th><th>Qty</th><th>Condition</th><th>Notes</th></tr>{rows or '<tr><td colspan=4 class="muted">No equipment logged yet.</td></tr>'}</table>
        </div>
        """
        return render("Equipment", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# AI Scout (Phase 5)
# ============================================================

def _gather_player_context(session, membership: TeamMembership) -> str:
    """Pulls together everything already logged about a roster player into
    one text block for Claude to synthesize. No independent stats/tracking
    data exists to draw on -- this is deliberately just what the coach (and,
    if the player is a linked bot user, the player themself) has recorded."""
    lines = [f"Name: {membership.display_name()}"]

    if membership.player_user:
        p = membership.player_user
        if p.player_profile:
            pf = p.player_profile
            lines.append(f"Position: {pf.position or 'unknown'}, Age: {pf.age or 'unknown'}, "
                         f"Dominant foot: {pf.dominant_foot.value if pf.dominant_foot else 'unknown'}")
    else:
        lines.append("(Guest roster entry -- not a registered bot user, so no self-reported profile/plan data.)")

    notes = (
        session.query(PlayerNote).filter_by(membership_id=membership.id)
        .order_by(PlayerNote.created_at.desc()).limit(8).all()
    )
    lines.append(f"\nCoach's notes ({len(notes)} most recent):")
    lines += [f"- {n.created_at.strftime('%d %b %Y')}: {n.note_text}" for n in notes] or ["- none logged"]

    latest_medical = (
        session.query(MedicalRecord).filter_by(membership_id=membership.id)
        .order_by(MedicalRecord.updated_at.desc()).first()
    )
    lines.append(f"\nCurrent fitness status: {latest_medical.status.value if latest_medical else 'fit (no record logged)'}")

    total_sessions = session.query(AttendanceRecord).filter_by(membership_id=membership.id).count()
    present_sessions = session.query(AttendanceRecord).filter_by(membership_id=membership.id, present=True).count()
    if total_sessions:
        lines.append(f"Attendance: {present_sessions}/{total_sessions} training sessions ({present_sessions*100//total_sessions}%)")
    else:
        lines.append("Attendance: no sessions recorded yet")

    if membership.player_user_id:
        video_count = session.query(VideoAnalysis).filter_by(user_id=membership.player_user_id).count()
        lines.append(f"\nAI video analyses on file: {video_count}")
        if video_count:
            latest_video = (
                session.query(VideoAnalysis).filter_by(user_id=membership.player_user_id)
                .order_by(VideoAnalysis.created_at.desc()).first()
            )
            lines.append(f"Most recent video analysis ({latest_video.category.value}): {latest_video.analysis_text[:400]}")

        latest_plan = (
            session.query(DevelopmentPlan).filter_by(user_id=membership.player_user_id)
            .order_by(DevelopmentPlan.created_at.desc()).first()
        )
        if latest_plan:
            lines.append(f"\nMost recent AI development plan (excerpt): {latest_plan.plan_text[:300]}")

    return "\n".join(lines)


def _generate_scouting_report(session, membership: TeamMembership) -> str:
    if _client is None:
        return "(AI not configured — set ANTHROPIC_API_KEY to enable scouting reports.)"
    context_text = _gather_player_context(session, membership)
    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=550,
            system=config.SCOUTING_REPORT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context_text}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except APIError:
        return "(Couldn't generate a report right now — try again shortly.)"


def _parse_rating(report_text: str):
    """Best-effort extraction of the 1-10 rating from the report text for
    sorting/display purposes. Falls back to None rather than guessing."""
    import re
    match = re.search(r"POTENTIAL RATING:\s*(\d{1,2})", report_text, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        if 1 <= val <= 10:
            return val
    return None


@app.route("/coach/scouting")
@login_required
def scouting_home():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        members = [m for m in team.members if m.active]
        ranked = []
        for m in members:
            latest = (
                session.query(PlayerScoutingReport).filter_by(membership_id=m.id)
                .order_by(PlayerScoutingReport.created_at.desc()).first()
            )
            ranked.append((m, latest))
        ranked.sort(key=lambda pair: (pair[1].potential_rating if pair[1] and pair[1].potential_rating else -1), reverse=True)

        rows = "".join(
            f'<tr><td><a class="link" href="/coach/scouting/player/{m.id}">{esc(m.display_name())}</a></td>'
            f'<td>{(str(r.potential_rating) + "/10") if r and r.potential_rating else "—"}</td>'
            f'<td>{r.created_at.strftime("%d %b %Y") if r else "No report yet"}</td></tr>'
            for m, r in ranked
        )

        prospect_count = session.query(ScoutingProspect).filter_by(team_id=team.id).count()

        body = f"""
        <div class="notice">AI Scout synthesizes what you've already logged about each player
        (notes, medical status, attendance, video analyses, development plans) into a talent
        assessment. It has no independent statistics or tracking data — the rating reflects your
        own recorded inputs, not a scientific measurement.</div>
        <div class="card">
          <h2>Roster, ranked by latest potential rating</h2>
          <table><tr><th>Player</th><th>Rating</th><th>Last report</th></tr>{rows or '<tr><td colspan=3 class="muted">No players yet.</td></tr>'}</table>
        </div>
        <div class="card">
          <h2>Compare two players</h2>
          <p class="muted">Get a side-by-side AI comparison based on logged data.</p>
          <a class="link" href="/coach/scouting/compare">Open comparison tool &rarr;</a>
        </div>
        <div class="card">
          <h2>External prospects ({prospect_count})</h2>
          <p class="muted">Track players you're scouting who aren't on your roster.</p>
          <a class="link" href="/coach/scouting/prospects">Open prospects &rarr;</a>
        </div>
        """
        return render("Scouting", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/scouting/player/<int:membership_id>", methods=["GET", "POST"])
@login_required
def scouting_player(membership_id):
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        membership = session.query(TeamMembership).filter_by(id=membership_id, team_id=team.id if team else -1).first()
        if not membership:
            return redirect("/coach/scouting")

        if request.method == "POST":
            report_text = _generate_scouting_report(session, membership)
            session.add(PlayerScoutingReport(
                membership_id=membership.id, report_text=report_text,
                potential_rating=_parse_rating(report_text), created_by_user_id=user.id,
            ))
            session.commit()

        reports = (
            session.query(PlayerScoutingReport).filter_by(membership_id=membership.id)
            .order_by(PlayerScoutingReport.created_at.desc()).all()
        )

        history_html = "".join(
            f'<div class="card"><p class="muted">{r.created_at.strftime("%d %b %Y")}'
            f'{" — Rating: " + str(r.potential_rating) + "/10" if r.potential_rating else ""}</p>'
            f'<p style="white-space:pre-line;">{esc(r.report_text)}</p></div>'
            for r in reports
        )

        body = f"""
        <div class="card">
          <h2>{esc(membership.display_name())}</h2>
          <form method="post"><button type="submit">🔍 Generate new scouting report</button></form>
        </div>
        {history_html or '<p class="muted">No reports yet — generate the first one above.</p>'}
        <p><a class="link" href="/coach/scouting">&larr; Back to Scouting</a></p>
        """
        return render("Scouting Report", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/scouting/compare", methods=["GET", "POST"])
@login_required
def scouting_compare():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        members = [m for m in team.members if m.active]
        options = "".join(f'<option value="{m.id}">{esc(m.display_name())}</option>' for m in members)

        comparison_html = ""
        if request.method == "POST":
            id_a, id_b = int(request.form["player_a"]), int(request.form["player_b"])
            if id_a == id_b:
                comparison_html = '<div class="error">Pick two different players.</div>'
            else:
                m_a = session.query(TeamMembership).filter_by(id=id_a, team_id=team.id).first()
                m_b = session.query(TeamMembership).filter_by(id=id_b, team_id=team.id).first()
                if not m_a or not m_b:
                    comparison_html = '<div class="error">Couldn\'t find one of those players on your roster.</div>'
                elif _client is None:
                    comparison_html = '<div class="error">AI not configured — set ANTHROPIC_API_KEY.</div>'
                else:
                    context_text = (
                        f"PLAYER A ({m_a.display_name()}):\n{_gather_player_context(session, m_a)}\n\n"
                        f"PLAYER B ({m_b.display_name()}):\n{_gather_player_context(session, m_b)}"
                    )
                    try:
                        response = _client.messages.create(
                            model=config.CLAUDE_MODEL, max_tokens=550,
                            system=config.SCOUTING_COMPARISON_SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": context_text}],
                        )
                        result = "".join(b.text for b in response.content if b.type == "text").strip()
                    except APIError:
                        result = "Couldn't generate a comparison right now — try again shortly."
                    comparison_html = f'<div class="card"><h2>Comparison</h2><p style="white-space:pre-line;">{esc(result)}</p></div>'

        body = f"""
        <div class="card">
          <h2>Compare two players</h2>
          <form method="post">
            <label>Player A</label>
            <select name="player_a">{options}</select>
            <label>Player B</label>
            <select name="player_b">{options}</select>
            <button type="submit">Compare</button>
          </form>
        </div>
        {comparison_html}
        <p><a class="link" href="/coach/scouting">&larr; Back to Scouting</a></p>
        """
        return render("Compare Players", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/scouting/prospects", methods=["GET", "POST"])
@login_required
def scouting_prospects():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            session.add(ScoutingProspect(
                team_id=team.id,
                name=request.form["name"].strip(),
                position=request.form.get("position", "").strip() or None,
                age=int(request.form["age"]) if request.form.get("age") else None,
                source=request.form.get("source", "").strip() or None,
                notes=request.form.get("notes", "").strip() or None,
                manual_rating=int(request.form["manual_rating"]) if request.form.get("manual_rating") else None,
                created_by_user_id=user.id,
            ))
            session.commit()

        prospects = (
            session.query(ScoutingProspect).filter_by(team_id=team.id)
            .order_by(ScoutingProspect.updated_at.desc()).all()
        )
        rows = "".join(
            f'<tr><td><a class="link" href="/coach/scouting/prospects/{p.id}">{esc(p.name)}</a></td>'
            f'<td>{esc(p.position) if p.position else "—"}</td><td>{p.age or "—"}</td>'
            f'<td><span class="badge {p.status.value}">{p.status.value.replace("_"," ")}</span></td></tr>'
            for p in prospects
        )

        body = f"""
        <div class="card">
          <h2>Add a prospect</h2>
          <form method="post">
            <label>Name</label>
            <input name="name" required>
            <label>Position</label>
            <input name="position" placeholder="e.g. Central Midfielder">
            <label>Age</label>
            <input type="number" name="age" min="5" max="60">
            <label>Where seen</label>
            <input name="source" placeholder="e.g. Rivers United U15, friendly 08 Aug">
            <label>Your notes</label>
            <textarea name="notes" rows="3"></textarea>
            <label>Your gut rating (1-10, optional)</label>
            <input type="number" name="manual_rating" min="1" max="10">
            <button type="submit">Add prospect</button>
          </form>
        </div>
        <div class="card">
          <h2>Prospects ({len(prospects)})</h2>
          <table><tr><th>Name</th><th>Position</th><th>Age</th><th>Status</th></tr>{rows or '<tr><td colspan=4 class="muted">No prospects logged yet.</td></tr>'}</table>
        </div>
        <p><a class="link" href="/coach/scouting">&larr; Back to Scouting</a></p>
        """
        return render("Prospects", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/scouting/prospects/<int:prospect_id>", methods=["GET", "POST"])
@login_required
def scouting_prospect_detail(prospect_id):
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        prospect = session.query(ScoutingProspect).filter_by(id=prospect_id, team_id=team.id if team else -1).first()
        if not prospect:
            return redirect("/coach/scouting/prospects")

        if request.method == "POST":
            prospect.notes = request.form.get("notes", "").strip() or None
            prospect.status = ProspectStatus(request.form.get("status", "watching"))
            prospect.manual_rating = int(request.form["manual_rating"]) if request.form.get("manual_rating") else None
            prospect.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if request.form.get("generate_assessment"):
                if _client is None:
                    prospect.ai_assessment = "(AI not configured — set ANTHROPIC_API_KEY.)"
                else:
                    prompt = (
                        f"Name: {prospect.name}\nPosition: {prospect.position or 'unknown'}\n"
                        f"Age: {prospect.age or 'unknown'}\nSeen: {prospect.source or 'unspecified'}\n"
                        f"Coach's notes: {prospect.notes or 'none'}"
                    )
                    try:
                        response = _client.messages.create(
                            model=config.CLAUDE_MODEL, max_tokens=350,
                            system=config.SCOUTING_PROSPECT_SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        prospect.ai_assessment = "".join(b.text for b in response.content if b.type == "text").strip()
                    except APIError:
                        prospect.ai_assessment = "(Couldn't generate an assessment right now — try again shortly.)"
            session.commit()

        status_opts = "".join(
            f'<option value="{s.value}" {"selected" if s == prospect.status else ""}>{s.value.replace("_"," ").title()}</option>'
            for s in ProspectStatus
        )

        body = f"""
        <div class="card">
          <h2>{esc(prospect.name)}</h2>
          <p class="muted">{esc(prospect.position) if prospect.position else 'Position unknown'} · Age {prospect.age or '?'} · {esc(prospect.source) if prospect.source else 'source not logged'}</p>
          <form method="post">
            <label>Notes</label>
            <textarea name="notes" rows="4">{esc(prospect.notes) if prospect.notes else ''}</textarea>
            <label>Your gut rating (1-10)</label>
            <input type="number" name="manual_rating" min="1" max="10" value="{prospect.manual_rating or ''}">
            <label>Status</label>
            <select name="status">{status_opts}</select>
            <label><input type="checkbox" name="generate_assessment" value="1" style="width:auto; display:inline-block; margin-right:0.4rem;">Generate/regenerate AI assessment from notes above</label>
            <button type="submit">Save</button>
          </form>
        </div>
        <div class="card">
          <h2>AI assessment</h2>
          {f'<p style="white-space:pre-line;">{esc(prospect.ai_assessment)}</p>' if prospect.ai_assessment else '<p class="muted">None yet.</p>'}
        </div>
        <p><a class="link" href="/coach/scouting/prospects">&larr; All prospects</a></p>
        """
        return render("Prospect", body, team_name=team.name)
    finally:
        session.close()


# ============================================================
# Marketplace (Phase 7)
# ============================================================

@app.route("/coach/marketplace")
@login_required
def marketplace_home():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        my_opps = session.query(Opportunity).filter_by(team_id=team.id).order_by(Opportunity.created_at.desc()).all()
        pending_apps = (
            session.query(OpportunityApplication)
            .join(Opportunity, OpportunityApplication.opportunity_id == Opportunity.id)
            .filter(Opportunity.team_id == team.id, OpportunityApplication.status == ApplicationStatus.PENDING)
            .count()
        )
        my_listings = session.query(EquipmentListing).filter_by(team_id=team.id).count()
        interests_received = (
            session.query(EquipmentInterest)
            .join(EquipmentListing, EquipmentInterest.listing_id == EquipmentListing.id)
            .filter(EquipmentListing.team_id == team.id)
            .count()
        )

        rows = "".join(
            f'<tr><td><a class="link" href="/coach/marketplace/opportunities/{o.id}">{esc(o.title)}</a></td>'
            f'<td>{o.listing_type.value}</td><td><span class="badge {o.status.value}">{o.status.value}</span></td>'
            f'<td>{len(o.applications)}</td></tr>'
            for o in my_opps
        )

        body = f"""
        <div class="grid">
          <div class="card stat"><div class="num">{len(my_opps)}</div><div class="label">Opportunities posted</div></div>
          <div class="card stat"><div class="num">{pending_apps}</div><div class="label">Pending applications</div></div>
          <div class="card stat"><div class="num">{my_listings}</div><div class="label">Equipment listings</div></div>
          <div class="card stat"><div class="num">{interests_received}</div><div class="label">Equipment interest received</div></div>
        </div>
        <div class="card">
          <h2>Post an opportunity</h2>
          <a class="link" href="/coach/marketplace/opportunities/new">+ New Trial / Job / Scholarship / Internship / Sponsorship listing &rarr;</a>
        </div>
        <div class="card">
          <h2>My opportunities</h2>
          <table><tr><th>Title</th><th>Type</th><th>Status</th><th>Applicants</th></tr>{rows or '<tr><td colspan=4 class="muted">Nothing posted yet.</td></tr>'}</table>
        </div>
        <div class="card">
          <h2>Equipment marketplace</h2>
          <p class="muted">List surplus kit for other teams, or browse what's available.</p>
          <a class="link" href="/coach/marketplace/equipment">Open Equipment Marketplace &rarr;</a>
        </div>
        """
        return render("Marketplace", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/marketplace/opportunities/new", methods=["GET", "POST"])
@login_required
def marketplace_new_opportunity():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            deadline = request.form.get("deadline") or None
            new_opp = Opportunity(
                team_id=team.id, posted_by_user_id=user.id,
                listing_type=ListingType(request.form["listing_type"]),
                title=request.form["title"].strip(),
                description=request.form["description"].strip(),
                location=request.form.get("location", "").strip() or None,
                age_min=int(request.form["age_min"]) if request.form.get("age_min") else None,
                age_max=int(request.form["age_max"]) if request.form.get("age_max") else None,
                deadline=datetime.strptime(deadline, "%Y-%m-%d").date() if deadline else None,
            )
            session.add(new_opp)
            session.commit()
            return redirect(f"/coach/marketplace/opportunities/{new_opp.id}")

        type_opts = "".join(f'<option value="{t.value}">{t.value.title()}</option>' for t in ListingType)
        body = f"""
        <div class="card">
          <h2>New opportunity</h2>
          <form method="post">
            <label>Type</label>
            <select name="listing_type">{type_opts}</select>
            <label>Title</label>
            <input name="title" placeholder="e.g. U15 Trial — Left Back" required>
            <label>Description</label>
            <textarea name="description" rows="5" required></textarea>
            <label>Location</label>
            <input name="location" placeholder="e.g. Lagos, NG">
            <div style="display:flex; gap:1rem;">
              <div style="flex:1;"><label>Min age</label><input type="number" name="age_min" min="5" max="60"></div>
              <div style="flex:1;"><label>Max age</label><input type="number" name="age_max" min="5" max="60"></div>
            </div>
            <label>Deadline</label>
            <input type="date" name="deadline">
            <button type="submit">Post listing</button>
          </form>
        </div>
        <p><a class="link" href="/coach/marketplace">&larr; Back to Marketplace</a></p>
        """
        return render("New Opportunity", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/marketplace/opportunities/<int:opportunity_id>", methods=["GET", "POST"])
@login_required
def marketplace_opportunity_detail(opportunity_id):
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        opp = session.query(Opportunity).filter_by(id=opportunity_id, team_id=team.id if team else -1).first()
        if not opp:
            return redirect("/coach/marketplace")

        if request.method == "POST":
            action = request.form.get("action")
            if action == "toggle_status":
                opp.status = ListingStatus.CLOSED if opp.status == ListingStatus.OPEN else ListingStatus.OPEN
                session.commit()
            elif action == "review_application":
                app_id = int(request.form["application_id"])
                new_status = request.form["new_status"]
                # Never trust an ID from form data alone -- confirm this
                # application actually belongs to the opportunity we already
                # scoped to this coach's own team above.
                application = session.query(OpportunityApplication).filter_by(id=app_id, opportunity_id=opp.id).first()
                if application:
                    application.status = ApplicationStatus(new_status)
                    application.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    session.commit()
                    applicant = session.query(User).filter_by(id=application.applicant_user_id).first()
                    if applicant:
                        notifications.send_telegram_message(
                            applicant.telegram_id,
                            f"Your application for \"{opp.title}\" ({team.name}) is now: {new_status}.",
                        )

        applications = (
            session.query(OpportunityApplication).filter_by(opportunity_id=opp.id)
            .order_by(OpportunityApplication.applied_at.desc()).all()
        )
        status_opts_html = "".join(f'<option value="{s.value}">{s.value.title()}</option>' for s in ApplicationStatus)
        app_rows = "".join(f"""
            <tr>
              <td>{esc(a.applicant.display_name())}</td>
              <td>{esc(a.note) if a.note else '—'}</td>
              <td><span class="badge {a.status.value}">{a.status.value}</span></td>
              <td>
                <form method="post" style="display:flex; gap:0.4rem; margin:0;">
                  <input type="hidden" name="action" value="review_application">
                  <input type="hidden" name="application_id" value="{a.id}">
                  <select name="new_status" style="width:auto;">{status_opts_html}</select>
                  <button type="submit">Update</button>
                </form>
              </td>
            </tr>
        """ for a in applications)

        toggle_label = "Close listing" if opp.status == ListingStatus.OPEN else "Reopen listing"
        body = f"""
        <div class="card">
          <h2>{esc(opp.title)}</h2>
          <p class="muted">{opp.listing_type.value.title()} · <span class="badge {opp.status.value}">{opp.status.value}</span></p>
          <p style="white-space:pre-line;">{esc(opp.description)}</p>
          <form method="post"><input type="hidden" name="action" value="toggle_status">
            <button class="secondary" type="submit">{toggle_label}</button></form>
        </div>
        <div class="card">
          <h2>Applicants ({len(applications)})</h2>
          <table><tr><th>Applicant</th><th>Note</th><th>Status</th><th>Update</th></tr>{app_rows or '<tr><td colspan=4 class="muted">No applications yet.</td></tr>'}</table>
        </div>
        <p><a class="link" href="/coach/marketplace">&larr; Back to Marketplace</a></p>
        """
        return render("Opportunity", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/marketplace/equipment", methods=["GET", "POST"])
@login_required
def marketplace_equipment():
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        if not team:
            return redirect("/coach/")

        if request.method == "POST":
            price = request.form.get("price")
            session.add(EquipmentListing(
                team_id=team.id, created_by_user_id=user.id,
                title=request.form["title"].strip(),
                description=request.form.get("description", "").strip() or None,
                condition=EquipmentCondition(request.form.get("condition", "good")),
                price_kobo=round(float(price) * 100) if price else None,
            ))
            session.commit()

        my_listings = session.query(EquipmentListing).filter_by(team_id=team.id).order_by(EquipmentListing.created_at.desc()).all()
        other_listings = (
            session.query(EquipmentListing)
            .filter(EquipmentListing.team_id != team.id, EquipmentListing.status == EquipmentListingStatus.AVAILABLE)
            .order_by(EquipmentListing.created_at.desc()).limit(20).all()
        )

        condition_opts = "".join(f'<option value="{c.value}">{c.value.title()}</option>' for c in EquipmentCondition)

        my_rows = "".join(
            f'<tr><td>{esc(l.title)}</td><td><span class="badge {l.condition.value}">{l.condition.value}</span></td>'
            f'<td>{naira(l.price_kobo) if l.price_kobo else "Free/Trade"}</td>'
            f'<td><span class="badge {l.status.value}">{l.status.value}</span></td>'
            f'<td>{len(l.interests)}</td></tr>'
            for l in my_listings
        )
        other_rows = "".join(
            f'<tr><td>{esc(l.title)}</td><td>{esc(l.team.name)}</td><td><span class="badge {l.condition.value}">{l.condition.value}</span></td>'
            f'<td>{naira(l.price_kobo) if l.price_kobo else "Free/Trade"}</td>'
            f'<td><form method="post" action="/coach/marketplace/equipment/{l.id}/interest" style="margin:0;">'
            f'<button type="submit">Express Interest</button></form></td></tr>'
            for l in other_listings
        )

        body = f"""
        <div class="card">
          <h2>List equipment for other teams</h2>
          <form method="post">
            <label>Item</label>
            <input name="title" placeholder="e.g. 10x training bibs (size M)" required>
            <label>Description</label>
            <textarea name="description" rows="2"></textarea>
            <label>Condition</label>
            <select name="condition">{condition_opts}</select>
            <label>Price (₦, leave blank for free/trade)</label>
            <input type="number" step="0.01" name="price">
            <button type="submit">List item</button>
          </form>
        </div>
        <div class="card">
          <h2>My listings</h2>
          <table><tr><th>Item</th><th>Condition</th><th>Price</th><th>Status</th><th>Interest</th></tr>{my_rows or '<tr><td colspan=5 class="muted">Nothing listed yet.</td></tr>'}</table>
        </div>
        <div class="card">
          <h2>Available from other teams</h2>
          <table><tr><th>Item</th><th>Team</th><th>Condition</th><th>Price</th><th></th></tr>{other_rows or '<tr><td colspan=5 class="muted">Nothing available right now.</td></tr>'}</table>
        </div>
        <p><a class="link" href="/coach/marketplace">&larr; Back to Marketplace</a></p>
        """
        return render("Equipment Marketplace", body, team_name=team.name)
    finally:
        session.close()


@app.route("/coach/marketplace/equipment/<int:listing_id>/interest", methods=["POST"])
@login_required
def marketplace_equipment_interest(listing_id):
    session = SessionLocal()
    try:
        user, team = current_user_and_team(session)
        listing = session.query(EquipmentListing).filter_by(id=listing_id).first()
        if not listing or not team or listing.team_id == team.id:
            return redirect("/coach/marketplace/equipment")

        # Bug found in audit: previously this had no status check at all, so
        # a listing already RESERVED or SOLD could keep collecting new
        # interest from other teams. Also skip if this team already
        # registered interest, rather than creating duplicate rows.
        if listing.status != EquipmentListingStatus.AVAILABLE:
            return redirect("/coach/marketplace/equipment")
        dupe = session.query(EquipmentInterest).filter_by(
            listing_id=listing.id, interested_team_id=team.id
        ).first()
        if dupe:
            return redirect("/coach/marketplace/equipment")

        session.add(EquipmentInterest(
            listing_id=listing.id, interested_team_id=team.id, interested_by_user_id=user.id,
        ))
        listing.status = EquipmentListingStatus.RESERVED
        session.commit()

        lister = session.query(User).filter_by(id=listing.created_by_user_id).first()
        if lister:
            notifications.send_telegram_message(
                lister.telegram_id,
                f"🎒 {team.name} is interested in your listing \"{listing.title}\". "
                "Check your Coach Dashboard for their contact details.",
            )
        return redirect("/coach/marketplace/equipment")
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5002, debug=False)
