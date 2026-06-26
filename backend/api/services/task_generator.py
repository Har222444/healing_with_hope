import logging
import os
import random
import re
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
TRIGGER_CONFIDENCE_THRESHOLD = 0.60
MIN_HOURS_BETWEEN_TASKS      = 3

TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
LLAMA_MODEL      = "meta-llama/Llama-3-70b-chat-hf"

# ── TASK_BANK (primary source — always clean, always correct) ──────────────────
TASK_BANK: Dict[str, Dict[str, List[str]]] = {
    "STUDY": {
        "LOW": [
            "Open your study file and read 5 lines.",
            "Write down the title of your next topic.",
            "Set a 3-minute timer and skim yesterday's notes.",
            "Open your IDE or a clean notebook page.",
            "Highlight one key formula in your slides.",
        ],
        "MEDIUM": [
            "Spend 15 minutes reviewing your trickiest bug.",
            "Write a 2-sentence summary of a core concept.",
            "Solve exactly one practice problem right now.",
            "Explain one architecture block to an imaginary peer.",
            "Refactor or clean up 10 lines of old code.",
        ],
        "HIGH": [
            "Complete a 25-minute focused study block.",
            "Map your study timeline for the next 3 days.",
            "Complete one mock question under a strict timer.",
            "Write a full code module or mock deployment script.",
            "Analyze and fix 3 high-priority bugs in your log.",
        ],
    },
    "CAREER": {
        "LOW": [
            "Open your CV document and keep the tab open.",
            "Write one new skill or project to add to your CV.",
            "Bookmark one job listing to review later.",
            "Check your professional inbox for new updates.",
            "Write one career milestone for this quarter.",
        ],
        "MEDIUM": [
            "Refine one project bullet point on your CV.",
            "Draft a 2-sentence intro message to a peer.",
            "List 2 requirements for your target role.",
            "Update the headline on your portfolio profile.",
            "Read one interview case-study breakdown.",
        ],
        "HIGH": [
            "Draft a tailored 3-paragraph cover letter.",
            "Record a 2-minute mock interview answer.",
            "Submit an application to your top-tracked role.",
            "Reach out directly to a recruiter today.",
            "Polish your GitHub readme for your top project.",
        ],
    },
    "EMOTIONAL": {
        "LOW": [
            "Write three words describing your mood right now.",
            "Take two slow, deep box-breaths.",
            "Write one thing that went well yesterday.",
            "Acknowledge your frustration out loud and reset.",
            "Listen to one calming song all the way through.",
        ],
        "MEDIUM": [
            "Set a 5-minute timer and journal freely.",
            "Text a trusted person you are thinking of them.",
            "Look out a window for 5 minutes without your phone.",
            "Drop your shoulders and unclench your jaw now.",
            "List 3 things you can physically touch right now.",
        ],
        "HIGH": [
            "Write your anxieties down then tear up the paper.",
            "Schedule your next check-in or support session.",
            "Call a trusted friend and talk for 10 minutes.",
            "Write a letter to your future self about resilience.",
            "Turn off all notifications for the next hour.",
        ],
    },
    "SOCIAL": {
        "LOW": [
            "Send a meme or voice note to a friend.",
            "Leave a kind comment on a peer's recent post.",
            "Write the name of one person you miss.",
            "Check one upcoming birthday in your contacts.",
            "React to an old memory shared by a friend.",
        ],
        "MEDIUM": [
            "Send a 30-second voice note to check in.",
            "Text a friend to arrange a quick catch-up call.",
            "Reply to one unread message with a single line.",
            "Suggest a coffee break or video call to a teammate.",
            "Share a useful article with a group chat.",
        ],
        "HIGH": [
            "Organise a group hangout for this weekend.",
            "Write an appreciation note to a close friend.",
            "Join one online community event or thread today.",
            "Plan a lunch catch-up with a colleague you respect.",
            "Call someone you have not spoken to recently.",
        ],
    },
    "PHYSICAL": {
        "LOW": [
            "Drink a full glass of water right now.",
            "Stand up and roll your shoulders 5 times.",
            "Step outside and take 3 deep breaths.",
            "Splash cold water on your face right now.",
            "Do a 30-second full-body overhead stretch.",
        ],
        "MEDIUM": [
            "Take a 10-minute walk outside or in the hall.",
            "Follow a 5-minute seated back-stretch routine.",
            "Clear your desk surface of everything.",
            "Make a simple hot drink or healthy snack.",
            "Sit away from your screen for 5 minutes.",
        ],
        "HIGH": [
            "Complete a brisk 20-minute workout right now.",
            "Log your water intake on a sticky note today.",
            "Book the health check-up you have been postponing.",
            "Pack a nutritious meal for tomorrow.",
            "Set a firm screen-off time for tonight.",
        ],
    },
    "OVERLOAD": {
        "LOW": [
            "List 3 stressors and cross out 2 that can wait.",
            "Close every browser tab except your active one.",
            "Set a 10-minute timer and do one micro-task.",
            "Clear your physical desk of loose items now.",
            "Mute all non-essential notifications for 20 minutes.",
        ],
        "MEDIUM": [
            "Move 2 low-priority tasks to tomorrow's list.",
            "Step away from your laptop for 15 minutes.",
            "Collapse all clutter into one folder on your desktop.",
            "Break one big problem into 3 tiny steps.",
            "Pick the easiest task on your list and finish it.",
        ],
        "HIGH": [
            "Block a 90-minute focus window on your calendar.",
            "Cut your to-do list down to 1 critical item.",
            "Sketch tomorrow's plan on a single index card.",
            "Delegate or cancel one pending responsibility now.",
            "Set a firm stop-work time for today.",
        ],
    },
    "UNDIRECTED": {
        "LOW": [
            "Doodle freely on a blank page for 2 minutes.",
            "Write 2 topics you are mildly curious about.",
            "Listen to one track from a genre you rarely play.",
            "Rearrange one small item on your desk.",
            "Change your wallpaper to something inspiring.",
        ],
        "MEDIUM": [
            "Read one article on a completely new topic.",
            "Sketch a rough layout of your ideal workspace.",
            "Learn one sentence in a language you do not speak.",
            "Write 3 side-project ideas without judging them.",
            "Watch a 5-minute explainer on something new.",
        ],
        "HIGH": [
            "Watch a 20-minute tech talk or documentary clip.",
            "Draft a 3-step plan for a personal side project.",
            "Browse a technical forum or research thread for 15 minutes.",
            "Set up a blank repo for an experimental idea.",
            "Read the intro docs for a framework you are curious about.",
        ],
    },
}

DOMAIN_TO_CATEGORY: Dict[str, str] = {
    "STUDY": "Study", "CAREER": "Focus", "EMOTIONAL": "Self",
    "SOCIAL": "Self", "PHYSICAL": "Health", "PURPOSE": "Self",
    "OVERLOAD": "Focus", "UNDIRECTED": "New",
}

DOMAIN_TO_TIME: Dict[str, str] = {
    "STUDY": "Today", "CAREER": "Today", "EMOTIONAL": "Anytime",
    "SOCIAL": "Today", "PHYSICAL": "Today", "PURPOSE": "Today",
    "OVERLOAD": "Now", "UNDIRECTED": "Anytime",
}

# ── Rate-limit tracker ─────────────────────────────────────────────────────────
_last_task_times: Dict[str, Dict[str, datetime]] = {}

def _can_push_task(uid: str, domain: str) -> bool:
    now  = datetime.now(timezone.utc)
    last = _last_task_times.get(uid, {}).get(domain)
    return last is None or (now - last) >= timedelta(hours=MIN_HOURS_BETWEEN_TASKS)

def _record_task_push(uid: str, domain: str) -> None:
    _last_task_times.setdefault(uid, {})[domain] = datetime.now(timezone.utc)


# ── Time Safeguard ─────────────────────────────────────────────────────────────
def extract_time_constraints(user_message: str) -> str:
    msg   = user_message.lower()
    rules: List[str] = []

    m = re.search(
        r"(?:sleep|bed|sleeping)\s*(?:at|by|around)?\s*(\d{1,2})(?::(\d{2}))?\s*(pm|am)?", msg
    )
    if m:
        hour, meridiem = int(m.group(1)), m.group(3) or "pm"
        rules.append(f"User sleeps at {hour}{meridiem}. Task MUST finish before {hour}{meridiem}.")

    m = re.search(
        r"(?:exam|interview|class|work|test)\s*(?:at|by)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", msg
    )
    if m:
        hour, meridiem = int(m.group(1)), m.group(3) or "am"
        rules.append(f"User has a commitment at {hour}{meridiem}. Task must finish before then.")

    m = re.search(r"(?:have|free for|only)\s*(\d+)\s*(mins?|minutes?|hours?)", msg)
    if m:
        rules.append(f"Available time: {m.group(1)} {m.group(2)} only.")

    return " ".join(rules) if rules else "No time restrictions."


# ── Output validator ───────────────────────────────────────────────────────────
_JUNK_PATTERNS = [
    r'(?i)output\s*:\s*\{',              # OUTPUT: {
    r'(?i)\{\s*["\']tasks["\']',         # {"tasks":
    r'(?i)\["task\s*\d',                 # ["task 1"
    r"(?i)^(i\s|i'm|i'll|i will|i can|i am|i'd|let me|allow me)",
    r"(?i)^(sure|of course|absolutely|great|noted|understood|got it)",
    r"(?i)^(here'?s?|here is|here are)",
    r"(?i)^(feeling|you seem|you look|it sounds|that sounds|i hear)",
    r"(?i)^(based on|as requested|the task is|the action is)",
    r"(?i)^(task:|output:|command:|result:|action:|step:)",
    r"(?i)^(a potential|a possible|an ultra|an actionable)",
    r"(?i)(write a 2-sentence journal entry now text one)",  # echo of example
    r"\{.*\}",                           # any JSON braces
    r"\[.*\]",                           # any JSON arrays
]

_JUNK_RE = re.compile("|".join(_JUNK_PATTERNS))

_IMPERATIVE_RE = re.compile(
    r"(?i)^(write|take|open|send|set|read|call|close|drink|step|do|complete|"
    r"list|draft|book|log|text|reply|clear|schedule|spend|follow|prepare|"
    r"reach|share|organise|organize|move|watch|sketch|plan|review|record|"
    r"download|check|pick|choose|start|finish|try|ask|message|find|make|"
    r"create|build|delete|add|update|save|note|jot|draw|explore|walk|"
    r"breathe|stretch|cook|eat|rest|focus|block|mute|cancel|commit|post|"
    r"comment|join|attend|confirm|collect|sort|switch|turn|launch|remove)\b"
)


def _is_valid_task(text: str) -> bool:
    """Returns True only if text is a clean, short, imperative task sentence."""
    if not text:
        return False
    text = text.strip().strip('"').strip("'")
    if _JUNK_RE.search(text):
        return False
    if not _IMPERATIVE_RE.match(text):
        return False
    word_count = len(text.split())
    if word_count < 3 or word_count > 12:
        return False
    return True


def _clean_task(raw: str) -> str:
    """Strip quotes and truncate to 8 words max."""
    text = raw.strip().strip('"').strip("'").strip("\u201c\u201d\u2018\u2019")
    m = re.search(r"[.!?]", text)
    if m:
        text = text[: m.end()].strip()
    words = text.split()
    if len(words) > 8:
        text = " ".join(words[:8]) + "..."
    return text


# ── TASK_BANK picker ───────────────────────────────────────────────────────────
def pick_task_text(domain: str, energy: str) -> str:
    bank    = TASK_BANK.get(domain, TASK_BANK["UNDIRECTED"])
    options = bank.get(energy, bank.get("MEDIUM", []))
    return random.choice(options) if options else "Take one slow deep breath now."


# ── Firestore client helper ────────────────────────────────────────────────────
def _get_db(firebase_service, fs):
    db = None
    if firebase_service:
        for attr in ["db", "firestore", "client", "_db", "_firestore"]:
            if hasattr(firebase_service, attr):
                val = getattr(firebase_service, attr)
                if val is not None:
                    db = val
                    break
    if db is None:
        db = fs.client()
    return db


# ── Together API (LLaMA 70B) ───────────────────────────────────────────────────
def _generate_via_together_api(
    user_message: str, domain: str, energy: str, time_rules: str
) -> Optional[str]:
    """
    Minimal prompt — NO examples (examples caused the model to echo them back).
    Strict stop tokens prevent JSON output, preamble, and multi-sentence replies.
    """
    if not TOGETHER_API_KEY:
        return None

    system_msg = (
        "You are a task formatter. "
        "Output ONE short task sentence only. "
        "Start with an imperative verb. "
        "Maximum 8 words. End with a period. "
        "No explanation, no preamble, no quotes, no JSON."
    )

    user_msg = (
        f"Domain: {domain}\n"
        f"Energy: {energy}\n"
        f"Time: {time_rules}\n"
        f"User: \"{user_message}\"\n\n"
        "Task:"
    )

    try:
        response = requests.post(
            TOGETHER_API_URL,
            json={
                "model": LLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg},
                ],
                "max_tokens": 30,
                "temperature": 0.10,
                "stop": [
                    "\n", "User:", "Assistant:",
                    "Here", "I'll", "I will", "I can", "Sure",
                    "Of course", "Let me", "Task:", "Output:",
                    "{", "[",
                ],
            },
            headers={
                "Authorization": f"Bearer {TOGETHER_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        return raw or None
    except Exception as exc:
        logger.warning(f"task_generator: Together API failed — {exc}")
        return None


# ── Main entry point ───────────────────────────────────────────────────────────
async def push_task_to_firestore(
    uid: str,
    classification: Dict,
    firebase_service,
    user_message: str = "",
    llm_generate_fn=None,
) -> Optional[str]:
    """
    Generates ONE clean task and writes it to Firestore.

    WHY llm_generate_fn IS IGNORED:
    The llm_generate_fn parameter is Hope's Ollama *chat* function. When called
    with a task-generation prompt it returns Hope's conversational reply, not a
    task (e.g. "You seem to have a clear plan..." or "Feeling calm, I'm glad...").
    We skip it entirely and use the Together API → TASK_BANK pipeline instead.

    Pipeline:
      1. Together API  (LLaMA 70B, strictly validated)
      2. TASK_BANK     (guaranteed clean, always works)
    """
    if firebase_service is None:
        logger.warning("task_generator: Firebase not available — skipping.")
        return None

    trigger      = classification.get("task_trigger", "NO")
    domain       = classification.get("life_domain",  "UNDIRECTED")
    energy       = classification.get("energy_level", "MEDIUM")
    trigger_conf = classification.get("confidence", {}).get("task_trigger", {}).get("YES", 0.0)

    if trigger != "YES":
        return None
    if trigger_conf < TRIGGER_CONFIDENCE_THRESHOLD:
        logger.debug(f"task_generator: confidence {trigger_conf:.2f} below threshold.")
        return None

    # ── Firestore rate-limit check ────────────────────────────────────────────
    try:
        from firebase_admin import firestore as fs
        db  = _get_db(firebase_service, fs)
        now = datetime.now(timezone.utc)

        if db is not None:
            docs = (
                db.collection("tiny_steps")
                  .where("userId", "==", uid)
                  .order_by("date", direction=fs.Query.DESCENDING)
                  .limit(5)
                  .get()
            )
            for doc in docs:
                data       = doc.to_dict()
                doc_domain = data.get("domain")
                doc_date   = data.get("date")
                if doc_domain == domain and doc_date:
                    if not doc_date.tzinfo:
                        doc_date = doc_date.replace(tzinfo=timezone.utc)
                    if (now - doc_date) < timedelta(hours=MIN_HOURS_BETWEEN_TASKS):
                        logger.info(f"task_generator: rate-limit hit — uid={uid} domain={domain}")
                        return None
    except Exception as q_exc:
        logger.warning(f"task_generator: Firestore rate-limit query failed — {q_exc}")

    if not _can_push_task(uid, domain):
        logger.debug(f"task_generator: in-memory rate-limit — uid={uid} domain={domain}")
        return None

    # ── Time constraints ──────────────────────────────────────────────────────
    time_rules = extract_time_constraints(user_message)

    # ── Generation pipeline ───────────────────────────────────────────────────
    task_text = ""

    # 1️⃣  Together API
    if TOGETHER_API_KEY:
        raw = _generate_via_together_api(user_message, domain, energy, time_rules)
        if raw and _is_valid_task(raw):
            task_text = _clean_task(raw)
            logger.info(f"task_generator: Together API → \"{task_text}\"")
        elif raw:
            logger.warning(f"task_generator: Together API junk → \"{raw}\" — using TASK_BANK.")

    # 2️⃣  TASK_BANK (always clean, never fails)
    if not task_text:
        task_text = pick_task_text(domain, energy)
        logger.info(f"task_generator: TASK_BANK → \"{task_text}\"")

    # ── Firestore write ───────────────────────────────────────────────────────
    try:
        from firebase_admin import firestore as fs
        db = _get_db(firebase_service, fs)

        db.collection("tiny_steps").add({
            "userId":           uid,
            "task":             task_text,
            "category":         DOMAIN_TO_CATEGORY.get(domain, "New"),
            "time":             DOMAIN_TO_TIME.get(domain, "Today"),
            "domain":           domain,
            "completed":        False,
            "source":           "chatbot",
            "history":          [False] * 31,
            "sage_highlighted": True,
            "sage_reason":      f"Based on what you shared ({domain.lower()}, {energy.lower()} energy)",
            "sage_suggested":   True,
            "date":             fs.SERVER_TIMESTAMP,
        })
        _record_task_push(uid, domain)
        logger.info(
            f"task_generator: ✅ pushed uid={uid} domain={domain} energy={energy} "
            f"conf={trigger_conf:.2f} | \"{task_text}\""
        )
        return task_text

    except Exception as exc:
        logger.error(f"task_generator: Firestore write failed — {exc}")
        return None