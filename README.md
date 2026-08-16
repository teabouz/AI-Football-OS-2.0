# AI Football OS — Telegram Bot (Phase 1 + Phase 2 + Phase 3 + Phase 4 + Phase 5 + Phase 6 + Phase 7)

Built from the master prompt roadmap.

> **Fixed:** `handlers/subscription.py: mark_user_premium()` had a bug where
> checking `user.is_premium()` *after* setting the tier to `PREMIUM` made a
> first-time upgrade (no prior `subscription_expires_at`) look already-active,
> so the code tried `None + timedelta(...)` and crashed. Every first Premium
> payment — via the Paystack webhook or the "I've Paid" button — would have
> hit this. Fixed by capturing `is_premium()` before flipping the tier.
> Verified against first-time upgrade, renewal (extends existing expiry), and
> lapsed-then-renews (resets from today) cases.

> **Fixed (security):** a class of IDOR (Insecure Direct Object Reference)
> bug — an ID taken from Telegram `callback_data` or a web form, used to look
> up and mutate a database record without confirming the requesting user
> actually owns it. `callback_data` and form fields are client-controlled;
> trusting an ID from either without an ownership check means any user can
> forge one referencing someone else's data. Two instances
> (`handlers/team.py: remove_player`, `handlers/attendance.py:
> toggle_attendance`) were caught and fixed externally; auditing every other
> handler with the same shape turned up five more: `handlers/goals.py:
> mark_goal_done` (any user could complete another user's goal),
> `handlers/payments.py: refresh_status` (a payment reference didn't verify
> it belonged to the caller before crediting Premium — low practical risk
> given the reference's entropy and private delivery, but the same
> unverified-ownership shape, fixed for defense in depth), and three Flask
> routes in `coach_dashboard.py` (`/coach/notes`, `/coach/medical`, and
> opportunity application review — the last of which had a subtler version
> where even the *legitimate* owner of one opportunity could review an
> application belonging to a completely different one). Every fix follows
> the same pattern: scope the lookup with a `WHERE owner = current_user`
> condition, not just `WHERE id = <value>`. All seven were reproduced as
> failing exploits against the vulnerable code, confirmed fixed, and
> confirmed to not break the legitimate owner's normal use, before being
> adopted — see the design notes below for the general principle.

- **Phase 1 (Foundation):** authentication, player/coach/academy profiles, a
  live AI Coach (Claude), a subscription foundation with a free daily quota,
  and an admin view — both inside Telegram and as a small web dashboard.
- **Phase 2 (Premium AI Coach):** personalized development plans, goal
  tracking, an AI Habit Coach with streaks, switchable coaching personas
  (Mindset / Leadership / Confidence / Recovery), weekly performance reports,
  and real payment collection via Paystack.
- **Phase 3 (Coach Dashboard & Club Management):** team rosters, quick
  in-bot attendance, and a companion web Coach Dashboard for training
  session planning (with optional AI-generated plans), player notes,
  medical/fitness tracking, match reports, a club finance ledger, and
  equipment inventory.
- **Phase 4 (AI Video Analysis):** players/coaches send a training, match,
  penalty, free-kick, or goalkeeping clip and get back a structured Claude
  vision review — plus an AI-assisted tactical summary on match reports,
  generated from the coach's own notes.
- **Phase 5 (AI Scout):** synthesizes everything already logged about a
  roster player (notes, medical history, attendance, video analyses,
  development plans) into a talent report with a potential rating, a
  side-by-side player comparison tool, and a lightweight external-prospect
  tracker for scouting outside the roster.
- **Phase 6 (Learning Academy):** 8 courses (Coaching, Nutrition, Sports
  Psychology, Sports Science, Laws of the Game, Refereeing, Leadership,
  Career Development), 4 lessons each, with AI-generated content and
  quizzes cached on first access, progress tracking, and Premium-gated
  completion certificates.
- **Phase 7 (Marketplace):** an opportunity board (trials, coaching jobs,
  scholarships, internships, sponsorship-seeking) that coaches/academies
  post and players/coaches browse and apply to, plus a team-to-team
  equipment marketplace.

> **Scope note on Phase 4** — the roadmap's Phase 5/6 describe two different
> things: (a) reviewing footage for technique feedback, and (b) automated
> match intelligence like heat maps, expected goals, and passing networks.
> (a) is genuinely built here: extract still frames from a clip, send them to
> Claude with vision, get a coaching write-up. (b) requires real computer-
> vision infrastructure — player/ball tracking, pose estimation, pitch
> homography — which is a different kind of project (dedicated ML models,
> GPU inference, likely a separate service) than something that bolts onto a
> Telegram bot via an LLM API. Rather than fake heat maps and xG numbers with
> no real positional data behind them, this phase gives coaches an
> AI-assisted tactical summary written from their own match notes instead —
> useful, honestly labeled, and a real foundation to build real tracking on
> top of later if that infrastructure investment makes sense.

> **Scope note on Phase 5** — the roadmap's "Player Ranking" and "Potential
> Rating" could easily be read as implying real scouting-grade statistics
> (goals/assists per game, physical testing data, etc.), none of which this
> platform collects. What's built instead is honest about that: AI Scout
> synthesizes the coach's own qualitative inputs (notes, medical history,
> attendance, video analysis, development plans) into a structured report,
> and both the on-screen copy and the system prompt itself are explicit that
> the rating reflects those logged inputs, not an independent or scientific
> measurement. It's a genuinely useful way to pull scattered observations
> into one coherent view — not a claim to have built real scouting
> analytics from data that doesn't exist.

> **Scope note on Phase 7 — this is the one worth reading closely.** The
> roadmap's Marketplace category list includes "Players" as something to be
> browsed alongside Jobs, Trials, and Equipment. A platform where coaches
> can passively browse a directory of players — many of whom are minors,
> given this is built around a youth academy — is a real child-safety
> concern, not a minor implementation detail. So this phase deliberately
> does **not** build that. Instead:
> - Coaches/academies post opportunities (trials, jobs, scholarships,
>   internships, sponsorship-seeking) — the institutional, "offering" side.
> - Players (or coaches, for job listings) **choose** to apply — nothing
>   about a person is ever visible to a poster unless they actively opted
>   in by applying, and even then a poster only sees what the applicant
>   wrote in their note, not their full profile.
> - There is no search, no filter-by-age-and-position browsing, no passive
>   directory of players anywhere in this codebase.
>
> This covers the roadmap's real intent (connecting players with
> opportunities) through a consent-based, applicant-initiated flow instead
> of a browsable directory. If a genuine scouting-marketplace with
> passive player discovery is wanted later, that needs real child-safety
> infrastructure around it first — age-appropriate consent flows, guardian
> involvement for minors, and real moderation — not just a database table
> and a browse view. That's a deliberate scope boundary, not an oversight.

## What's included

| Deliverable (from the roadmap) | Where it lives |
|---|---|
| Authentication / User Registration | `handlers/start.py` (role-based onboarding conversation) |
| Player / Coach / Academy Profile | `models.py`, `handlers/profile.py` |
| Database | `database.py`, `models.py` (SQLite by default, swap to Postgres via `DATABASE_URL`) |
| AI Chat | `handlers/ai_chat.py` (Claude API, `claude-sonnet-5`) |
| Subscription Module | `handlers/subscription.py` (free/premium tiers, daily quota, upgrade UI, premium gating) |
| Admin Dashboard | `admin_dashboard.py` (Flask, browser-based) + `/admin` command in-bot |
| Telegram Bot | `main.py` |
| **Personalized Development Plan** | `handlers/plan.py` — AI-generated 4-week plan from the player/coach/academy profile |
| **Goal Tracking / Weekly/Monthly/Season Objectives** | `handlers/goals.py`, `/addgoal` |
| **AI Habit Coach** | `handlers/checkin.py`, `/checkin` — sleep, hydration, training, mood + streaks |
| **Mindset / Leadership / Confidence / Recovery Coaching** | `handlers/coaching_modes.py` — switches the AI Coach's system prompt |
| **Performance Reports** | `handlers/reports.py` — AI-written weekly summary from goals + check-ins + chat activity |
| **Payments (Paystack)** | `handlers/payments.py`, `payments/paystack.py`, `payment_server.py` |
| **Unlimited AI Conversations** | already enforced in `handlers/ai_chat.py` via `user.is_premium()` |
| **Team / Roster Management** | `handlers/team.py` — `/createteam`, `/addplayer`, `/roster` |
| **Attendance** | `handlers/attendance.py`, `/attendance` — tap-to-toggle checklist |
| **Training Session Planning + Session Evaluation** | `coach_dashboard.py` → Sessions (optional AI-generated plan) |
| **Player Notes** | `coach_dashboard.py` → Notes (coach-only, never shown to the player) |
| **Medical / Fitness Monitoring** | `coach_dashboard.py` → Medical (append-only status history) |
| **Match Reports** | `coach_dashboard.py` → Matches |
| **Club Finance** | `coach_dashboard.py` → Finance (income/expense ledger) |
| **Equipment / Inventory** | `coach_dashboard.py` → Equipment |
| **Communication** | `handlers/broadcast.py`, `/broadcast <message>` — messages the whole roster |
| **AI Video Analysis** | `handlers/video.py`, `media/video_frames.py`, `/analyzevideo`, `/videos` |
| **AI Match Analyst (tactical summary)** | `coach_dashboard.py` → Matches → match detail page |
| **Talent Identification / Player Ranking / Potential Rating** | `coach_dashboard.py` → Scouting (per-player reports, ranked by rating) |
| **Player Comparison** | `coach_dashboard.py` → Scouting → Compare |
| **Recruitment Reports / Scholarship & Trial Recommendations** | `coach_dashboard.py` → Scouting → Prospects (external, not-yet-rostered players) |
| **Courses / Certificates (Coaching, Nutrition, Sports Psychology, Sports Science, Laws of Football, Refereeing, Leadership, Career Development)** | `academy_curriculum.py`, `handlers/academy.py`, `media/certificate.py`, `/academy` |
| **Jobs / Trials / Scholarships / Internships / Sponsorship (Marketplace)** | `handlers/marketplace.py` (browse/apply), `coach_dashboard.py` → Marketplace (post/manage applicants) |
| **Equipment (Marketplace)** | `coach_dashboard.py` → Marketplace → Equipment (list, browse, express interest) |

## Setup

1. **Get a bot token**: message [@BotFather](https://t.me/BotFather) on
   Telegram, run `/newbot`, follow the prompts, copy the token.
2. **Get a Claude API key**: from [console.anthropic.com](https://console.anthropic.com) → API Keys.
3. **Get your Telegram numeric ID** (to make yourself an admin): message
   [@userinfobot](https://t.me/userinfobot).
4. Copy the environment template and fill it in:
   ```bash
   cp .env.example .env
   # edit .env with your values
   ```
5. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
6. Run the bot:
   ```bash
   python main.py
   ```
   This also seeds the Learning Academy's 8 courses / 32 lessons into the
   database automatically on every startup (idempotent — safe to restart
   as often as you like, won't duplicate or touch already-generated content).
7. (Optional, separate terminal) Run the admin dashboard:
   ```bash
   python admin_dashboard.py
   # open http://localhost:5000
   ```
8. (Optional, separate terminal) Run the Coach Dashboard web app:
   ```bash
   python coach_dashboard.py
   # a coach/academy account opens it via /dashboard in the bot, not a fixed URL
   ```

> **Note:** This code was built and syntax/logic-tested in a sandboxed
> environment that cannot reach `api.telegram.org`, so the live Telegram
> connection itself hasn't been exercised end-to-end. The database layer, all
> handler wiring, and the Application build were verified directly. Run it
> with a real bot token on your own machine or server to go live — if
> anything doesn't behave as expected, send me the error and I'll fix it.

## Paystack setup (Phase 2 payments)

1. Create a [Paystack](https://paystack.com) account and grab your **test
   secret key** (`sk_test_...`) from Settings → API Keys & Webhooks.
2. Put it in `.env` as `PAYSTACK_SECRET_KEY`.
3. For local testing, expose port 5001 publicly. If [ngrok](https://ngrok.com)
   works on your machine:
   ```bash
   ngrok http 5001
   ```
   If ngrok crashes or won't install (seen on some older macOS/Intel
   setups), an SSH tunnel needs no extra install:
   ```bash
   ssh -R 80:localhost:5001 nokey@localhost.run
   ```
   Either way, copy the `https://...` URL it gives you into `.env` as `PUBLIC_BASE_URL`.
4. In the Paystack dashboard, set your webhook URL to
   `{PUBLIC_BASE_URL}/paystack/webhook`.
5. Run the payment server alongside the bot:
   ```bash
   python payment_server.py
   ```

**You don't strictly need the webhook to test end-to-end** — the bot's
"✅ I've Paid — Refresh" button verifies directly with Paystack's API, so you
can test the whole upgrade flow with just `python main.py` running. The
webhook is what makes upgrades happen automatically in production without the
user needing to tap that button.

Use [Paystack's test cards](https://paystack.com/docs/payments/test-payments/)
to simulate a real payment while `PAYSTACK_SECRET_KEY` is a test key.

## Coach Dashboard (Phase 3)

The web Coach Dashboard (`coach_dashboard.py`) has no separate login screen —
a coach/academy account runs `/dashboard` in the bot, gets a one-time link
(valid 15 minutes), and that logs them into a signed session. It runs on
port 5002 by default. Set a real `FLASK_SECRET_KEY` in `.env` before running
this anywhere but your own machine (a random one-liner is in `.env.example`).

### Making the dashboard reachable from Telegram

`/dashboard` builds its link from `DASHBOARD_BASE_URL` (a **separate**
setting from payment's `PUBLIC_BASE_URL` above — they're two different
Flask processes on two different ports, and each tunnel gives you a
different URL). The default, `http://127.0.0.1:5002`, only opens in a
browser on the same computer the bot is running on — Telegram on a phone
can never reach `localhost`. If `DASHBOARD_BASE_URL` is left local-only,
`/dashboard` still works for testing in your own browser, but the bot sends
the link as plain text with a warning instead of a tappable button (a
button pointing at an address nobody else can reach isn't useful, and
avoids Telegram rejecting it outright).

To make it reachable from a real device, expose port 5002 publicly and put
that HTTPS URL in `.env` as `DASHBOARD_BASE_URL`. A few ways to do that:

- **ngrok** (if it runs on your machine): `ngrok http 5002`, then copy the
  `https://....ngrok-free.app` URL it prints.
- **SSH tunnel** (no extra install, works when ngrok/cloudflared don't —
  e.g. on some older macOS/Intel setups): pick one —
  ```bash
  ssh -R 80:localhost:5002 nokey@localhost.run
  ssh -R 80:localhost:5002 serveo.net
  ssh -R 80:localhost:5002 a.pinggy.io
  ```
  Each prints a public `https://...` URL — copy it into `.env`.
- **A real deployment** (e.g. two Railway services from this repo, one for
  the bot and one for the dashboard, sharing a Postgres add-on): once
  `coach_dashboard.py` is deployed as its own service, use its real HTTPS
  domain here instead of a tunnel.

Then restart the bot so it picks up the new `DASHBOARD_BASE_URL`.

**Getting started as a coach/academy:**
1. `/start` and register as Coach or Academy
2. `/createteam AbleGod FC U15`
3. `/addplayer @someusername` (if they're on the bot) or `/addplayer Chidi Okonkwo` (guest, not on the bot yet)
4. `/attendance` on training days — tap names to mark present
5. `/dashboard` for everything else: training plans, notes, medical status, match reports, finance, equipment

This is scoped as a lightweight pilot tool (one team per coach account, no
CSRF tokens on forms) — solid for AbleGod FC-scale usage, but add CSRF
protection and proper audit logging before opening it up more broadly.

## Video Analysis (Phase 4)

Requires `ffmpeg` and `ffprobe` on the server's PATH (system packages, not
pip — see `requirements.txt` for install commands). If they're missing, the
bot will tell the person analyzing a clip exactly what's wrong rather than
failing silently.

**How it works:** `/analyzevideo` → pick a category → send a video (under
`MAX_VIDEO_MB`, default 20MB — Telegram's standard bot API can't download
anything bigger without a self-hosted Bot API server) → the bot pulls 6
evenly-spaced still frames with `ffmpeg`, sends them to Claude with vision,
and stores + returns the write-up. `/videos` shows history.

This reviews **stills, not motion** — the system prompt
(`config.VIDEO_ANALYSIS_SYSTEM_PROMPT`) explicitly tells Claude to comment
on what's visible in the frames rather than claim to see continuous
movement it can't actually observe. It's a real, useful second opinion on
technique and body positioning — not a replacement for a coach watching the
full clip.

## Learning Academy (Phase 6)

8 courses, 4 lessons each — structure is curated by hand in
`academy_curriculum.py` (so topic coverage is deliberate, not AI-improvised),
but each lesson's actual text and 3-question quiz are generated by Claude
**the first time anyone opens it**, then cached on that `Lesson` row and
reused for every user after that. One generation per lesson, ever — not one
per user, which keeps the cost flat regardless of how many people use it.

**Getting started:** `/academy` → pick a course → pick a lesson → read →
take the quiz → repeat for all lessons in a course → the bot offers
🎓 Get Certificate. Lessons and quizzes are **free for everyone** (matching
the roadmap's own free tier, which includes basic lessons/quizzes).
**Certificates are a Premium perk** — same freemium pattern as course
platforms that let you audit free and pay for the credential. Certificate
images are drawn locally with Pillow (no external service, no template
files) and sent as a Telegram photo; re-requesting one reuses the same
certificate record rather than issuing a duplicate.

Nutrition and sports-science lessons are explicitly instructed to stay at
general-education level — no specific calorie/macro targets or dosages —
and to recommend a professional for individual guidance, same guardrail
philosophy as the rest of the bot's health-adjacent content.

## Marketplace (Phase 7)

**Opportunity board** (`/marketplace` in the bot to browse and apply; Coach
Dashboard → Marketplace to post and manage applicants):
- Coaches/academies post Trials, Jobs, Scholarships, Internships, or
  Sponsorship-seeking listings with a title, description, location, age
  range, and deadline.
- Players (or coaches, for Job listings) browse by category and apply with
  a short note. Applying notifies the poster instantly — this happens
  inside the bot process, so it's a direct `context.bot.send_message` call.
- The poster reviews applicants and updates status (Reviewed / Accepted /
  Rejected) from the dashboard, which notifies the applicant — this crosses
  from the Flask process to Telegram, so it goes through
  `notifications.send_telegram_message()`, a small synchronous wrapper
  around Telegram's HTTP API (same pattern as Paystack's sync verification
  in `payments/paystack.py`). Best-effort: a failed notification never
  blocks the underlying action.

**Equipment marketplace** (Coach Dashboard → Marketplace → Equipment):
teams list surplus kit (free, trade, or priced) for other teams to browse;
expressing interest notifies the lister the same way. This is separate from
each team's own private inventory tracker (Phase 3's Equipment page) — a
team chooses what to list, rather than its whole stock being automatically
public.

**No passive player browsing anywhere** — see the scope note near the top
of this README for why, and how the applicant-initiated flow above covers
the roadmap's intent responsibly instead.

## Database Migrations

Every app process (`main.py`, `coach_dashboard.py`, `admin_dashboard.py`,
`payment_server.py`) still calls `init_db()` on startup, which uses
SQLAlchemy's `create_all()` — zero-config, creates any missing tables, and
is exactly right for local development, running the test suite, or a fresh
install with nothing to lose yet. **This is unchanged and remains the
default.**

What `create_all()` can't safely do is evolve a schema that already has
real data: it only creates tables that don't exist yet, never alters an
existing one. Add a new column to a model after AbleGod FC has real players
in the database, and `create_all()` will silently do nothing — the column
just won't be there until someone notices.

That's what [Alembic](https://alembic.sqlalchemy.org/) (`migrations/`) is
for. Once there's real data to protect, use it instead of relying on
`init_db()` picking up schema changes:

```bash
# After pulling an update that changed models.py, before restarting the app:
alembic upgrade head
```

**To make a schema change yourself:** edit `models.py`, then:
```bash
alembic revision --autogenerate -m "describe the change"
# review the generated file in migrations/versions/ -- autogenerate is very
# good but not infallible, especially for renames (it may see a rename as
# a drop + add) or complex constraint changes
alembic upgrade head
```

The included `migrations/versions/d67dc0c66fa3_baseline_schema.py` is the
full current schema as of Phase 7 (33 tables) — verified to produce an
identical schema to `init_db()`'s `create_all()`, and verified end-to-end
that applying an incremental migration on top of a database with real data
in it preserves that data (tested by adding a column to a populated table
and confirming existing rows survive with the new column correctly null).

`database.py` also exposes `run_migrations()` if you'd rather call this
from Python (e.g. in a deploy script) than shell out to the `alembic` CLI.

## Bot commands

- `/start` — register (player/coach/academy) or view your profile if already registered
- `/menu` — open the main menu
- `/profile` — view your profile
- `/status` — subscription plan + remaining free questions today
- `/ask <question>` — ask the AI Coach directly
- `/addgoal <goal>` — add a goal (Premium)
- `/checkin` — log today's sleep, hydration, training & mood (Premium)
- `/analyzevideo` — get AI feedback on a training/match clip (Premium)
- `/videos` — view your past video analyses (Premium)
- `/academy` — browse Learning Academy courses (free lessons & quizzes; certificates are Premium)
- `/marketplace` — browse and apply to trials, jobs, scholarships, internships
- `/admin` — stats (restricted to `ADMIN_TELEGRAM_IDS`)
- Any plain message is treated as a question to the AI Coach

**Coach / Academy accounts:**
- `/createteam <name>` — set up your team
- `/addplayer @username` or `/addplayer Name` — add to your roster
- `/roster` — view your roster (with remove buttons)
- `/attendance` — quick tap-to-toggle attendance for today
- `/broadcast <message>` — message everyone on your roster who's on the bot
- `/dashboard` — get a link to the full web Coach Dashboard

🏆 **Premium Coaching** (from `/menu`) opens: Development Plan, Goals,
Daily Check-in, Coaching Modes, Performance Report, Video Analysis, Video History.

🏫 **Coach Dashboard** (from `/menu`) opens: Roster, Attendance, Scouting
Reports (deep-links straight into the web dashboard's Scouting section),
the general web dashboard link, and broadcast instructions.

## Design notes

- **Every ID from a callback button or a form field is untrusted input**:
  Telegram `callback_data` and HTML form fields are both round-tripped
  through the client, which means a user can submit any value there,
  not just the one a button was rendered with. Every handler that takes an
  ID this way and uses it to look up a record for mutation scopes the
  query to the current user's own ownership (`WHERE id = X AND
  owner_user_id = current_user.id`, or the equivalent join through a team)
  — never a bare `filter_by(id=X)`. This isn't automatically enforced by a
  framework here, so it's a pattern to keep applying by hand to any new
  handler: if it takes an ID and writes to the DB, ask "whose record is
  this, and did I check?"
- **SQLite → Postgres**: everything goes through SQLAlchemy, so moving to
  Postgres later is just changing `DATABASE_URL` — no code changes.
- **Subscription is a foundation, not a full billing system**: the roadmap
  correctly scopes Paystack/Flutterwave checkout to Phase 2. This build has
  the tiers, quota enforcement, and upgrade UI ready so payment integration
  is a drop-in (`handlers/subscription.py: mark_user_premium()` is the hook
  a payment webhook should call).
- **AI Coach memory**: currently a rolling window of the last 10 messages per
  user, stored in `chat_messages`. The roadmap's dedicated "Memory Agent" is a
  natural Phase 2/3 upgrade (e.g. summarizing older history instead of just
  windowing it).
- **Single Claude call, no agent orchestration yet**: Phase 1 uses one system
  prompt tuned as a general football coach. Phase 2's Coaching Modes are a
  lightweight step toward the roadmap's multi-agent architecture — they swap
  the system prompt per persona rather than routing to separate agents/tools.
  Full orchestration (an Orchestrator Agent routing to specialist agents) is
  the natural next step once there's real usage data on what people actually
  ask for.
- **Payments — two verification paths, one source of truth**: the webhook
  (`payment_server.py`) is the production path; the in-bot "I've Paid"
  button is a zero-infra fallback for local dev and for the rare missed
  webhook. Both call the same `subscription.mark_user_premium()`, and the
  `Payment` table's unique `reference` prevents double-crediting either way.
- **Premium gating is centralized**: every Phase 2 feature calls
  `subscription.require_premium()` first. Adding a new premium feature later
  means one function call, not reimplementing the check.
- **Report/plan generation is on-demand, not scheduled**: a good Phase 4
  add-on is a daily job (e.g. APScheduler or a cron-triggered script) that
  pushes performance reports automatically every Sunday instead of waiting
  for the user to tap the button.
- **One team per coach, roster entries can be guests**: real academies have
  players who aren't going to install a Telegram bot before their coach can
  track attendance for them. `TeamMembership.guest_name` covers that without
  blocking anything on sign-up — a guest can be upgraded to a linked account
  later by re-adding them with `@username` (a natural small enhancement:
  auto-merge a guest into a real account when the names match).
- **Coach Dashboard auth is magic-link, not passwords**: nothing to reset,
  nothing to leak in a breach beyond a 15-minute single-use token. It trades
  off convenience for the coach re-requesting a link periodically — fine at
  pilot scale, worth revisiting if a coach wants to leave the dashboard open
  all day during a tournament (a longer-lived "remember this device" option
  would be the natural next step).
- **Medical records are append-only**: each update inserts a new row rather
  than overwriting the last one, so there's a real history of a player's
  fitness over a season, not just a snapshot — useful for spotting recurring
  issues, even though the current UI only surfaces the latest status.
- **Video analysis is frame-based, not a video model**: Claude's vision
  input is images, not video, so `media/video_frames.py` does the one thing
  that bridges that gap — pull evenly-spaced stills with `ffmpeg`. The system
  prompt is written to keep Claude honest about that limitation rather than
  let it hallucinate motion analysis it can't actually do. If this grows
  into wanting real tracking data (heat maps, xG, sprint speed), that's a
  genuinely different build: a CV pipeline (e.g. YOLO + ByteTrack + pitch
  homography), not an LLM prompt change.
- **Tactical summaries are coach-notes-in, not video-in**: `MatchReport`'s
  AI summary is explicitly scoped to work from what the coach typed
  (formation, key moments, notes) — it says so in its own output. This
  keeps it honest and still useful (a second pair of eyes on the coach's
  own account of the match) without pretending to have watched the game.
- **AI Scout ratings are extracted, not structured**: `_parse_rating()`
  regex-matches the "POTENTIAL RATING: N" line out of Claude's free-form
  report text rather than asking for JSON output. This is a deliberate
  trade-off — free-form text reads better for a coach and is more robust to
  Claude's natural variation, at the cost of the rating occasionally coming
  back as `None` if the format drifts (handled gracefully: it just sorts
  last and shows "—" rather than erroring).
- **External prospects are a lighter model than roster players**:
  `ScoutingProspect` deliberately isn't a `TeamMembership` — a player a
  coach is watching at another club isn't part of the team, shouldn't show
  up in attendance/roster views, and has a much smaller data footprint (a
  name and some notes, not a full profile). Converting a signed prospect
  into a real roster entry is a manual `/addplayer` for now; auto-promoting
  a prospect on status change to "Signed" would be a natural small addition.
- **Lesson content is generated once, globally, not per-user**: `Lesson`
  itself carries `content_text`/`quiz_json`, populated on first access by
  anyone and reused after that — verified in testing that a second open
  does not trigger another Claude call. This is a meaningfully different
  cost/consistency trade-off than the rest of the bot's AI features (which
  are deliberately per-user and personalized) — courses are shared
  reference material, so shared generation is the right call here.
- **Quiz answers are checked client-side against server-cached data, not
  re-verified by Claude per answer**: the correct answer index is part of
  the cached `quiz_json` from generation time, so scoring an answer is a
  simple lookup — fast, free, and doesn't depend on the AI being available
  after the lesson's first load.
- **Certificates gate the credential, not the learning**: every lesson and
  quiz is free for everyone; only the shareable, downloadable proof of
  completion is Premium. This avoids the worse alternative of paywalling
  the actual education.
- **Two different notification paths for one conceptual event**: an
  application arriving is a bot-side event (`context.bot.send_message`
  works directly); an application being reviewed is a dashboard-side event
  (needs `notifications.py`'s HTTP wrapper, since `coach_dashboard.py` is a
  separate process with no live bot connection). Both paths converge on the
  same Telegram chat — the split is about which process the action
  originates in, not a difference in what's being communicated.
- **Equipment marketplace listings are separate from private inventory**:
  `EquipmentListing` (Phase 7, cross-team, opt-in) intentionally isn't the
  same table as `EquipmentItem` (Phase 3, private per-team stock list) — a
  team choosing to list one spare set of cones shouldn't require exposing
  its whole inventory.

## Suggested next phase

The original 10-phase roadmap is now fully built in some form — Phases 1-9
(Foundation through Learning Academy, mapped across this build's own
Phase 1-6 numbering plus AI Scout) and Phase 10 (Marketplace) here. From
here, the natural direction shifts from "new feature areas" to
**hardening and scale**:
- ~~**Postgres migration**~~ — the prerequisite for this is done: schema
  changes now go through Alembic (`migrations/`) instead of relying on
  `create_all()`, which is what actually made moving to Postgres risky
  before (any schema change after go-live would've silently failed to
  apply). The migration to Postgres itself is still just a `DATABASE_URL`
  change whenever the SQLite contention above becomes a real bottleneck —
  worth doing once the bot + payment server + admin dashboard + coach
  dashboard sharing one file actually shows contention, not preemptively.
- **Multi-agent orchestration**: the roadmap's original vision of an
  Orchestrator Agent routing to specialists is still one general-purpose
  Claude call per feature today — reasonable at this scale, but worth
  revisiting with real usage data on what people actually ask.
- **Real computer-vision infrastructure**, if the video/match-intelligence
  features outgrow frame-based review — see the Phase 4/5 scope notes above
  for what that would actually require.
- **WhatsApp / mobile app / multilingual support**, per the roadmap's own
  "Phase 5 (ongoing)" bucket in the Development Strategy section.

Worth deciding deliberately rather than defaulting into: which of these
actually matters for AbleGod FC's real usage first.
