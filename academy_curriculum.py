"""
Learning Academy curriculum — Phase 6.

Course and lesson STRUCTURE is curated by hand (titles, ordering, topic
coverage) so the catalog reliably covers what the roadmap asks for and
doesn't drift or duplicate itself. Lesson CONTENT and quizzes are generated
by Claude on first access (see handlers/academy.py) and cached in the
database from then on — generated once, shared by every user, not
regenerated per-user. The "brief" field below is the one-line steer given
to Claude for each lesson so content stays on-topic.

To add a lesson: add an entry here. It'll show up in the catalog and get
its content generated the first time anyone opens it — no migration needed
beyond the usual `init_db()` table creation.
"""

COURSES = [
    {
        "slug": "coaching",
        "title": "Coaching Fundamentals",
        "category": "coaching",
        "description": "Core principles for coaching youth football players.",
        "lessons": [
            {"slug": "youth-coaching-principles", "title": "Principles of Youth Coaching",
             "brief": "What makes youth coaching different from coaching adults: development over "
                      "results, age-appropriate expectations, and creating a positive environment."},
            {"slug": "session-planning", "title": "Session Planning Fundamentals",
             "brief": "How to structure a training session: warm-up, main themes, small-sided games, "
                      "cool-down, and matching session length/intensity to age group."},
            {"slug": "communication-management", "title": "Communication & Man-Management",
             "brief": "How to give feedback that lands, manage different personalities on a team, "
                      "and communicate with parents constructively."},
            {"slug": "coaching-philosophy", "title": "Building a Coaching Philosophy",
             "brief": "Why a clear, consistent coaching philosophy matters and how to start defining "
                      "your own values and priorities as a coach."},
        ],
    },
    {
        "slug": "nutrition",
        "title": "Nutrition for Footballers",
        "category": "nutrition",
        "description": "Practical, healthy nutrition guidance for active young players.",
        "lessons": [
            {"slug": "nutrition-basics", "title": "Nutrition Basics for Young Footballers",
             "brief": "General healthy-eating principles for active teenagers: balanced meals, "
                      "energy needs, and why extreme diets are inappropriate for young athletes."},
            {"slug": "match-day-fueling", "title": "Match Day Fueling",
             "brief": "General guidance on eating before and after a match — timing and food types "
                      "in general terms, not specific calorie/macro targets."},
            {"slug": "hydration-recovery", "title": "Hydration & Recovery Nutrition",
             "brief": "Why hydration matters for performance and recovery, general signs of "
                      "dehydration, and simple recovery-meal habits."},
            {"slug": "healthy-habits", "title": "Building Healthy, Sustainable Habits",
             "brief": "How to build sustainable healthy eating habits as a young athlete, and why "
                      "this should never mean skipping meals or extreme restriction."},
        ],
    },
    {
        "slug": "sports-psychology",
        "title": "Sports Psychology",
        "category": "sports_psychology",
        "description": "Mental skills for performing under pressure and bouncing back from setbacks.",
        "lessons": [
            {"slug": "confidence-mistakes", "title": "Building Confidence & Handling Mistakes",
             "brief": "How top players think about mistakes during a game and simple techniques "
                      "for resetting focus after an error."},
            {"slug": "focus-routines", "title": "Focus & Pre-Match Routines",
             "brief": "Why pre-match routines help focus, and how to build a simple, personal "
                      "routine for matchday."},
            {"slug": "pressure-setbacks", "title": "Dealing with Pressure & Setbacks",
             "brief": "General mental strategies for handling high-pressure moments and recovering "
                      "from setbacks like being dropped or losing a big game."},
            {"slug": "team-culture-motivation", "title": "Team Culture & Motivation",
             "brief": "What makes a positive team culture, and the difference between internal and "
                      "external motivation in a sports context."},
        ],
    },
    {
        "slug": "sports-science",
        "title": "Sports Science Basics",
        "category": "sports_science",
        "description": "Foundational physical development and injury-prevention knowledge.",
        "lessons": [
            {"slug": "football-fitness-basics", "title": "Basics of Football Fitness",
             "brief": "The general physical qualities football requires (endurance, speed, agility, "
                      "strength) at a conceptual level, not a training program."},
            {"slug": "injury-prevention-basics", "title": "Injury Prevention Fundamentals",
             "brief": "General principles of injury prevention: warm-ups, load management, and "
                      "recognizing early signs of overuse — always recommending a professional for "
                      "actual injuries."},
            {"slug": "recovery-rest", "title": "Understanding Recovery & Rest",
             "brief": "Why rest and sleep matter for young athletes' development and performance, "
                      "in general educational terms."},
            {"slug": "strength-conditioning-basics", "title": "Strength & Conditioning for Young Players",
             "brief": "General, age-appropriate principles of strength and conditioning for youth "
                      "players — bodyweight-based, not prescriptive loading programs."},
        ],
    },
    {
        "slug": "laws-of-football",
        "title": "Laws of the Game",
        "category": "laws_of_football",
        "description": "The official Laws of the Game, explained clearly.",
        "lessons": [
            {"slug": "the-basics", "title": "The Basics: Field, Players, Duration",
             "brief": "Pitch dimensions basics, number of players, match duration, and other "
                      "foundational Law 1-7 concepts from IFAB's Laws of the Game."},
            {"slug": "offside-explained", "title": "Offside Explained",
             "brief": "A clear, example-driven explanation of the offside law (Law 11)."},
            {"slug": "fouls-misconduct-cards", "title": "Fouls, Misconduct & Cards",
             "brief": "What constitutes a foul, the difference between a yellow and red card, and "
                      "common misconduct offenses (Laws 12)."},
            {"slug": "set-pieces-restarts", "title": "Set Pieces & Restarts",
             "brief": "How each restart works: kick-off, throw-in, goal kick, corner kick, free "
                      "kick, and penalty kick (Laws 13-17)."},
        ],
    },
    {
        "slug": "refereeing",
        "title": "Introduction to Refereeing",
        "category": "refereeing",
        "description": "The basics of officiating a football match.",
        "lessons": [
            {"slug": "intro-officiating", "title": "Introduction to Match Officiating",
             "brief": "What a referee's role involves at a youth/grassroots level, and the roles of "
                      "assistant referees."},
            {"slug": "positioning-signals", "title": "Positioning & Signals",
             "brief": "Basic referee positioning principles (diagonal system) and common signals "
                      "referees use."},
            {"slug": "managing-behavior", "title": "Managing Player Behavior",
             "brief": "How referees manage dissent and player behavior calmly and consistently, "
                      "especially at youth level."},
            {"slug": "advantage-game-management", "title": "Advantage & Game Management",
             "brief": "How the advantage rule works and general principles of game management — "
                      "letting the game flow appropriately."},
        ],
    },
    {
        "slug": "leadership",
        "title": "Leadership on the Pitch",
        "category": "leadership",
        "description": "What it takes to lead a team, on and off the ball.",
        "lessons": [
            {"slug": "good-captain", "title": "What Makes a Good Captain",
             "brief": "The qualities of effective football captains at any level, beyond just "
                      "being the most talented player."},
            {"slug": "leading-by-example", "title": "Leading by Example",
             "brief": "How work rate, attitude, and consistency influence teammates more than words do."},
            {"slug": "communicating-under-pressure", "title": "Communicating Under Pressure",
             "brief": "How to communicate clearly and calmly with teammates during high-pressure "
                      "moments in a match."},
            {"slug": "building-trust", "title": "Building Trust in a Team",
             "brief": "How trust is built within a squad over time, and the leader's role in that."},
        ],
    },
    {
        "slug": "career-development",
        "title": "Career Development",
        "category": "career_development",
        "description": "Understanding pathways and preparing for opportunities in football.",
        "lessons": [
            {"slug": "pathways", "title": "Understanding Pathways in Football",
             "brief": "The range of realistic pathways in football — professional play, semi-pro, "
                      "coaching, sports science, admin — and why having a broad view matters."},
            {"slug": "preparing-for-trials", "title": "Preparing for Trials",
             "brief": "Practical, general advice on preparing for a football trial: what to expect "
                      "and how to present yourself well."},
            {"slug": "highlight-reel", "title": "Building a Player Profile & Highlight Reel",
             "brief": "What makes a good highlight reel and player profile for scouts/academies to "
                      "review, in general terms."},
            {"slug": "working-with-scouts", "title": "Working with Coaches, Scouts & Agents",
             "brief": "General, safe guidance on how young players and families should approach "
                      "interactions with scouts and agents."},
        ],
    },
]


def get_course(slug: str):
    return next((c for c in COURSES if c["slug"] == slug), None)


def get_lesson(course_slug: str, lesson_slug: str):
    course = get_course(course_slug)
    if not course:
        return None
    return next((l for l in course["lessons"] if l["slug"] == lesson_slug), None)
