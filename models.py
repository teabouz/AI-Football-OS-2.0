"""
Phase 1 data model.

Deliberately kept simple and normalized so later phases (Video Analysis,
Match Analyst, Scouting, Marketplace, etc.) can add new tables that hang off
User / PlayerProfile without needing a rewrite.
"""
import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, Date, Boolean, Text,
    ForeignKey, Enum, UniqueConstraint
)
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, enum.Enum):
    PLAYER = "player"
    COACH = "coach"
    ACADEMY = "academy"


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PREMIUM = "premium"


class DominantFoot(str, enum.Enum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"


class CoachMode(str, enum.Enum):
    """Phase 2: selectable personas for the AI Coach chat, each with its own
    system prompt (see handlers/coaching_modes.py). Premium-only."""
    GENERAL = "general"
    MINDSET = "mindset"
    LEADERSHIP = "leadership"
    CONFIDENCE = "confidence"
    RECOVERY = "recovery"


class GoalTimeframe(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SEASON = "season"


class GoalStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class MedicalStatus(str, enum.Enum):
    FIT = "fit"
    DOUBTFUL = "doubtful"
    INJURED = "injured"


class FinanceEntryType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


class EquipmentCondition(str, enum.Enum):
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    NEEDS_REPLACEMENT = "needs_replacement"


class AttendanceStatusEnum(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"


class VideoCategory(str, enum.Enum):
    TRAINING = "training"
    MATCH = "match"
    PENALTY = "penalty"
    FREE_KICK = "free_kick"
    GOALKEEPING = "goalkeeping"


class ProspectStatus(str, enum.Enum):
    WATCHING = "watching"
    TRIAL_INVITED = "trial_invited"
    PASSED = "passed"
    SIGNED = "signed"


class CourseCategory(str, enum.Enum):
    COACHING = "coaching"
    NUTRITION = "nutrition"
    SPORTS_PSYCHOLOGY = "sports_psychology"
    SPORTS_SCIENCE = "sports_science"
    LAWS_OF_FOOTBALL = "laws_of_football"
    REFEREEING = "refereeing"
    LEADERSHIP = "leadership"
    CAREER_DEVELOPMENT = "career_development"


class ListingType(str, enum.Enum):
    TRIAL = "trial"
    JOB = "job"
    SCHOLARSHIP = "scholarship"
    INTERNSHIP = "internship"
    SPONSORSHIP = "sponsorship"


class ListingStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class ApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EquipmentListingStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"


class User(Base):
    """One row per Telegram user. Central identity + subscription record."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    language_code = Column(String(8), nullable=True)
    email = Column(String(128), nullable=True)  # collected lazily, needed for Paystack receipts

    role = Column(Enum(UserRole), nullable=True)  # null until registration completes
    registration_complete = Column(Boolean, default=False, nullable=False)

    # --- Subscription foundation (Phase 1 scaffolding; payments land Phase 2) ---
    subscription_tier = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False)
    subscription_expires_at = Column(DateTime, nullable=True)

    # --- Free-tier AI quota tracking ---
    daily_question_count = Column(Integer, default=0, nullable=False)
    daily_question_reset_date = Column(Date, default=date.today, nullable=False)

    # --- Phase 2: which AI Coach persona this user currently has active ---
    active_coach_mode = Column(Enum(CoachMode), default=CoachMode.GENERAL, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_active_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    player_profile = relationship("PlayerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    coach_profile = relationship("CoachProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    academy_profile = relationship("AcademyProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    checkins = relationship("DailyCheckin", back_populates="user", cascade="all, delete-orphan")
    development_plans = relationship("DevelopmentPlan", back_populates="user", cascade="all, delete-orphan")
    performance_reports = relationship("PerformanceReport", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    owned_team = relationship("Team", back_populates="owner", uselist=False, cascade="all, delete-orphan")
    dashboard_tokens = relationship("DashboardToken", back_populates="user", cascade="all, delete-orphan")
    video_analyses = relationship("VideoAnalysis", back_populates="user", cascade="all, delete-orphan")
    lesson_progress = relationship("LessonProgress", back_populates="user", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="user", cascade="all, delete-orphan")
    opportunity_applications = relationship("OpportunityApplication", back_populates="applicant", cascade="all, delete-orphan")

    def is_premium(self) -> bool:
        if self.subscription_tier != SubscriptionTier.PREMIUM:
            return False
        if self.subscription_expires_at and self.subscription_expires_at < datetime.utcnow():
            return False
        return True

    def display_name(self) -> str:
        return self.first_name or self.username or f"User {self.telegram_id}"


class PlayerProfile(Base):
    __tablename__ = "player_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    full_name = Column(String(128), nullable=True)
    age = Column(Integer, nullable=True)
    position = Column(String(64), nullable=True)          # e.g. "Right Winger"
    dominant_foot = Column(Enum(DominantFoot), nullable=True)
    current_club = Column(String(128), nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Integer, nullable=True)
    bio = Column(Text, nullable=True)

    user = relationship("User", back_populates="player_profile")


class CoachProfile(Base):
    __tablename__ = "coach_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    full_name = Column(String(128), nullable=True)
    license_level = Column(String(64), nullable=True)     # e.g. "UEFA B", "CAF C"
    years_experience = Column(Integer, nullable=True)
    specialization = Column(String(128), nullable=True)   # e.g. "Youth Development"
    current_club = Column(String(128), nullable=True)

    user = relationship("User", back_populates="coach_profile")


class AcademyProfile(Base):
    __tablename__ = "academy_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    academy_name = Column(String(128), nullable=True)
    location = Column(String(128), nullable=True)
    founded_year = Column(Integer, nullable=True)
    contact_email = Column(String(128), nullable=True)

    user = relationship("User", back_populates="academy_profile")


class ChatMessage(Base):
    """Rolling AI chat history, used both for quota accounting and to give the
    AI short-term conversational memory (Phase 1 = simple recency window;
    the dedicated Memory Agent from the roadmap arrives in a later phase)."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(16), nullable=False)   # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="messages")


# ============================================================
# Phase 2 — Premium AI Coach
# ============================================================

class Goal(Base):
    """Goal Tracking + Weekly/Monthly/Season Objectives from the roadmap.
    A single flexible table covers all three timeframes."""
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String(200), nullable=False)
    timeframe = Column(Enum(GoalTimeframe), default=GoalTimeframe.WEEKLY, nullable=False)
    target_date = Column(Date, nullable=True)
    status = Column(Enum(GoalStatus), default=GoalStatus.ACTIVE, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="goals")


class DailyCheckin(Base):
    """Backs the AI Habit Coach: sleep, hydration, training completion, and
    mood, one row per user per day. Streaks are computed from consecutive
    dates rather than stored, to avoid drift."""
    __tablename__ = "daily_checkins"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    checkin_date = Column(Date, default=date.today, nullable=False)
    sleep_hours = Column(Integer, nullable=True)
    hydration_liters = Column(Integer, nullable=True)  # stored in deciliters (x10) for 1-decimal precision
    training_completed = Column(Boolean, default=False, nullable=False)
    mood = Column(Integer, nullable=True)  # 1 (rough day) - 5 (great day)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="checkins")


class DevelopmentPlan(Base):
    """Personalized Development Plan, generated by Claude from the player's
    profile. Kept as a history (not overwritten) so progress is visible."""
    __tablename__ = "development_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    plan_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="development_plans")


class PerformanceReport(Base):
    """Weekly/periodic Performance Report: a snapshot of goals, habits, and
    AI Coach engagement, summarized by Claude into a short narrative."""
    __tablename__ = "performance_reports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    report_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="performance_reports")


class Payment(Base):
    """One row per Paystack transaction attempt. `reference` is what ties a
    Telegram user to a Paystack transaction end-to-end (init -> webhook/verify)."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    reference = Column(String(100), unique=True, nullable=False, index=True)
    amount_kobo = Column(Integer, nullable=False)
    currency = Column(String(8), default="NGN", nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    verified_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="payments")


# ============================================================
# Phase 3 — Coach Dashboard & Club Management
# ============================================================

class Team(Base):
    """One team per coach/academy account (kept simple; multi-team support
    is a natural Phase 4+ extension if a coach runs several squads)."""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="owned_team")
    members = relationship("TeamMembership", back_populates="team", cascade="all, delete-orphan")
    training_sessions = relationship("TrainingSession", back_populates="team", cascade="all, delete-orphan")
    match_reports = relationship("MatchReport", back_populates="team", cascade="all, delete-orphan")
    finance_entries = relationship("FinanceEntry", back_populates="team", cascade="all, delete-orphan")
    equipment_items = relationship("EquipmentItem", back_populates="team", cascade="all, delete-orphan")
    scouting_prospects = relationship("ScoutingProspect", back_populates="team", cascade="all, delete-orphan")
    opportunities = relationship("Opportunity", back_populates="team", cascade="all, delete-orphan")
    equipment_listings = relationship("EquipmentListing", back_populates="team", cascade="all, delete-orphan")


class TeamMembership(Base):
    """A roster slot. Either linked to a registered bot User (player_user_id
    set) or a lightweight guest entry (guest_name set) for players who
    aren't on the bot yet — a coach shouldn't be blocked from managing their
    real-world roster by who has and hasn't signed up."""
    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "player_user_id", name="uq_team_membership_team_player"),
    )

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    player_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    guest_name = Column(String(128), nullable=True)

    active = Column(Boolean, default=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="members")
    player_user = relationship("User")
    notes = relationship("PlayerNote", back_populates="membership", cascade="all, delete-orphan")
    medical_records = relationship("MedicalRecord", back_populates="membership", cascade="all, delete-orphan")
    attendance_records = relationship("AttendanceRecord", back_populates="membership", cascade="all, delete-orphan")
    scouting_reports = relationship("PlayerScoutingReport", back_populates="membership", cascade="all, delete-orphan")

    def display_name(self) -> str:
        if self.player_user:
            return self.player_user.display_name()
        return self.guest_name or f"Player #{self.id}"


class TrainingSession(Base):
    """Covers Training Planning + Attendance + Session Evaluation in one
    row per real-world session, matching how a coach actually experiences
    a training day: plan it, take attendance, evaluate it afterward."""
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    session_date = Column(Date, default=date.today, nullable=False)
    focus = Column(String(200), nullable=True)
    plan_text = Column(Text, nullable=True)  # optionally AI-generated

    evaluation_rating = Column(Integer, nullable=True)  # 1-5
    evaluation_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="training_sessions")
    attendance_records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("training_sessions.id"), nullable=False)
    membership_id = Column(Integer, ForeignKey("team_memberships.id"), nullable=False)
    present = Column(Boolean, default=False, nullable=False)
    marked_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("TrainingSession", back_populates="attendance_records")
    membership = relationship("TeamMembership", back_populates="attendance_records")


class PlayerNote(Base):
    """Coach-only notes on a roster player — performance, development,
    behavioral observations. Never shown to the player themselves."""
    __tablename__ = "player_notes"

    id = Column(Integer, primary_key=True)
    membership_id = Column(Integer, ForeignKey("team_memberships.id"), nullable=False)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    membership = relationship("TeamMembership", back_populates="notes")


class MedicalRecord(Base):
    """Current fitness/medical status per player. Kept as a history (not
    overwritten) so a coach can see how it's evolved."""
    __tablename__ = "medical_records"

    id = Column(Integer, primary_key=True)
    membership_id = Column(Integer, ForeignKey("team_memberships.id"), nullable=False)
    status = Column(Enum(MedicalStatus), default=MedicalStatus.FIT, nullable=False)
    description = Column(Text, nullable=True)
    expected_return_date = Column(Date, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    membership = relationship("TeamMembership", back_populates="medical_records")


class MatchReport(Base):
    __tablename__ = "match_reports"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    match_date = Column(Date, default=date.today, nullable=False)
    opponent = Column(String(128), nullable=False)
    competition = Column(String(128), nullable=True)
    score_for = Column(Integer, nullable=True)
    score_against = Column(Integer, nullable=True)
    formation = Column(String(32), nullable=True)         # e.g. "4-3-3"
    key_moments = Column(Text, nullable=True)              # coach-entered: goals, cards, subs, turning points
    notes = Column(Text, nullable=True)
    tactical_summary = Column(Text, nullable=True)         # AI-written, from formation + key_moments + notes

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    team = relationship("Team", back_populates="match_reports")


class FinanceEntry(Base):
    """Club Finance ledger — simple income/expense tracking (kit, fees,
    transport, tournament costs, etc.). Not a payment gateway integration;
    that's the Payment table over in Phase 2 (player subscriptions)."""
    __tablename__ = "finance_entries"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    entry_type = Column(Enum(FinanceEntryType), nullable=False)
    amount_kobo = Column(Integer, nullable=False)
    category = Column(String(64), nullable=True)  # e.g. "Kit", "Fees", "Transport"
    description = Column(String(255), nullable=True)
    entry_date = Column(Date, default=date.today, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    team = relationship("Team", back_populates="finance_entries")


class EquipmentItem(Base):
    __tablename__ = "equipment_items"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    name = Column(String(128), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    condition = Column(Enum(EquipmentCondition), default=EquipmentCondition.GOOD, nullable=False)
    notes = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="equipment_items")


class DashboardToken(Base):
    """Short-lived magic-link token so a coach can open the web Coach
    Dashboard from Telegram without a separate username/password to manage."""
    __tablename__ = "dashboard_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="dashboard_tokens")


# ============================================================
# Phase 4 — AI Video Analysis
# ============================================================

class VideoAnalysis(Base):
    """One row per analyzed clip. `analysis_text` is Claude's full structured
    write-up (strengths / weaknesses / improvement areas / training focus) —
    stored as one text block rather than split into separate columns, since
    that's more robust than parsing free-form AI output into fields."""
    __tablename__ = "video_analyses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    category = Column(Enum(VideoCategory), nullable=False)
    telegram_file_id = Column(String(256), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    frame_count = Column(Integer, nullable=True)
    analysis_text = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="video_analyses")


# ============================================================
# Phase 5 — AI Scout
# ============================================================

class PlayerScoutingReport(Base):
    """AI-synthesized talent assessment for a roster player, drawing on
    everything already logged about them (notes, medical history,
    attendance, video analyses, development plans) rather than any
    independent statistical or tracking data — kept as history like
    DevelopmentPlan, so a coach can see how an assessment evolves."""
    __tablename__ = "player_scouting_reports"

    id = Column(Integer, primary_key=True)
    membership_id = Column(Integer, ForeignKey("team_memberships.id"), nullable=False)

    report_text = Column(Text, nullable=False)
    potential_rating = Column(Integer, nullable=True)  # 1-10, coach-input-derived, not a scientific score

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    membership = relationship("TeamMembership", back_populates="scouting_reports")


class ScoutingProspect(Base):
    """An external player a coach is tracking — seen at another club, a
    trial, an opposing team, etc. Not on the roster (no TeamMembership);
    this is deliberately a separate, lighter-weight record since a
    prospect isn't yet part of the team."""
    __tablename__ = "scouting_prospects"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    name = Column(String(128), nullable=False)
    position = Column(String(64), nullable=True)
    age = Column(Integer, nullable=True)
    source = Column(String(200), nullable=True)  # e.g. "Rivers United U15, seen at friendly 08 Aug"
    notes = Column(Text, nullable=True)
    manual_rating = Column(Integer, nullable=True)  # 1-10, the coach's own gut rating
    status = Column(Enum(ProspectStatus), default=ProspectStatus.WATCHING, nullable=False)
    ai_assessment = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    team = relationship("Team", back_populates="scouting_prospects")


# ============================================================
# Phase 6 — Learning Academy
# ============================================================

class Course(Base):
    """Course structure mirrors academy_curriculum.py 1:1 (matched by
    `slug`), seeded into the DB at startup. Keeping courses/lessons as real
    rows (not just static data) lets progress, quiz scores, and generated
    content attach to them with normal foreign keys."""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(128), nullable=False)
    description = Column(String(255), nullable=True)
    category = Column(Enum(CourseCategory), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)

    lessons = relationship("Lesson", back_populates="course", cascade="all, delete-orphan",
                            order_by="Lesson.order_index")
    certificates = relationship("Certificate", back_populates="course", cascade="all, delete-orphan")


class Lesson(Base):
    """`content_text` and `quiz_json` are null until the first time anyone
    opens the lesson — generated once by Claude then, and shared by every
    user after that (see handlers/academy.py)."""
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    slug = Column(String(64), nullable=False)
    title = Column(String(128), nullable=False)
    brief = Column(String(255), nullable=False)  # generation steer, from academy_curriculum.py
    order_index = Column(Integer, default=0, nullable=False)

    content_text = Column(Text, nullable=True)
    quiz_json = Column(Text, nullable=True)
    generated_at = Column(DateTime, nullable=True)

    course = relationship("Course", back_populates="lessons")
    progress_records = relationship("LessonProgress", back_populates="lesson", cascade="all, delete-orphan")


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)

    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    quiz_score = Column(Integer, nullable=True)
    quiz_total = Column(Integer, nullable=True)

    user = relationship("User", back_populates="lesson_progress")
    lesson = relationship("Lesson", back_populates="progress_records")


class Certificate(Base):
    """Issued when every lesson in a course is completed. Premium-gated —
    lessons and quizzes themselves are free (matches the roadmap's own free
    tier including basic lessons/quizzes), but the certificate is a Premium
    perk, similar to how some course platforms let you audit free and pay
    for the credential."""
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    certificate_code = Column(String(32), unique=True, nullable=False, index=True)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="certificates")
    course = relationship("Course", back_populates="certificates")


# ============================================================
# Phase 7 — Marketplace
# ============================================================

class Opportunity(Base):
    """Trial/Job/Scholarship/Internship/Sponsorship-seeking listing.

    Deliberately institutional: only Coach/Academy accounts post these
    (same require_coach_or_academy gate used everywhere else), and players
    (or coaches, for Job listings) choose to apply. There is intentionally
    NO passive "browse all players" side to this marketplace — see
    OpportunityApplication below and the README for why."""
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    posted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    listing_type = Column(Enum(ListingType), nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(128), nullable=True)
    age_min = Column(Integer, nullable=True)
    age_max = Column(Integer, nullable=True)
    deadline = Column(Date, nullable=True)
    status = Column(Enum(ListingStatus), default=ListingStatus.OPEN, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="opportunities")
    applications = relationship("OpportunityApplication", back_populates="opportunity", cascade="all, delete-orphan")


class OpportunityApplication(Base):
    """A player/coach CHOOSES to apply — this is the only way a person
    becomes visible to an opportunity's poster through the marketplace.
    Nothing about a user is ever surfaced to a poster before they apply."""
    __tablename__ = "opportunity_applications"

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=False)
    applicant_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    note = Column(Text, nullable=True)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False)

    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)

    opportunity = relationship("Opportunity", back_populates="applications")
    applicant = relationship("User", back_populates="opportunity_applications")


class EquipmentListing(Base):
    """Team-to-team equipment marketplace — separate from the private
    inventory tracker (EquipmentItem, Phase 3) so a team's internal stock
    list isn't automatically public; a team chooses what to list."""
    __tablename__ = "equipment_listings"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    condition = Column(Enum(EquipmentCondition), default=EquipmentCondition.GOOD, nullable=False)
    price_kobo = Column(Integer, nullable=True)  # null = free / open to trade
    status = Column(Enum(EquipmentListingStatus), default=EquipmentListingStatus.AVAILABLE, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="equipment_listings")
    interests = relationship("EquipmentInterest", back_populates="listing", cascade="all, delete-orphan")


class EquipmentInterest(Base):
    __tablename__ = "equipment_interests"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("equipment_listings.id"), nullable=False)
    interested_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    interested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    listing = relationship("EquipmentListing", back_populates="interests")
