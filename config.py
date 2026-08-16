"""
Central configuration for the AI Football OS bot (Phase 1).
All values are loaded from environment variables / .env so secrets never
live in source code.
"""
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

# Resolve .env relative to this file rather than the process's current
# working directory. main.py, coach_dashboard.py, payment_server.py, and
# admin_dashboard.py are all meant to be launched as separate processes
# (see README), sometimes from different terminals/working directories, or
# from a process manager (systemd, Railway, etc.) whose cwd isn't the repo
# root. The bare `load_dotenv()` relies on searching upward from the
# current working directory and can silently miss the file if a process is
# started from somewhere else -- that's the most likely explanation for
# "TELEGRAM_BOT_TOKEN in environment: False" being observed in one shell
# while the bot (started from the project root in another shell) loads it
# fine. Pointing load_dotenv() at an explicit path removes that ambiguity.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_ENV_PATH)

LOCAL_ONLY_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def is_local_only_url(url: str) -> bool:
    """True if `url` points at a loopback address a phone/Telegram cannot
    reach (e.g. http://localhost:5002). Used to decide whether a magic-link
    dashboard URL is safe to hand to Telegram as a clickable button."""
    try:
        host = urlparse(url).hostname
    except ValueError:
        return True
    return not host or host in LOCAL_ONLY_HOSTS


def is_well_formed_public_url(url: str) -> bool:
    """True if `url` is a syntactically valid absolute http(s) URL at all
    (regardless of whether it's local-only). Guards against a blank,
    malformed, or scheme-less DASHBOARD_BASE_URL producing a broken link."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)

# --- Telegram ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# --- AI (Claude) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_football.db")

# --- Admin (Telegram-side /admin command) ---
ADMIN_TELEGRAM_IDS = {
    int(x) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip().isdigit()
}

# --- Admin web dashboard ---
ADMIN_DASHBOARD_USERNAME = os.getenv("ADMIN_DASHBOARD_USERNAME", "admin")
ADMIN_DASHBOARD_PASSWORD = os.getenv("ADMIN_DASHBOARD_PASSWORD", "changeme")

if ADMIN_DASHBOARD_PASSWORD == "changeme":
    print("[WARNING] ADMIN_DASHBOARD_PASSWORD is using the insecure default ('changeme'). "
          "Set a real password in .env before deploying -- the Admin Dashboard exposes "
          "user data, payments, and broadcast to every user on the platform.")

# --- Subscription / Phase 1 foundation ---
FREE_TIER_DAILY_QUESTIONS = int(os.getenv("FREE_TIER_DAILY_QUESTIONS", "5"))
PREMIUM_MONTHLY_PRICE_NGN = os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "5,000")

# --- Phase 2: Payments (Paystack) ---
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PREMIUM_PRICE_KOBO = int(os.getenv("PREMIUM_PRICE_KOBO", "500000"))  # NGN 5,000 * 100
PREMIUM_DURATION_DAYS = int(os.getenv("PREMIUM_DURATION_DAYS", "30"))

# Public base URL where payment_server.py (port 5001) is reachable, e.g. an
# ngrok/tunnel URL in dev or your real domain in production. Required for
# Paystack's callback_url and to receive the charge.success webhook.
#
# NOTE: this is deliberately a *separate* variable from DASHBOARD_BASE_URL
# below. payment_server.py and coach_dashboard.py are two independent Flask
# processes on two different ports (5001 vs 5002) and will very often need
# two different public tunnel URLs (each `ngrok http <port>` / SSH tunnel
# gives you a distinct address) -- collapsing them into one variable is what
# previously sent Coach Dashboard links to the payment server by mistake.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5001")

if not PAYSTACK_SECRET_KEY:
    print("[WARNING] PAYSTACK_SECRET_KEY is not set. Upgrade-to-Premium payments will not work.")

# --- Phase 3: Coach Dashboard ---
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-insecure-secret-change-me")
DASHBOARD_TOKEN_TTL_MINUTES = int(os.getenv("DASHBOARD_TOKEN_TTL_MINUTES", "15"))

# Public base URL where coach_dashboard.py (port 5002) is reachable. This is
# what /dashboard uses to build the magic-link the coach taps in Telegram --
# it MUST be a URL Telegram (running on the coach's phone, not this
# computer) can actually open. `http://localhost:5002` / `127.0.0.1` only
# work in a browser on this same machine, never from Telegram on a device.
# For local-machine-only browser testing that's fine and left as the
# default; for anything opened via Telegram, set this to a public HTTPS
# tunnel (see README) or your real domain.
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://127.0.0.1:5002")

if FLASK_SECRET_KEY == "dev-insecure-secret-change-me":
    print("[WARNING] FLASK_SECRET_KEY is using the insecure default. Set a real random value in .env before deploying.")

if is_local_only_url(DASHBOARD_BASE_URL):
    print(
        f"[INFO] DASHBOARD_BASE_URL is a local-only address ({DASHBOARD_BASE_URL}). "
        "/dashboard links will open in a browser on THIS computer but cannot be opened "
        "from Telegram on a phone or another device. Set DASHBOARD_BASE_URL in .env to a "
        "public HTTPS tunnel (e.g. localhost.run / serveo.net / pinggy.io / Railway) to "
        "make the dashboard reachable from Telegram."
    )
elif not is_well_formed_public_url(DASHBOARD_BASE_URL):
    print(
        f"[WARNING] DASHBOARD_BASE_URL ({DASHBOARD_BASE_URL!r}) doesn't look like a valid "
        "http(s) URL. /dashboard links will be broken until this is fixed."
    )

# --- Phase 4: Video Analysis ---
# Telegram's standard Bot API can only download files up to 20MB via getFile.
# Bigger clips need a self-hosted Bot API server (see README) — not attempted here.
MAX_VIDEO_MB = int(os.getenv("MAX_VIDEO_MB", "20"))
VIDEO_FRAME_COUNT = int(os.getenv("VIDEO_FRAME_COUNT", "6"))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")
VIDEO_TEMP_DIR = os.getenv("VIDEO_TEMP_DIR", "/tmp/ai_football_video")

VIDEO_ANALYSIS_PROMPTS = {
    "training": "This is a training session clip. Focus on technique, body shape, first touch, and "
                "decision-making under low pressure.",
    "match": "This is a match clip. Focus on positioning, scanning/awareness, decision-making under "
             "real pressure, and work rate off the ball.",
    "penalty": "This is a penalty-taking clip. Focus on run-up consistency, plant foot position, "
               "body shape over the ball, and disguise/technique.",
    "free_kick": "This is a free-kick clip. Focus on run-up, contact point on the ball, technique "
                 "(strike type), and body shape through the follow-through.",
    "goalkeeping": "This is a goalkeeping clip. Focus on starting position, footwork, handling "
                   "technique, positioning relative to goal, and shot-stopping shape.",
}

VIDEO_ANALYSIS_SYSTEM_PROMPT = """You are a UEFA-licensed football coach reviewing still frames \
extracted from a player's video clip. You do NOT have the full video, motion, or audio — only a \
handful of still frames spread across the clip. Be genuinely useful within that real limitation: \
comment on what's visible in the frames (body positioning, posture, technique at the moment \
captured, spacing/shape if other players are visible) rather than claiming to see continuous \
movement you can't actually observe. If the frames don't show enough to judge something \
confidently, say so plainly instead of guessing.

Structure your response with these exact headers, each 2-4 sentences:
STRENGTHS:
WEAKNESSES:
IMPROVEMENT AREAS:
TRAINING FOCUS:

Keep the whole response under 300 words. Plain text, no markdown tables."""

# --- Phase 5: AI Scout ---
SCOUTING_REPORT_SYSTEM_PROMPT = """You are helping a football coach synthesize everything they've \
already recorded about a player into one coherent scouting-style report. You have NO independent \
statistical, tracking, or scouting-network data — only the coach's own notes, medical history, \
attendance record, video analysis history, and profile info, all provided to you. Your job is \
synthesis and pattern-spotting across what's there, not independent judgment from data you don't \
have. If the available information is thin, say so plainly rather than padding the report with \
generic filler.

Structure your response with these exact headers:
OVERVIEW: (2-3 sentences)
STRENGTHS: (from the evidence provided)
AREAS TO DEVELOP: (from the evidence provided)
POTENTIAL RATING: (a single number 1-10, then one sentence explaining what it's based on — be clear \
this reflects the coach's own logged inputs, not an independent or scientific rating)
RECOMMENDATION: (one concrete next step — e.g. more minutes, a trial, another season of development)

Keep the whole response under 320 words. Plain text, no markdown tables."""

SCOUTING_COMPARISON_SYSTEM_PROMPT = """You are helping a football coach compare two players using \
only what the coach has already logged about each of them (notes, medical history, attendance, \
video analyses, profile info) — you have no independent statistics or tracking data. Compare them \
fairly on what's actually there; if the data is uneven between the two (e.g. one has far more notes \
logged than the other), say so rather than pretending the comparison is balanced.

Structure: a short paragraph on Player A, a short paragraph on Player B, then a final "HEAD TO HEAD" \
section giving a balanced view of what each brings. Do not declare one player categorically "better" \
— footballers play different roles and develop at different rates. Plain text, under 300 words."""

SCOUTING_PROSPECT_SYSTEM_PROMPT = """You are helping a football coach write up an assessment of an \
external prospect (not on their own roster) based only on the coach's own scouting notes from \
watching them. You have no independent data on this player. Write a short, honest recruitment-style \
note: what stood out, what's unproven or needs a closer look, and a suggested next step (e.g. invite \
to a trial, watch again, not a fit right now). Be clear this reflects one coach's observations, not \
a formal scouting report. Plain text, under 200 words."""

# --- Phase 6: Learning Academy ---
ACADEMY_LESSON_SYSTEM_PROMPT = """You write lessons for a football education platform aimed at \
players, coaches, and academy staff (mostly teenagers and young adults). You will be given a course \
title, category, lesson title, and a one-line brief describing what the lesson should cover.

Write educational, accurate, engaging content. For nutrition and sports-science topics, stay at the \
level of general healthy-living education — no specific calorie counts, macro targets, supplement \
dosages, or restrictive diet plans, and note that a nutritionist/doctor should be consulted for \
individual guidance. For laws-of-football and refereeing topics, be precise and accurate to the \
actual IFAB Laws of the Game. For psychology/leadership topics, keep guidance general and healthy — \
no clinical claims.

Respond with ONLY valid JSON (no markdown fences, no commentary before or after), in exactly this \
shape:
{
  "content": "<the lesson text, 400-600 words, plain prose with occasional paragraph breaks, no markdown formatting>",
  "quiz": [
    {"question": "<question 1>", "options": ["<A>", "<B>", "<C>", "<D>"], "correct_index": 0},
    {"question": "<question 2>", "options": ["<A>", "<B>", "<C>", "<D>"], "correct_index": 0},
    {"question": "<question 3>", "options": ["<A>", "<B>", "<C>", "<D>"], "correct_index": 0}
  ]
}
Exactly 3 quiz questions, each with exactly 4 options and one correct_index (0-3) that's actually \
correct based on the lesson content."""

AI_COACH_SYSTEM_PROMPT = """You are the AI Coach inside the AI Football OS \
Telegram bot. You speak to players, coaches, and academies who want to \
improve their football knowledge, training, and careers.

Guidelines:
- Be practical, encouraging, and specific — give real drills, real tactical \
concepts, real explanations, not vague motivation.
- Keep answers concise enough for a chat app (roughly 80-180 words) unless \
the user clearly wants a detailed breakdown.
- When relevant, tailor advice to the user's role (player/coach/academy) and \
position if known.
- You are not a doctor. For injuries or medical symptoms, give general safe \
guidance and recommend seeing a physiotherapist or doctor for anything beyond \
minor soreness.
- Stay strictly on football, football fitness, football psychology, and \
football career topics. If asked something unrelated, gently redirect.
"""

# --- Phase 2: Coaching Mode system prompts ---
# Each mode narrows the general AI Coach into a specialist persona. Selected
# via handlers/coaching_modes.py and applied in handlers/ai_chat.py.
COACH_MODE_PROMPTS = {
    "general": AI_COACH_SYSTEM_PROMPT,
    "mindset": AI_COACH_SYSTEM_PROMPT + """

MODE: Mindset Coach.
Focus specifically on sports psychology: focus, motivation, pre-match \
routines, dealing with mistakes, and building mental resilience. Use \
techniques like visualization, self-talk reframing, and routine-building. \
Keep a calm, grounding tone.""",
    "leadership": AI_COACH_SYSTEM_PROMPT + """

MODE: Leadership Coach.
Focus on captaincy, communication on the pitch, leading by example, \
motivating teammates, and handling conflict within a team. Draw on real \
leadership principles adapted for a football dressing room.""",
    "confidence": AI_COACH_SYSTEM_PROMPT + """

MODE: Confidence Coach.
Focus on rebuilding confidence after a bad game, mistake, injury, or being \
dropped. Be warm and encouraging without empty positivity — acknowledge the \
setback honestly, then give one or two concrete, doable next steps.""",
    "recovery": AI_COACH_SYSTEM_PROMPT + """

MODE: Recovery Coach.
Focus on recovery, sleep, hydration, and injury-prevention habits between \
sessions and matches. Give practical, evidence-based guidance. For anything \
that sounds like an actual injury or persistent pain, clearly recommend \
seeing a physiotherapist or doctor rather than trying to manage it via chat.""",
}

if not BOT_TOKEN:
    print("[WARNING] TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
if not ANTHROPIC_API_KEY:
    print("[WARNING] ANTHROPIC_API_KEY is not set. AI Chat will not work until it is.")
