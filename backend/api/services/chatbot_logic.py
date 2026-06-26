"""
HEALING_WITH_HOPE — api/services/chatbot_logic.py  v8.2
CRISIS FLOW (simplified, single path):
  Round 1: Listen & understand
  Round 2: Value of life message
  Round 3: Different angle on life value
  Round 4+: Sri Lankan human help contacts ONLY

CONTACTS (Sri Lanka):
  📞 Sumithrayo: 0707 308 308 / 0767 520 620
  📞 CCC Foundation Crisis Line: 1333
  📞 National Mental Health Helpline: 1926

v8.1 CHANGES vs v8.0:
  - Added ConversationContext.last_stage1_push_domain / last_stage1_push_time
    (throttling bookkeeping for the new silent Stage 1 classifier hook)
  - Added HopeChatbot._situation_classifier attribute (optional, None by default)
  - Added HopeChatbot._run_stage1_silent() and _generate_stage1_task()
  - process_message() now calls _run_stage1_silent() once per turn

v8.2 CHANGES vs v8.1:
  - _run_stage1_silent() now calls api/services/task_generator.push_task_to_firestore()
    directly (in a background thread) instead of appending to ctx.tiny_steps.
  - REASON: the TinySteps UI reads a richer Firestore document shape
    (category, time, domain, a 31-day `history` streak array,
    sage_reason/sage_highlighted for the suggestion tooltip) that a plain
    string in ctx.tiny_steps cannot carry. task_generator.py already builds
    that exact shape, plus its own LLaMA prompt + time-constraint safeguards
    + TASK_BANK fallback + its own (uid, domain, 3-hour) rate limiter — reuse
    it rather than duplicating a second, thinner task-generation path here.
  - Added HopeChatbot._firebase_service attribute (optional, None by default;
    set to your firebase_service instance so push_task_to_firestore() has a
    real client). _generate_stage1_task() is now LEGACY/unused but kept for
    backward compatibility with any external imports.
  - api/routes/chat.py needs NO changes: it diffs ctx.tiny_steps, which this
    method no longer touches at all, so there is no double-write risk.
"""

import re
import json
import time
import logging
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Deque, Any
from enum import Enum

logger = logging.getLogger(__name__)

_sbert_instance: Any = None


# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATES = {
    "listen_first_contact": """
ROLE: First contact. Warm genuine greeting.
RULES: 1-2 sentences max. Natural friend tone. End with one open question.
Do NOT use flowery language or metaphors.
""",
    "listen_reflect_light": """
ROLE: Early listening. Low-intensity share.
RULES: Paraphrase their feeling. 2 sentences max. One open question. No solutions yet.
""",
    "listen_reflect_medium": """
ROLE: Mid-depth listening. Moderate intensity.
RULES: Reference something specific. Acknowledge difficulty first. 2 sentences max. No advice yet.
""",
    "listen_reflect_deep": """
ROLE: Deep listening. High intensity disclosure.
RULES: Lead with acknowledgment. Make them feel heard. 2 sentences max. No menu yet.
""",
    "listen_transition_to_menu": """
ROLE: User has shared enough. Offer support options.
RULES: One warm sentence. Ask what would feel most helpful. 2 sentences max.
""",
    "listen_neutral_greeting": """
ROLE: Casual or neutral message received.
RULES: 1-2 sentences. Real friend tone. One casual follow-up question.
""",
    "physical_illness_response": """
ROLE: User mentioned physical illness or pain.
RULES: Acknowledge physical discomfort first. 2 sentences max. One gentle question.
Do NOT launch into emotional support techniques.
""",
    "physical_tiny_steps": """
ROLE: User is physically unwell.
ILLNESS CONTEXT: {illness_context}
RULES: Suggest 3 tiny physical restorative steps. Number them 1, 2, 3. One sentence each.
""",
    "stuck_normalize": """
ROLE: User feels stuck or frozen.
RULES: Normalize briefly. Ask one orienting question. 2 sentences max.
""",
    "stuck_two_choices": """
ROLE: User still stuck after orientation.
RULES: Offer two paths — listen OR calm the feeling. 2 sentences max. Warm tone.
""",
    "technique_permission_ask": """
ROLE: Preparing to offer a calming technique.
TECHNIQUE: {technique_name}
RULES: One sentence reflecting their feeling. One sentence asking permission to try {technique_name}.
Use "if you are open to it". Never force.
""",
    "technique_delivery_breathing": """
ROLE: Guiding breathing exercise. STEP: {step_number}
RULES: Step 1=breathe in slowly. Step 2=breathe out slowly. Step 3=rest and repeat.
One short sentence per step. Check in after.
""",
    "technique_delivery_grounding": """
ROLE: Guiding 5-4-3-2-1 grounding. STEP: {step_number}
RULES: Step 1=5 things you see. Step 2=4 things you touch. Step 3=3 things you hear. Step 4=2 smell 1 taste.
Ask them to name things. One step per message.
""",
    "technique_delivery_inner_hug": """
ROLE: Guiding inner hug exercise.
RULES: Ask to cross arms gently. Breathe in slowly, shoulders soften on exhale.
One instruction per sentence. Warm and gentle.
""",
    "technique_delivery_safe_place": """
ROLE: Guiding safe place visualization.
RULES: Ask to close eyes if comfortable. Ask what they notice first — senses only.
2 sentences per exchange. Gentle pace.
""",
    "technique_delivery_havening": """
ROLE: Guiding havening technique.
RULES: Cross arms like a hug. Rub slowly shoulders to elbows. One instruction per sentence.
""",
    "technique_delivery_bilateral": """
ROLE: Guiding bilateral tapping.
RULES: Pause first. Tap left then right shoulder alternately. Slow rhythm 30 seconds. Brief calm instructions.
""",
    "technique_delivery_sensory": """
ROLE: Guiding sensory noticing for numb state.
RULES: Ask to notice one physical sensation. Just notice — not do anything. Very gentle.
""",
    "technique_delivery_binary_choice": """
ROLE: Guiding binary choice for overthinking.
RULES: Give one trivial choice to interrupt spiral. One sentence. Acknowledge decision warmly.
""",
    "technique_checkin": """
ROLE: Checking in after technique.
TECHNIQUE: {technique_name}
RULES: Ask how they feel now. Reference something specific. One warm curious sentence.
""",
    "technique_worked": """
ROLE: Technique helped.
TECHNIQUE: {technique_name}
RULES: Celebrate specifically — mention actual technique. One warm genuine sentence.
""",
    "technique_not_worked": """
ROLE: Technique did not help.
TECHNIQUE: {technique_name}
RULES: Acknowledge without disappointment. Normalize. Offer to try something else. 2 sentences max.
""",
    "just_talk_open": """
ROLE: Free conversation mode. Warm curious friend.
CONTEXT: {context_summary}
RULES: Respond to what they said. One follow-up question. No techniques or advice. 2-3 sentences max.
""",
    "just_talk_goal_noticed": """
ROLE: User mentioned a goal in just talk mode.
GOAL: {goal}
RULES: One warm sentence acknowledging goal. One question about what it means to them. Conversational.
""",
    "just_talk_transition": """
ROLE: Just talk has been going a while.
RULES: One sentence reflecting conversation. One question about what they need. Natural.
""",
    "tiny_plan_open_ask": """
ROLE: Starting tiny plan.
SITUATION: {situation}
CAPACITY: {capacity_level}
RULES: Ask what one small step comes to mind. LOW=emphasize tiny. One sentence invitation, one question.
""",
    "tiny_plan_personalize_step": """
ROLE: Personalizing a tiny step.
STEP: {step_text}
CAPACITY: {capacity_level}
RULES: Rewrite step as warm personal suggestion. Friend tone. One sentence.
""",
    "tiny_plan_suggest_ideas": """
ROLE: Suggest 3 tiny steps.
SITUATION: {situation}
CAPACITY: {capacity_level}
RULES: LOW=physical only. MEDIUM=simple mental. HIGH=slightly engaged.
Label Option 1, Option 2, Option 3. One sentence each.
""",
    "tiny_plan_completion_celebrate": """
ROLE: User completed a tiny step.
STEP: {step_text}
STREAK: {streak_days} days
RULES: Celebrate specifically — mention actual step. If streak>1 mention it. One warm sentence.
""",
    "tiny_plan_add_to_routine_ask": """
ROLE: Ask if user wants step in daily routine.
STEP: {step_text}
RULES: One friendly sentence asking about adding to routine. Not pressuring.
""",
    "tiny_plan_routine_time_ask": """
ROLE: Ask when to do routine step.
STEP: {step_text}
RULES: One simple question about timing. Brief and friendly.
""",
    "tiny_plan_routine_confirmed": """
ROLE: Routine step confirmed.
STEP: {step_text}
TIME: {time_of_day}
RULES: One sentence confirming addition. One warm sentence about building this habit.
""",
    "hope_message_situational": """
ROLE: User needs something hopeful.
SITUATION: {situation}
RULES: One genuinely hopeful thought tailored to their situation. Not toxic positivity.
2 sentences max. Warm and personal.
""",
    "hope_goal_confirm_add": """
ROLE: User shared a hope goal.
GOAL: {goal_text}
TIMEFRAME: {timeframe}
RULES: One warm sentence valuing what they shared. One sentence asking to add to Hope page.
""",
    "hope_goal_milestone_generate": """
ROLE: Generate milestone checkpoints silently.
GOAL: {goal_text}
TIMEFRAME: {timeframe}
OUTPUT: Return only JSON: {{"milestones": ["milestone 1", "milestone 2", "milestone 3"]}}
RULES: Emotionally framed milestones. Return ONLY the JSON.
""",
    "hope_goal_checkin": """
ROLE: Check in on a previously set goal.
GOAL: {goal_text}
DAYS LEFT: {days_left}
RULES: Ask how it FEELS — not how prepared. One question. Warm curious tone.
""",
    "hope_goal_achieved": """
ROLE: User achieved a goal.
GOAL: {goal_text}
RULES: Celebrate genuinely. Reference the journey. 2-3 sentences max.
""",

    # ── CRISIS TEMPLATES (3 rounds, single path) ──────────────────────────────
    "crisis_round_1": """
ROLE: User expressed suicidal or crisis thoughts. ROUND 1 — LISTEN ONLY. Do NOT give advice.
GOAL: Make them feel heard. Listen first.
RULES:
- Lead with quiet, genuine acknowledgment of their pain. No platitudes.
- Ask ONE open question: What has been happening? How long have they felt this way?
- Do NOT mention life value, hope, or any advice in this round.
- Sound like a real caring person, not a helpline script.
- 2-3 sentences max. No buttons, no options.
""",

    "crisis_round_2": """
ROLE: User still in crisis. ROUND 2 — VALUE OF LIFE (first attempt).
GOAL: Gently shift their perspective toward why their life has value.
RULES:
- First: briefly acknowledge what they shared (1 sentence max).
- Then: share ONE genuine reason their life has value — make it personal, not generic.
  Examples:
    "The fact that you are still here and still talking means something in you is still reaching."
    "Pain this sharp means you have been feeling deeply — that depth is a real part of who you are."
    "Reaching out right now takes courage. That matters."
- Ask ONE gentle question to keep them talking.
- 3 sentences max. Warm, real, no clichés. No options.
""",

    "crisis_round_3": """
ROLE: User still in crisis. ROUND 3 — DIFFERENT ANGLE on life value.
GOAL: Try a COMPLETELY DIFFERENT angle from round 2 to help shift their mindset.
RULES:
- Do NOT repeat the same idea from round 2.
- Offer a different reason their life has value. Focus on one of:
    their impact on others, the future they cannot see yet,
    or the pain itself showing how much they care.
  Examples:
    "The world is genuinely different with you in it, even when it does not feel that way."
    "When we are in this kind of pain, we cannot see the future — but that does not mean it is not there."
    "Someone out there would feel the loss of you, even if it does not feel that way right now."
- Ask ONE anchoring question:
  "Is there even one small thing — a person, a place, a moment — that has kept you here?"
- 3 sentences max. No options. No repetition from round 2.
""",

    "crisis_human_help": """
ROLE: User has not shifted after 3 rounds. Time for human support.
RULES:
- Open with genuine care: "I care about you, and I want to be honest with you."
- Say clearly: what you are carrying right now is more than a chatbot can hold alone.
- Say: a real person is ready to listen right now — no judgment, free to call.
- Do NOT apologise. This is the most caring thing to do.
- 3 sentences max, then contacts on SEPARATE lines exactly as written below.
- CONTACTS (Sri Lanka only — copy EXACTLY):
  📞 Sumithrayo: 0707 308 308 / 0767 520 620
  📞 CCC Foundation Crisis Line: 1333
  📞 National Mental Health Helpline: 1926
""",

    "crisis_post_stay": """
ROLE: User stayed after crisis flow.
RULES: One warm sentence glad they stayed. One gentle open question. Follow their lead completely.
Do NOT restart crisis script.
""",

    "panic_empathy_response": """
ROLE: User is experiencing a panic attack or severe anxiety spike.
RULES:
- Lead with grounding presence: "I am right here with you."
- Acknowledge the physical and emotional overwhelm — name it gently.
- Tell them they are safe and this will pass.
- Keep sentences very short — one idea per sentence.
- 3 sentences max. Warm, steady, calm tone.
- Do NOT ask lots of questions. Do NOT offer techniques yet — just presence first.
""",

    "panic_just_talk": """
ROLE: User chose to just talk during a panic attack or high anxiety moment.
CONTEXT: {context_summary}
RULES:
- Very short sentences — panic state means low reading capacity.
- Stay present and grounding. Reflect back what they say simply.
- Do NOT offer techniques unless they ask.
- One gentle follow-up question per response.
- 2-3 sentences max. Warm, slow, steady tone.
""",

    "passive_crisis_acknowledge": """
ROLE: User has shared multiple signals of emptiness, hopelessness, or not wanting to be here.
RULES: Lead with quiet care — not alarm. Acknowledge the weight of what they have been carrying.
2 sentences max. End with one gentle, open question.
Do NOT mention crisis contacts yet unless they ask.
""",

    "passive_crisis_gentle_check": """
ROLE: Gently checking if user is safe after passive hopelessness signals.
RULES: One warm sentence first. Then ask softly: "Are you having any thoughts of not wanting to be here?"
Do NOT make it clinical. Warm, friend tone.
""",

    "exit_feeling_better": """
ROLE: User is feeling better and leaving.
RULES: One warm sentence genuinely glad they feel better. Brief, complete. Do NOT ask them to keep talking.
""",
    "return_user_greeting": """
ROLE: Returning user.
RULES: Acknowledge they have been here before. Ask how they are feeling today. 2 sentences max.
""",
    "silence_gentle_nudge": """
ROLE: User has been silent.
RULES: No pressure. One warm sentence. Keep the door open.
""",
    "silence_after_crisis": """
ROLE: Silence after crisis conversation.
RULES: Very gentle. One sentence only. No questions. Warm and present.
""",
    "goal_anchor_reflect": """
ROLE: User mentioned a goal during conversation.
GOAL: {goal}
RULES: One sentence acknowledging goal. One open question about what it means to them.
""",
    "repeated_message_response": """
ROLE: User sent same message multiple times.
RULES: Acknowledge you heard them. Show it weighs deeply. Ask what is underneath. Do not say they are repeating.
""",
    "meaningless_input_response": """
ROLE: User sent unclear or very short message.
RULES: Gently let them know you are there. No pressure. One warm open sentence.
""",
    "empathetic_fallback": """
ROLE: General empathetic response.
RULES: Respond with warmth and genuine curiosity. One open question. 2 sentences max.
""",
    "unclear_input_response": """
ROLE: Unclear input — gibberish or accidental.
RULES: ONE sentence only. Do NOT say "I didn't understand". Say something like "Take your time 💜".
""",
    "thought_loop_response": """
ROLE: User stuck in thought loop.
REPEATED: {repeated_message}
RULES: Acknowledge repetition as meaningful. One warm sentence. One question about what is underneath.
""",
    "rate_limit_response": """
ROLE: User sending very rapidly.
RULES: One calm sentence. Invite them to take a breath. Warm slow grounding tone.
""",
    "ambiguous_clarify": """
ROLE: Ambiguous message.
MESSAGE: {user_message}
RULES: Respond warmly for both distress and casual. Leave door open. 2 sentences max.
""",
    "low_confidence_clarify": """
ROLE: Not sure what user needs.
RULES: One warm sentence. One open question. Do not mention uncertainty.
""",
    "multi_signal_escalation": """
ROLE: Multiple risk signals this session.
RISK LEVEL: {risk_level}
RULES: Reference whole session. One sentence about human support. Provide Sri Lankan crisis contacts only.
Warm, not clinical. 3 sentences max.
""",
    "repeated_rejection_of_help": """
ROLE: User declined support multiple times.
RULES: Respect autonomy. One sentence acknowledging choice. "I am here whenever you are ready."
Provide Sri Lankan crisis contacts quietly.
""",
    "session_acknowledgment": """
ROLE: Returning to menu after significant sharing.
THEMES: {session_themes}
RULES: One warm sentence referencing themes. Then offer menu naturally.
""",
    "gaming_detected_response": """
ROLE: User may be testing the chatbot.
RULES: No accusation. One warm sentence. Redirect: "Whatever brings you here, I am happy to talk."
""",
    "privacy_acknowledgment": """
ROLE: User asked about data or privacy.
RULES: Explain warmly — processed locally, no identifying info stored, can delete anytime.
This is AI support not clinical care. 3 sentences max.
""",
    "assistant_discover_situation": """
ROLE: Personal assistant beginning discovery.
SITUATION: {situation_summary}
CAPACITY: {capacity_level}
RULES: Ask ONE question — biggest thing on their mind. 2 sentences max. Friend tone.
""",
    "assistant_discover_freetime": """
ROLE: Learning about user's available time — specifically TIME OF DAY.
GOAL: {active_goal}
RULES: Ask warmly WHEN they have free time — morning, afternoon, or evening.
One friendly sentence. Casual, not scheduling. Do NOT ask how much time.
""",
    "assistant_discover_habits": """
ROLE: Learning user's focus style.
GOAL: {active_goal}
RULES: Ask one question about whether they focus better in short bursts or longer sessions.
Casual, curious, friendly. One sentence only.
""",
    "assistant_discover_blockers": """
ROLE: Understanding what is in the way.
GOAL: {active_goal}
RULES: Ask what feels hardest right now. One gentle question. Acknowledge situation first. 2 sentences max.
""",
    "assistant_create_plan": """
ROLE: Create a personalised plan.
GOAL: {active_goal}
FREE TIME: {free_time}
HABITS: {user_habits}
BLOCKERS: {blockers}
CAPACITY: {capacity_level}
DAYS: {days_available}
RULES: LOW=1-2 tiny steps. MEDIUM=3-4 steps. HIGH=fuller plan.
Address blocker directly. Numbered steps. Plain language. Max 5 steps. One encouraging sentence at end.
Each step MUST reference the goal: "{active_goal}".
""",
    "assistant_plan_confirm": """
ROLE: Presenting plan to user.
PLAN: {plan_text}
RULES: One warm intro sentence. Present plan. Ask if it feels doable or needs adjusting.
""",
    "assistant_plan_adjust": """
ROLE: Adjusting plan based on feedback.
ORIGINAL: {original_plan}
FEEDBACK: {user_feedback}
CAPACITY: {capacity_level}
RULES: Acknowledge first. Make specific adjustments. Ask if adjusted version feels better.
""",
    "assistant_generate_tasks": """
ROLE: Generate daily tasks from plan.
PLAN: {plan_text}
GOAL: {active_goal}
CAPACITY: {capacity_level}
TODAY: {today_str}
OUTPUT: Return only JSON: {{"tasks": ["task 1", "task 2"]}}
RULES:
- LOW capacity = 1 micro-task (5-10 minutes max)
- MEDIUM capacity = 2 tasks (15-20 minutes each)
- HIGH capacity = 3 tasks (30 minutes each)
- Each task MUST be specific and completable today
- Each task MUST reference the goal: "{active_goal}"
- Return ONLY JSON, no other text
""",
    "assistant_surface_task": """
ROLE: Surfacing a suggested task.
TASK: {task_text}
GOAL: {active_goal}
CAPACITY: {capacity_level}
RULES: One sentence connecting task to goal "{active_goal}". One sentence presenting task as suggestion.
Ask if they want to add to daily page.
""",
    "assistant_change_detected": """
ROLE: User mentioned something new or different.
CHANGE: {change_description}
RULES: One sentence acknowledging change. One question about updating plan or goals.
Sound natural — not "I detected".
""",
    "assistant_manual_change_detected": """
ROLE: User updated tasks or goals manually.
CHANGE: {change_description}
RULES: Reference specific change. Ask one question about it. 2 sentences max.
""",
    "assistant_proactive_checkin": """
ROLE: Proactively checking in on a goal.
GOAL: {active_goal}
DAYS SINCE: {days_since}
PROXIMITY: {proximity_description}
CAPACITY: {capacity_level}
RULES: Sound natural. If IMPROVING acknowledge progress. If DECLINING gentle curious check-in.
1-2 sentences. One gentle question.
""",
    "assistant_futurebloom_update": """
ROLE: Managing FutureBloom hope goals page.
CHANGE: {goal_change}
TIMEFRAME: {timeframe}
RULES: One warm sentence about the change. One confirming what was saved. Never judge their choice.
""",
    "assistant_confused_user": """
ROLE: Helping confused user figure out what they want.
SITUATION: {situation_summary}
RULES: Ask ONE clarifying question. Warm, patient, curious. 2 sentences max.
""",
    "assistant_first_step_confused": """
ROLE: Helping confused user take ONE first step.
SITUATION: {situation_summary}
CAPACITY: {capacity_level}
RULES: ONE step only. Match capacity. Frame as possibility not command.
""",
}

# ══════════════════════════════════════════════════════════════════════════════
# SUPPORT CLASSES
# ══════════════════════════════════════════════════════════════════════════════

class InputValidator:
    MIN_CHARS = 2
    MAX_CHARS = 2000
    _GIBBERISH    = re.compile(r"^[^aeiouAEIOU\s]{5,}$|^(.)\1{4,}$|^[\W\d_]+$", re.IGNORECASE)
    _EMOJI_ONLY   = re.compile(r"^[\U00010000-\U0010ffff\u2600-\u26FF\u2700-\u27BF\s]+$")
    _NUMBERS_ONLY = re.compile(r"^[\d\s.,%-]+$")
    _VOWELS       = re.compile(r"[aeiouAEIOU]")

    @classmethod
    def validate(cls, text: str) -> Tuple[bool, str]:
        t = text.strip()
        if not t:                           return False, "empty"
        if len(t) < cls.MIN_CHARS:          return False, "too_short"
        if len(t) > cls.MAX_CHARS:          return False, "too_long"
        if cls._NUMBERS_ONLY.match(t):      return False, "numbers_only"
        if cls._EMOJI_ONLY.match(t):        return False, "emoji_only"
        if cls._GIBBERISH.match(t):         return False, "gibberish"
        letters = re.findall(r"[a-zA-Z]", t)
        if len(letters) >= 6:
            vowels = cls._VOWELS.findall(t)
            if len(vowels) / len(letters) < 0.08:
                return False, "keyboard_mash"
        return True, "ok"


class RepetitionTracker:
    RATE_WINDOW_SECS  = 8
    RATE_MAX_MESSAGES = 5
    SPAM_SECS         = 10
    LOOP_THRESHOLD    = 3

    def __init__(self):
        self._timestamps: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=20))
        self._last: Dict[str, Tuple[str, float]]  = {}

    def record(self, uid: str, message: str) -> Tuple[str, int]:
        now   = time.time()
        msg_l = message.strip().lower()
        ts    = self._timestamps[uid]
        ts.append(now)
        recent_count = sum(1 for t in ts if now - t < self.RATE_WINDOW_SECS)
        if recent_count > self.RATE_MAX_MESSAGES:
            return "rate_flood", recent_count
        last_msg, last_ts = self._last.get(uid, ("", 0.0))
        self._last[uid] = (message, now)
        if msg_l == last_msg.lower() and (now - last_ts) < self.SPAM_SECS:
            return "spam", 1
        return "ok", 0

    def thought_loop_count(self, uid: str, message: str, history: List[Dict]) -> int:
        msg_l = message.strip().lower()
        return sum(1 for h in history
                   if h.get("role") == "user"
                   and h.get("content", "").strip().lower() == msg_l)

    def reset(self, uid: str):
        self._timestamps.pop(uid, None)
        self._last.pop(uid, None)


class SessionRiskTracker:
    WEIGHTS = {
        "suicidal_language":     0.45,
        "hopelessness_language": 0.20,
        "isolation_language":    0.08,
        "finality_language":     0.30,
        "method_mention":        0.50,
        "high_intensity":        0.08,
        "rejected_help":         0.10,
    }
    _HOPELESS  = re.compile(r"\b(hopeless|pointless|no point|nothing matters|give up|no future|why bother|lost interest|nothing makes me happy|feel empty|feel numb|tired of everything|can.t anymore|not be here|disappear)\b", re.IGNORECASE)
    _ISOLATION = re.compile(r"\b(nobody cares|no one would miss|burden to everyone|better without me|completely alone|everyone.s better without me|world.s better without me)\b", re.IGNORECASE)
    _FINALITY  = re.compile(r"\b(last time|goodbye forever|won.t be here|saying goodbye|final message|after i.m gone|fade away|not be here anymore)\b", re.IGNORECASE)
    _METHOD    = re.compile(r"\b(pills|overdose|rope|knife|gun|bridge|jump|hang|slash|poison)\b", re.IGNORECASE)

    def __init__(self):
        self._scores:     Dict[str, float]     = {}
        self._signals:    Dict[str, List[str]] = defaultdict(list)
        self._rejections: Dict[str, int]       = defaultdict(int)

    def score(self, uid: str) -> float:
        return min(self._scores.get(uid, 0.0), 1.0)

    def level(self, uid: str) -> str:
        s = self.score(uid)
        if s >= 0.8: return "critical"
        if s >= 0.6: return "high"
        if s >= 0.3: return "elevated"
        return "normal"

    def update(self, uid: str, message: str, state: "UserState", intensity: float):
        delta, signals = 0.0, []
        if state.value == "suicidal":
            delta += self.WEIGHTS["suicidal_language"]; signals.append("suicidal")
        if self._HOPELESS.search(message):
            delta += self.WEIGHTS["hopelessness_language"]; signals.append("hopeless")
        if self._ISOLATION.search(message):
            delta += self.WEIGHTS["isolation_language"]; signals.append("isolation")
        if self._FINALITY.search(message):
            delta += self.WEIGHTS["finality_language"]; signals.append("finality")
        if self._METHOD.search(message):
            delta += self.WEIGHTS["method_mention"]; signals.append("method")
        if intensity >= 0.75:
            delta += self.WEIGHTS["high_intensity"]; signals.append("high_intensity")
        self._scores[uid] = min(self._scores.get(uid, 0.0) + delta, 1.0)
        self._signals[uid].extend(signals)

    def record_rejection(self, uid: str):
        self._rejections[uid] += 1
        if self._rejections[uid] >= 3:
            self._scores[uid] = max(self._scores.get(uid, 0.0) + 0.1, 0.3)

    def get_signals(self, uid: str) -> List[str]:
        return list(set(self._signals.get(uid, [])))

    def reset(self, uid: str):
        self._scores.pop(uid, None)
        self._signals.pop(uid, None)
        self._rejections.pop(uid, None)


class MoodTrajectory:
    def __init__(self):
        self._history: Dict[str, List[float]] = defaultdict(list)

    def record(self, uid: str, intensity: float):
        h = self._history[uid]
        h.append(intensity)
        if len(h) > 30: self._history[uid] = h[-30:]

    def trajectory(self, uid: str) -> str:
        h = self._history.get(uid, [])
        if len(h) < 3: return "unknown"
        avg_r    = sum(h[-3:]) / 3
        avg_b    = sum(h[:3])  / 3
        delta    = avg_r - avg_b
        variance = max(h[-3:]) - min(h[-3:])
        if variance > 0.35: return "volatile"
        if delta < -0.15:   return "improving"
        if delta > 0.15:    return "declining"
        return "stable"

    def current_avg(self, uid: str) -> float:
        h = self._history.get(uid, [])
        if not h: return 0.15
        return sum(h[-5:]) / min(len(h), 5)

    def reset(self, uid: str):
        self._history.pop(uid, None)


class ConfidenceGate:
    THRESHOLD = 0.35

    @staticmethod
    def score(message: str, state: "UserState", intensity: float) -> float:
        t             = message.lower()
        base          = min(intensity * 0.8, 0.7)
        length_bonus  = min(len(t.split()) / 50, 0.2)
        contradiction = 0.0
        if re.search(r"\b(but|however|although|though)\b", t, re.IGNORECASE):
            contradiction += 0.10
        if re.search(r"\b(not really|kind of|sort of|maybe|i think)\b", t, re.IGNORECASE):
            contradiction += 0.08
        direct = 0.3 if state.value == "suicidal" else (
                 0.1 if re.search(r"\b(i feel|i am|i.m)\b", t, re.IGNORECASE) else 0.0)
        return max(min(base + length_bonus + direct - contradiction, 1.0), 0.0)

    @classmethod
    def is_confident(cls, message: str, state: "UserState", intensity: float) -> bool:
        if state.value in ("suicidal", "panic"): return True
        return cls.score(message, state, intensity) >= cls.THRESHOLD


class ResponseFilter:
    _DIAGNOSTIC    = re.compile(r"\b(you have|you.re suffering from|you are diagnosed|you exhibit symptoms of|this is (depression|anxiety|ptsd|bipolar))\b", re.IGNORECASE)
    _FALSE_PROMISE = re.compile(r"\b(everything will be (fine|okay|alright)|it.ll all work out|things will definitely|i promise|i guarantee)\b", re.IGNORECASE)
    _TRIVIALISING  = re.compile(r"\b(just think positive|cheer up|calm down|it.s not that bad|others have it worse|snap out of it)\b", re.IGNORECASE)
    _CLINICAL      = re.compile(r"\b(nervous system|prefrontal cortex|amygdala|oxytocin|dopamine|serotonin|cortisol|neural|neuroscience|cognitive reappraisal|dysregulation|limbic|parasympathetic|sympathetic|fight or flight|trauma response|trigger warning)\b", re.IGNORECASE)
    _ADVICE_ADJ    = re.compile(r"\b(you should|you need to|my advice is|you must|make sure you|i recommend)\b", re.IGNORECASE)

    DISCLAIMER = (
        "\n\n_(I want to be honest — I am an AI and not a professional therapist. "
        "For serious concerns, a qualified mental health professional can help more.)_"
    )

    @classmethod
    def clean(cls, text: str, add_disclaimer: bool = False) -> Optional[str]:
        if not text: return None
        for p in (cls._DIAGNOSTIC, cls._FALSE_PROMISE, cls._TRIVIALISING, cls._CLINICAL):
            text = p.sub("", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        text = re.sub(r"\s([.,?!])", r"\1", text)
        if len(text.split()) < 4: return None
        if add_disclaimer and cls._ADVICE_ADJ.search(text):
            text += cls.DISCLAIMER
        return text

    @classmethod
    def needs_disclaimer(cls, text: str) -> bool:
        return bool(cls._ADVICE_ADJ.search(text or ""))


class AmbiguityHandler:
    _AMBIGUOUS_CRISIS = re.compile(r"\b(i want to die|kill me|i could kill|ugh kill me now|this is killing me)\b", re.IGNORECASE)
    _HUMOUR           = re.compile(r"\b(lol|lmao|haha|hehe|joking|jk|just kidding|sarcasm|😂|🤣)\b", re.IGNORECASE)
    _CASUAL_HEAVY     = re.compile(r"\b(i.m dead|dying of (laughter|boredom)|killing it|exam is killing me|work is killing me)\b", re.IGNORECASE)

    @classmethod
    def classify(cls, message: str, state: "UserState") -> Tuple[str, float]:
        if state.value == "suicidal":
            if cls._HUMOUR.search(message):       return "ambiguous", 0.5
            if cls._CASUAL_HEAVY.search(message): return "ambiguous", 0.6
            return "serious", 0.95
        if cls._AMBIGUOUS_CRISIS.search(message):
            if cls._HUMOUR.search(message):       return "casual", 0.7
            return "ambiguous", 0.5
        return "casual", 0.85


class GameDetector:
    def __init__(self):
        self._crisis_times: Dict[str, List[float]] = defaultdict(list)

    def check(self, uid: str, message: str, state: "UserState", history: List[Dict]) -> bool:
        now = time.time()
        if state.value == "suicidal":
            times  = self._crisis_times[uid]
            times.append(now)
            recent = [t for t in times if now - t < 60]
            self._crisis_times[uid] = recent
            if len(recent) >= 4: return True
            if re.search(r"\b(lol|jk|just kidding|haha|test|testing)\b", message, re.IGNORECASE):
                return True
        return False

    def reset(self, uid: str):
        self._crisis_times.pop(uid, None)


class FallbackChain:
    def __init__(self):
        self._failures: Dict[str, int] = defaultdict(int)

    def record_failure(self, uid: str):
        self._failures[uid] += 1

    def count(self, uid: str) -> int:
        return self._failures.get(uid, 0)

    def should_restart(self, uid: str) -> bool:
        return self._failures.get(uid, 0) >= 5

    def reset(self, uid: str):
        self._failures.pop(uid, None)


# ══════════════════════════════════════════════════════════════════════════════
# STATE DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

class UserState(Enum):
    NEUTRAL  = "neutral"
    CALM     = "calm"
    SAD      = "sad"
    ANXIOUS  = "anxious"
    STUCK    = "stuck"
    PANIC    = "panic"
    SUICIDAL = "suicidal"
    PHYSICAL = "physical"
    EXIT     = "exit"


class TechniqueState(Enum):
    NONE       = "none"
    PERMISSION = "permission"
    ACTIVE     = "active"
    DONE       = "done"


# ── Positive signal detection ─────────────────────────────────────────────────
_RE_POSITIVE_SHIFT = re.compile(
    r"\b("
    r"feel(ing)? (a little |slightly |somewhat )?(better|calmer|okay|ok|alright|lighter)|"
    r"(a little |slightly )?(better|calmer|okay|ok)|"
    r"thank(s| you)|that helped|"
    r"feel(ing)? less|not as bad|"
    r"i('m| am) okay|i('m| am) fine|"
    r"just needed to talk|feel heard|"
    r"starting to feel|"
    r"still here|i stayed"
    r")\b",
    re.IGNORECASE
)


def _user_seems_better(message: str, intensity: float, trajectory: str) -> bool:
    if _RE_POSITIVE_SHIFT.search(message):
        return True
    if intensity < 0.35 and trajectory in ("improving", "stable"):
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# STATE & INTENSITY DETECTION
# ══════════════════════════════════════════════════════════════════════════════

_RE_SUICIDAL = re.compile(
    r"\b("
    r"suicid|want to die|wanna die|kill myself|end my life|"
    r"don.t want to live|no reason to live|better off dead|end it all|"
    r"can.t go on|i want to die|don.t wanna live|not worth living|"
    r"i want to end|don.t wanna life|"
    r"wish i could disappear|want to disappear|just disappear|"
    r"don.t want to be here|not want to be here|not be here anymore|"
    r"don.t wanna be here|wish i wasn.t here|wish i wasn.t alive|"
    r"rather not exist|rather be dead|rather not be alive|"
    r"not want to exist|don.t want to exist|stop existing|"
    r"fade away|just fade away|vanish|wish i could vanish|"
    r"want it all to stop|want everything to stop|just want it to stop|"
    r"want this to stop|make it stop|everything just stop|"
    r"can.t do this anymore|can.t keep going|can.t keep doing this|"
    r"can.t take it anymore|can.t take this anymore|"
    r"done with everything|done with life|done with it all|"
    r"giving up on everything|given up on everything|given up on life|"
    r"giving up on life|no point anymore|no point in anything|"
    r"no point in living|see no point|"
    r"don.t see the point|what.s the point|why bother being here|"
    r"tired of being here|tired of living|tired of existing|"
    r"tired of everything|so tired of everything|"
    r"everyone.s better without me|better off without me|"
    r"world.s better without me|no one would miss me|"
    r"feel nothing|feeling nothing|don.t feel anything|"
    r"completely empty|completely numb|totally empty|"
    r"lost all hope|no hope left|no hope anymore"
    r")\b",
    re.IGNORECASE)

_RE_PASSIVE_CRISIS = re.compile(
    r"("
    r"nothing.{0,20}(make|makes).{0,10}happy|nothing makes me happy|"
    r"nothing brings me joy|nothing feels good|nothing feels right|"
    r"not happy anymore|can.t enjoy|don.t enjoy anything|"
    r"stopped enjoying|used to (enjoy|like|love|care)|"
    r"don.t care anymore|stopped caring|lost interest|lost all interest|"
    r"what.s the point|what is the point|what.s even the point|what is even the point|"
    r"why even try|why bother|"
    r"life feels pointless|life feels meaningless|feel meaningless|"
    r"feel.{0,5}empty|feel so empty|empty inside|hollow inside|"
    r"feel.{0,5}numb|feeling numb|gone numb|numb inside|emotionally numb|"
    r"feel nothing|feeling nothing|don.t feel anything|"
    r"feel like a burden|feel like i.m a burden|everyone.{0,10}better without|"
    r"disconnected from (everything|life|people|myself)|"
    r"don.t recognize myself|don.t feel like myself|"
    r"so exhausted.{0,20}(life|living|everything)|beyond exhausted|drained of everything|"
    r"tired of (everything|living|being here|existing)|"
    r"can.t keep (going|doing this|living like this)"
    r")",
    re.IGNORECASE)

_RE_PANIC = re.compile(
    r"\b(panic attack|i.m panicking|can.t breathe|heart is racing|can.t calm down|"
    r"freaking out|i.m shaking|can.t stop shaking|overwhelmed right now)\b",
    re.IGNORECASE)
_RE_PHYSICAL = re.compile(
    r"\b(fever|i.m sick|feel sick|headache|nausea|nauseous|vomiting|cold|flu|"
    r"sore throat|body ache|stomach ache|not well|unwell|ill |feeling ill|"
    r"i have a (cold|fever|flu|headache)|throwing up|i have fever)\b",
    re.IGNORECASE)

_RE_SAD = re.compile(
    r"\b("
    r"sad|depress|grief|griev|heartbreak|crying|cry|tears|"
    r"hopeless|empty|lonely|alone|miss|lost|hurt|broken|"
    r"devastat|mourn|upset|"
    r"lost interest|no interest|not interested in anything|"
    r"can.t enjoy|don.t enjoy|nothing brings joy|"
    r"nothing makes me happy|stopped enjoying|"
    r"feel numb|feeling numb|gone numb|emotionally numb|"
    r"feel empty|feel so empty|hollow|"
    r"no hope|losing hope|feel hopeless|feel so hopeless|"
    r"what.s the point|why bother|nothing matters|"
    r"so tired|exhausted all the time|completely drained|"
    r"given up|feel like giving up"
    r")\b",
    re.IGNORECASE)

_RE_ANXIOUS = re.compile(
    r"\b(anxious|anxiety|stress|stressed|worried|worry|nervous|fear|afraid|"
    r"overwhelm|tense|dread|scared|terrif)\b",
    re.IGNORECASE)
_RE_STUCK = re.compile(
    r"\b(stuck|don.t know what to do|nothing is clear|can.t decide|can.t move|"
    r"frozen|confused|don.t know where to start|nothing makes sense|paralys)\b",
    re.IGNORECASE)
_RE_EXIT = re.compile(
    r"\b(i.m good now|i.m better now|feeling better now|thank you|thanks|bye|goodbye|"
    r"that helped|much better now|i feel okay now|i.m okay now|feel better now)\b",
    re.IGNORECASE)
_RE_CALM = re.compile(
    r"\b(feeling calm|feeling peaceful|feeling relaxed|feeling settled|"
    r"i feel calm|i feel relaxed|i feel at ease|much calmer|"
    r"calmed down|settled now|at peace|feeling content)\b",
    re.IGNORECASE)

_RE_HIGH_INTENSITY = re.compile(
    r"\b(can.t|cannot|never|always|everything|nothing|hate|devastat|shatter|"
    r"broken|hopeless|worthless|agony|unbearable|want to die|end it|"
    r"disappear|give up|giving up|no point|no reason|fade away|"
    r"tired of everything|lost all|can.t anymore|done with|"
    r"stop existing|not be here|don.t care anymore)\b",
    re.IGNORECASE)

_RE_GOAL_EXAM    = re.compile(r"\b(exam|exams|test|quiz|study|studying|assignment|thesis|submit|coursework|grade|grades|pass|fail|university|course)\b", re.IGNORECASE)
_RE_GOAL_WORK    = re.compile(r"\b(job|work|career|interview|project|deadline|promotion|salary|fired|resign)\b", re.IGNORECASE)
_RE_GOAL_HEALTH  = re.compile(r"\b(lose weight|get fit|exercise|run|workout|healthy|diet|sleep better)\b", re.IGNORECASE)
_RE_GOAL_FINANCE = re.compile(r"\b(save money|debt|loan|afford|buy a house|financial|budget)\b", re.IGNORECASE)
_RE_GOAL_RELATION= re.compile(r"\b(relationship|partner|friend|family|connect|social|lonely)\b", re.IGNORECASE)

_RE_TIME_MORNING   = re.compile(r"\b(morning|mornings|early|dawn|before noon|am\b)\b", re.IGNORECASE)
_RE_TIME_AFTERNOON = re.compile(r"\b(afternoon|afternoons|midday|noon|lunch|after lunch|pm\b)\b", re.IGNORECASE)
_RE_TIME_EVENING   = re.compile(r"\b(evening|evenings|night|nights|after work|after school|late)\b", re.IGNORECASE)
_RE_TIME_WEEKEND   = re.compile(r"\b(weekend|weekends|saturday|sunday)\b", re.IGNORECASE)


def detect_state_and_intensity(text: str) -> Tuple["UserState", float]:
    t = text.lower()
    if _RE_SUICIDAL.search(t): return UserState.SUICIDAL, 1.0
    if _RE_PANIC.search(t):    return UserState.PANIC, 0.9
    if _RE_PHYSICAL.search(t): return UserState.PHYSICAL, 0.2
    if _RE_EXIT.search(t):     return UserState.EXIT, 0.1

    high_count = len(_RE_HIGH_INTENSITY.findall(t))
    word_count  = max(len(t.split()), 1)
    intensity   = min(0.25 + (high_count * 0.2) + (word_count / 250), 1.0)

    if _RE_SAD.search(t):     return UserState.SAD, max(intensity, 0.4)
    if _RE_ANXIOUS.search(t): return UserState.ANXIOUS, max(intensity, 0.4)
    if _RE_STUCK.search(t):   return UserState.STUCK, max(intensity, 0.35)
    if _RE_CALM.search(t):    return UserState.CALM, 0.2
    return UserState.NEUTRAL, 0.15


def detect_passive_crisis(text: str) -> bool:
    return bool(_RE_PASSIVE_CRISIS.search(text))


def intensity_to_listen_template(intensity: float) -> str:
    if intensity < 0.3: return "listen_neutral_greeting"
    if intensity < 0.5: return "listen_reflect_light"
    if intensity < 0.7: return "listen_reflect_medium"
    return "listen_reflect_deep"


def intensity_to_capacity(intensity: float) -> str:
    if intensity >= 0.7: return "LOW"
    if intensity >= 0.4: return "MEDIUM"
    return "HIGH"


def situation_bucket(history: List[Dict], state: "UserState") -> str:
    recent = " ".join(
        h["content"] for h in history[-10:] if h.get("role") == "user"
    ).lower()
    if any(w in recent for w in ["exam","study","test","grade","university","course","assignment","thesis"]):
        return "exam"
    if any(w in recent for w in ["work","job","deadline","project","boss","career","interview"]):
        return "work"
    if any(w in recent for w in ["relation","friend","family","partner","break","fight","miss","lonely","love"]):
        return "relationship"
    if any(w in recent for w in ["fever","sick","ill","cold","flu","headache","unwell"]):
        return "physical_wellness"
    if state == UserState.SAD:     return "sad"
    if state == UserState.ANXIOUS: return "anxious"
    if state == UserState.STUCK:   return "stuck"
    return "general"


_GOAL_PATTERNS = [
    r"\b(pass|passing)\b.{0,30}\b(exam|test|course)\b",
    r"\b(graduate|graduation|degree|finish\s+uni)\b",
    r"\b(get|find|land|start)\b.{0,20}\b(job|work|career)\b",
    r"\b(finish|complete|submit)\b.{0,20}\b(project|thesis|degree)\b",
    r"\b(want\s+to|wanna|hope\s+to|dream\s+of)\b.{0,30}\b(be|become|achieve|do|make)\b",
    r"\b(my\s+goal|my\s+dream|someday|one\s+day|in\s+the\s+future)\b",
    r"\b(save\s+money|buy\s+a\s+house|travel|learn|move)\b",
]


def extract_goal(text: str) -> Optional[str]:
    for p in _GOAL_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return text.strip()
    return None


def auto_detect_goal_label(text: str) -> Optional[str]:
    if _RE_GOAL_EXAM.search(text):     return "Pass my exams"
    if _RE_GOAL_WORK.search(text):     return "Manage my work"
    if _RE_GOAL_HEALTH.search(text):   return "Improve my health"
    if _RE_GOAL_FINANCE.search(text):  return "Improve my finances"
    if _RE_GOAL_RELATION.search(text): return "Improve my relationships"
    return None


def extract_time_of_day(text: str) -> Optional[str]:
    if _RE_TIME_MORNING.search(text):   return "morning"
    if _RE_TIME_AFTERNOON.search(text): return "afternoon"
    if _RE_TIME_EVENING.search(text):   return "evening"
    if _RE_TIME_WEEKEND.search(text):   return "weekends"
    return None


TECHNIQUE_LABELS = {
    "grounding":  "5-4-3-2-1 grounding",
    "inner_hug":  "the inner hug",
    "safe_place": "the safe place visualization",
    "havening":   "havening",
    "bilateral":  "bilateral tapping",
    "sensory":    "sensory noticing",
    "binary":     "the tiny choice",
}

# Sri Lankan crisis contacts
_SL_CONTACTS = (
    "📞 Sumithrayo: 0707 308 308 / 0767 520 620\n"
    "📞 CCC Foundation Crisis Line: 1333\n"
    "📞 National Mental Health Helpline: 1926"
)

# ══════════════════════════════════════════════════════════════════════════════
# CONVERSATION CONTEXT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConversationContext:
    user_id: str
    chat_count: int = 0
    consecutive_neutral: int = 0
    current_state: UserState = UserState.NEUTRAL
    previous_state: Optional[UserState] = None
    current_intensity: float = 0.15
    had_crisis_this_session: bool = False
    listen_depth: int = 0
    emotional_stabilized: bool = False
    menu_shown: bool = False
    menu_cycle: int = 0

    # ── Crisis (single linear flow) ──────────────────────────────────────────
    crisis_round: int = 0
    crisis_in_flow: bool = False

    technique_state: TechniqueState = TechniqueState.NONE
    active_technique: Optional[str] = None
    technique_step: int = 0
    in_panic_protocol: bool = False
    panic_step: int = 0
    panic_just_talk_mode: bool = False
    panic_just_talk_exchanges: int = 0
    stuck_orientation_asked: bool = False
    stuck_two_choice_shown: bool = False
    in_just_talk: bool = False
    just_talk_exchanges: int = 0
    in_routine_flow: bool = False
    in_routine_time: bool = False
    routine_step_text: str = ""
    hope_capture_mode: bool = False
    hope_timeframe: Optional[str] = None
    pending_hope_goal: Optional[str] = None
    detected_goal: Optional[str] = None
    goal_question_asked: bool = False
    exit_pending: bool = False
    returning_user: bool = False
    healing_points: int = 0
    streak_days: int = 0
    tiny_steps: List[str] = field(default_factory=list)
    daily_routine: List[Dict] = field(default_factory=list)
    hope_goals: Dict[str, list] = field(default_factory=lambda: {
        "3_months": [], "1_year": [], "2_years": []
    })
    history: List[Dict] = field(default_factory=list)
    last_activity: Optional[datetime] = None
    session_risk_level: str = "normal"
    mood_trajectory: str = "unknown"
    help_rejections: int = 0
    ambiguity_count: int = 0
    low_confidence_count: int = 0
    gaming_suspected: bool = False
    disclaimer_shown: bool = False
    situation_summary: str = ""
    situation_profile: Dict = field(default_factory=dict)
    in_assistant_mode: bool = False
    assistant_goal: str = ""
    assistant_plan: str = ""
    assistant_discovery_step: int = 0
    assistant_free_time: str = ""
    assistant_free_time_raw: str = ""
    assistant_habits: str = ""
    assistant_blockers: str = ""
    assistant_mode_source: str = ""
    goal_proximity_scores: Dict[str, float] = field(default_factory=dict)
    goal_proximity_history: Dict[str, List[float]] = field(default_factory=dict)
    proactive_shown_this_session: bool = False
    sessions_since_goal_mention: int = 0
    passive_crisis_count: int = 0
    passive_crisis_escalated: bool = False

    # ── Stage 1 silent classifier bookkeeping (added v8.1, behavior changed v8.2) ──
    # v8.2: tracks the most recent (domain, time) that triggered a Firestore
    # push via push_task_to_firestore() (no longer ctx.tiny_steps -- see
    # module docstring). Used only as a cheap session-local early-exit before
    # spawning a background push thread; task_generator's own _can_push_task()
    # rate limiter (3 hours per uid+domain) is the authoritative throttle.
    last_stage1_push_domain: Optional[str] = None
    last_stage1_push_time: Optional[datetime] = None


# ══════════════════════════════════════════════════════════════════════════════
# SILENT LISTENER
# ══════════════════════════════════════════════════════════════════════════════

_SITU_PATTERNS = {
    "exam":         re.compile(r"\b(exam|test|assignment|thesis|submit|deadline|study|studying|university|course|grade|fail|pass|marks|quiz|coursework)\b", re.IGNORECASE),
    "work":         re.compile(r"\b(job|work|boss|office|meeting|fired|resign|deadline|project|career|interview|salary|colleague|promotion|workplace)\b", re.IGNORECASE),
    "relationship": re.compile(r"\b(partner|boyfriend|girlfriend|husband|wife|friend|family|fight|argument|breakup|divorce|miss|lonely|alone|relationship|dating)\b", re.IGNORECASE),
    "health":       re.compile(r"\b(sick|doctor|hospital|medicine|pain|anxiety|depression|therapy|diagnosis|treatment|unwell|fever|mental health)\b", re.IGNORECASE),
    "financial":    re.compile(r"\b(money|debt|bills|afford|broke|savings|loan|rent|financial|expenses|income)\b", re.IGNORECASE),
    "loss":         re.compile(r"\b(died|death|lost|grief|funeral|passed away|miss them|bereavement)\b", re.IGNORECASE),
    "personal":     re.compile(r"\b(myself|my life|who i am|identity|purpose|meaning|direction|future|what i want)\b", re.IGNORECASE),
}
_URGENCY_RE  = re.compile(r"\b(today|tonight|tomorrow|this week|next week|soon|urgent|deadline|due|running out of time|no time)\b", re.IGNORECASE)
_FREETIME_RE = re.compile(r"\b(free|available|evenings?|mornings?|weekends?|afternoons?|after \w+|before \w+|\d+ hours?|\d+ minutes?)\b", re.IGNORECASE)
_HABIT_RE    = re.compile(r"\b(usually|always|tend to|prefer|better when|work best|focus|routine|every day|daily|habit|short bursts?|long sessions?|varies)\b", re.IGNORECASE)
_CHANGE_RE   = re.compile(r"\b(changed|updated|decided|no longer|actually|instead|different|dropped|added|removed|new goal|new plan)\b", re.IGNORECASE)


def _silent_extract(ctx: ConversationContext, message: str) -> None:
    now     = datetime.utcnow().isoformat()
    urgency = "high" if _URGENCY_RE.search(message) else "medium"
    for situ, pattern in _SITU_PATTERNS.items():
        if pattern.search(message):
            existing = ctx.situation_profile.get(situ, {})
            ctx.situation_profile[situ] = {
                "urgency":        urgency if urgency == "high" else existing.get("urgency", "medium"),
                "days_mentioned": existing.get("days_mentioned", 0) + 1,
                "last_seen":      now,
                "first_seen":     existing.get("first_seen", now),
            }

    tod = extract_time_of_day(message)
    if tod:
        ctx.assistant_free_time_raw = message.strip()
        if ctx.in_assistant_mode or not ctx.assistant_free_time:
            ctx.assistant_free_time = tod

    if _HABIT_RE.search(message) and ctx.in_assistant_mode:
        ctx.assistant_habits = (ctx.assistant_habits + " " + message.strip()).strip()[-300:]

    if not ctx.detected_goal and not ctx.assistant_goal:
        auto_goal = auto_detect_goal_label(message)
        if auto_goal:
            ctx.detected_goal = auto_goal

    ctx._pending_summary_update = getattr(ctx, "_pending_summary_update", 0) + 1


def _build_situation_summary(ctx: ConversationContext) -> str:
    if not ctx.situation_profile:
        return "No specific situation identified yet."
    parts = []
    for situ, data in sorted(ctx.situation_profile.items(),
                              key=lambda x: x[1].get("days_mentioned", 0), reverse=True):
        parts.append(f"{situ} ({data.get('urgency','medium')} urgency)")
    return ", ".join(parts[:3])


def _compute_goal_proximity(ctx: ConversationContext, goal: str) -> float:
    if not goal:
        return 0.0
    global _sbert_instance
    if _sbert_instance is not None and _sbert_instance.is_ready:
        try:
            recent = [h["content"] for h in ctx.history[-10:]
                      if h.get("role") == "user"][-5:]
            if not recent:
                return 0.0
            scores = [_sbert_instance.goal_proximity(m, goal) for m in recent]
            return float(sum(scores) / len(scores))
        except Exception as e:
            logger.debug(f"SBERT proximity failed: {e}")
    keywords      = [w for w in goal.lower().split() if len(w) > 3][:5]
    recent_msgs   = [h["content"].lower() for h in ctx.history[-20:] if h.get("role") == "user"]
    positive_count = 0
    for msg in recent_msgs:
        if any(kw in msg for kw in keywords):
            positive_count += 1 if not _RE_SAD.search(msg) and not _RE_ANXIOUS.search(msg) else -0.5
    return min(max(positive_count / 8.0, 0.0), 1.0)

# ══════════════════════════════════════════════════════════════════════════════
# HOPE CHATBOT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class HopeChatbot:

    def __init__(self):
        self.contexts: Dict[str, ConversationContext] = {}
        self._llama_model  = None
        self._llama_ready  = False
        self._warmup_done  = False
        self._sbert        = None
        self._validator    = InputValidator()
        self._repetition   = RepetitionTracker()
        self._risk         = SessionRiskTracker()
        self._mood         = MoodTrajectory()
        self._confidence   = ConfidenceGate()
        self._filter       = ResponseFilter()
        self._ambiguity    = AmbiguityHandler()
        self._game         = GameDetector()
        self._fallback     = FallbackChain()
        # Stage 1 silent situation classifier (NEW in v8.1) — optional.
        # None by default; wire up by setting this to an object exposing
        # .is_loaded (bool) and .classify(text) -> dict with keys
        # task_trigger / life_domain / energy_level / confidence.
        self._situation_classifier = None
        # Firebase service handle for Stage 1's direct Firestore push (v8.2).
        # None by default; set this to your firebase_service instance
        # (the same one api/routes/chat.py imports) so push_task_to_firestore()
        # has a real client to write through. If left None, _run_stage1_silent()
        # silently no-ops -- it never raises for a missing service.
        self._firebase_service = None
        self._load_llama()
        self._load_sbert()

    def _load_llama(self):
        try:
            from api.models.llama_model import HopeLlamaModel
            self._llama_model = HopeLlamaModel()
            loaded = self._llama_model.load(background=False)
            if loaded:
                self._llama_ready = True
                logger.info("✅ LLaMA ready at chatbot startup.")
                self._warmup_llama()
            else:
                logger.warning("⚠️ LLaMA did not load. Fallback mode active.")
        except Exception as e:
            logger.error(f"LLaMA startup failed: {e}")

    def _warmup_llama(self):
        try:
            result = self._llama_model.generate(
                "warmup", system_prompt="Reply only: ready", max_new_tokens=5)
            if result:
                self._warmup_done = True
                logger.info("✅ LLaMA warmup complete.")
        except Exception as e:
            logger.warning(f"LLaMA warmup non-critical failure: {e}")

    def _load_sbert(self):
        global _sbert_instance
        try:
            import importlib
            sbert_mod = None
            for mod_path in ("api.services.sbert_service", "services.sbert_service", "sbert_service"):
                try:
                    sbert_mod = importlib.import_module(mod_path)
                    break
                except ModuleNotFoundError:
                    continue
            if sbert_mod is None:
                raise ImportError("sbert_service not found")
            self._sbert     = getattr(sbert_mod, "SBERTService")()
            _sbert_instance = self._sbert
            if self._sbert.is_ready:
                logger.info("✅ SBERT loaded and ready.")
            else:
                logger.warning("⚠️ SBERT not ready — keyword fallback active.")
        except Exception as e:
            logger.warning(f"SBERT load skipped: {e}. Keyword fallback active.")
            self._sbert     = None
            _sbert_instance = None

    def llama_status(self) -> Dict:
        sbert_status = self._sbert.status() if self._sbert else {"ready": False}
        return {
            "llama": {"loaded": self._llama_ready, "warmup_done": self._warmup_done,
                      "model": "llama3.2:3b via Ollama"},
            "sbert": sbert_status,
        }

    def _ctx(self, uid: str) -> ConversationContext:
        if uid not in self.contexts:
            self.contexts[uid] = ConversationContext(user_id=uid)
        return self.contexts[uid]

    def _llm(self, ctx: ConversationContext, template_key: str,
             user_message: str = "", template_vars: Optional[Dict] = None,
             fallback: str = "I am here with you. 💜") -> str:

        if not self._llama_ready or self._llama_model is None:
            return fallback

        template = TEMPLATES.get(template_key, "")
        if not template:
            logger.warning(f"Template '{template_key}' not found.")
            return fallback

        if template_vars:
            for k, v in template_vars.items():
                val = str(v)[:200] if v else ""
                template = template.replace("{" + k + "}", val)

        _LONG_TEMPLATES = {
            "assistant_create_plan", "assistant_generate_tasks",
            "hope_goal_milestone_generate", "assistant_plan_confirm",
        }
        max_tokens = 100 if template_key in _LONG_TEMPLATES else 50

        try:
            result = self._llama_model.generate_with_context(
                user_message[:200] or "(continuing)",
                state=ctx.current_state.value,
                context_summary=self._context_summary(ctx),
                memory_hint=self._memory_hint(ctx),
                extra_instruction=template,
                max_new_tokens=max_tokens,
            )
            if result and len(result.strip()) >= 8:
                cleaned = self._safety_filter(result)
                if cleaned:
                    return self._trim(cleaned)
        except Exception as e:
            logger.error(f"LLM error (template='{template_key}'): {e}")

        return fallback

    def _safety_filter(self, text: str) -> Optional[str]:
        forbidden = [
            "nervous system", "prefrontal cortex", "amygdala", "oxytocin",
            "dopamine", "serotonin", "cortisol", "neural", "neuroscience",
            "cognitive reappraisal", "dysregulation", "limbic", "parasympathetic",
            "sympathetic", "fight or flight", "trauma response", "trigger warning",
        ]
        for term in forbidden:
            text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE).strip()
        return text if len(text.split()) >= 5 else None

    @staticmethod
    def _trim(text: str, limit: int = 55) -> str:
        words = text.split()
        if len(words) <= limit:
            return text
        trimmed = " ".join(words[:limit])
        last = max(trimmed.rfind("."), trimmed.rfind("?"), trimmed.rfind("!"))
        return trimmed[:last + 1] if last > len(trimmed) // 2 else trimmed + "…"

    def _context_summary(self, ctx: ConversationContext) -> str:
        msgs = [h["content"] for h in ctx.history[-4:] if h.get("role") == "user"]
        return " | ".join(msgs[-2:])[:120] if msgs else ""

    def _memory_hint(self, ctx: ConversationContext) -> Optional[str]:
        if ctx.detected_goal:
            return f"goal: {ctx.detected_goal[:60]}"
        if ctx.tiny_steps:
            return f"planned: '{ctx.tiny_steps[0][:40]}'"
        for tf, goals in ctx.hope_goals.items():
            if goals:
                return f"hope ({tf.replace('_',' ')}): '{goals[0][:40]}'"
        return None

    @staticmethod
    def _is_meaningless(text: str) -> bool:
        t = text.strip()
        if not t or len(t) == 1: return True
        if re.match(r"^[\d\s.,]+$", t): return True
        if re.match(r"^[^a-zA-Z0-9]+$", t): return True
        if len(t) > 4:
            vowels  = len(re.findall(r"[aeiouAEIOU]", t))
            letters = len(re.findall(r"[a-zA-Z]", t))
            if letters >= 4 and vowels / max(letters, 1) < 0.1: return True
        return bool(re.match(r"^(.)\1{3,}$", t))

    @staticmethod
    def _resp(text: str, options: List[Dict], state: str,
              priority: str = "normal") -> Dict:
        return {"text": text, "options": options,
                "metadata": {"state": state, "priority": priority}}

    def _record_history(self, ctx: ConversationContext, role: str,
                        content: str, state: str = ""):
        entry = {"role": role, "content": content}
        if state: entry["state"] = state
        ctx.history.append(entry)

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 1 — SILENT SITUATION CLASSIFIER → AUTO TASK PUSH (v8.2)
    # ══════════════════════════════════════════════════════════════════════════
    #
    # DESIGN NOTE (changed in v8.2): _run_stage1_silent() now calls
    # push_task_to_firestore() (api/services/task_generator.py) directly,
    # in a background thread, instead of appending to ctx.tiny_steps.
    #
    # WHY: the TinySteps UI reads a richer Firestore document shape
    # (category, time, domain, a 31-day `history` streak array,
    # sage_reason/sage_highlighted for the "why was this suggested" tooltip)
    # that a plain string in ctx.tiny_steps cannot carry. task_generator.py
    # already builds that exact document shape, plus its own time-constraint
    # extraction and LLaMA prompt formatting — reuse it rather than
    # duplicating a second, thinner task-generation path here.
    #
    # BECAUSE this writes to Firestore directly, chat.py's existing
    # before/after diff on ctx.tiny_steps must NOT also try to persist
    # Stage 1's contribution (it never touches ctx.tiny_steps now, so the
    # diff naturally won't see anything new from this method — no code
    # change needed in chat.py for this specifically). Two independent
    # writers of *ctx.tiny_steps* would have been the duplicate-write risk;
    # since this method no longer touches that list at all, that risk does
    # not apply. task_generator.py's own _can_push_task() rate-limit (3 hours
    # per uid+domain) is the authoritative throttle; the check below is a
    # cheap early-exit so we skip the classifier call entirely when we
    # already know from this session's own bookkeeping that we just pushed.
    #
    def _run_stage1_silent(self, ctx: ConversationContext, message: str) -> None:
        """
        Runs the Stage 1 situation classifier on the user message and, if a
        task should be pushed, calls push_task_to_firestore() in a background
        thread. Never raises -- all errors are logged and swallowed so a
        classifier problem can never break the main chat flow. Called from
        process_message() on every valid, non-spam, non-crisis user message.
        """
        classifier   = self._situation_classifier
        firebase_svc = getattr(self, "_firebase_service", None)
        if classifier is None or not getattr(classifier, "is_loaded", False):
            return
        if firebase_svc is None:
            return

        try:
            classification = classifier.classify(message)
            if not classification:
                return

            if classification.get("task_trigger") != "YES":
                return

            trigger_conf = (
                classification.get("confidence", {})
                .get("task_trigger", {})
                .get("YES", 0.0)
            )
            if trigger_conf < 0.60:
                return

            domain = classification.get("life_domain", "")
            now    = datetime.utcnow()

            # Cheap session-local early-exit (10 min) before even attempting
            # the push. task_generator._can_push_task() applies its own,
            # authoritative 3-hour-per-domain rate limit on top of this --
            # this check just avoids spawning a thread we already know would
            # be redundant within the same short conversation.
            if (ctx.last_stage1_push_domain == domain
                    and ctx.last_stage1_push_time is not None
                    and (now - ctx.last_stage1_push_time) < timedelta(minutes=10)):
                return

            ctx.last_stage1_push_domain = domain
            ctx.last_stage1_push_time   = now

            llm_fn = None
            if self._llama_ready and self._llama_model is not None:
                llm_fn = lambda prompt, max_new_tokens=40: (
                    self._llama_model.generate(
                        prompt,
                        system_prompt="You are a helpful personal growth assistant.",
                        max_new_tokens=max_new_tokens,
                    )
                )

            def _push():
                try:
                    import asyncio
                    from api.services.task_generator import push_task_to_firestore

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    task_text = loop.run_until_complete(
                        push_task_to_firestore(
                            uid              = ctx.user_id,
                            classification   = classification,
                            firebase_service = firebase_svc,
                            user_message     = message,
                            llm_generate_fn  = llm_fn,
                        )
                    )
                    loop.close()

                    if task_text:
                        ctx.healing_points += 5
                        logger.info(
                            f"Stage1 push: uid={ctx.user_id} domain={domain} "
                            f"energy={classification.get('energy_level')} "
                            f"task='{task_text[:60]}'"
                        )
                except Exception as e:
                    logger.error(f"Stage1 background push failed (uid={ctx.user_id}): {e}")

            threading.Thread(target=_push, daemon=True).start()

        except Exception as e:
            logger.error(f"_run_stage1_silent error (uid={ctx.user_id}): {e}")

    def _generate_stage1_task(self, ctx: ConversationContext, message: str,
                               domain: str, capacity: str) -> Optional[str]:
        """
        LEGACY (v8.1) — superseded by task_generator.push_task_to_firestore(),
        which now owns Stage 1 task text generation (LLaMA + TASK_BANK
        fallback + time-constraint safeguards). Kept only so any external
        code that imported this method directly does not break; no longer
        called by _run_stage1_silent().
        """
        goal = ctx.assistant_goal or ctx.detected_goal or (domain.replace("_", " ").lower() if domain else "this")
        today_str = datetime.utcnow().strftime("%A %d %B")

        tasks_json_str = self._llm(
            ctx, "assistant_generate_tasks", message,
            template_vars={
                "plan_text":         f"Silent detection from conversation: {message[:150]}",
                "active_goal":       goal[:60],
                "capacity_level":    capacity,
                "situation_summary": domain,
                "today_str":         today_str,
            },
            fallback=f'{{"tasks": ["One small step related to {domain.lower()}"]}}' if domain
                     else '{"tasks": []}'
        )

        try:
            clean  = tasks_json_str.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean)
            tasks  = parsed.get("tasks", [])
            if tasks:
                return tasks[0]
        except Exception:
            pass

        return f"One small step related to {domain.lower()}" if domain else None

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════════

    def process_message(self, uid: str, message: str) -> Dict:
        ctx = self._ctx(uid)
        ctx.chat_count    += 1
        ctx.previous_state = ctx.current_state
        ctx.last_activity  = datetime.utcnow()

        valid, reason = self._validator.validate(message)
        if not valid:
            return self._handle_invalid_input(ctx, uid, message, reason)

        rep_type, rep_count = self._repetition.record(uid, message)
        if rep_type == "rate_flood":
            text = self._llm(ctx, "rate_limit_response",
                             fallback="Take your time — I am right here. 💜")
            self._record_history(ctx, "user", message, "neutral")
            self._record_history(ctx, "assistant", text)
            return self._resp(text, [], "rate_limited")

        if rep_type == "spam":
            loop_count = self._repetition.thought_loop_count(uid, message, ctx.history)
            if loop_count >= self._repetition.LOOP_THRESHOLD:
                return self._handle_thought_loop(ctx, uid, message)

            _spam_state, _spam_intensity = detect_state_and_intensity(message)
            if _spam_state == UserState.SUICIDAL:
                ctx.current_state     = _spam_state
                ctx.current_intensity = _spam_intensity
                ctx.had_crisis_this_session = True
                self._risk.update(uid, message, _spam_state, _spam_intensity)
                self._record_history(ctx, "user", message, _spam_state.value)
                resp = self._crisis_route(ctx, message)
                self._record_history(ctx, "assistant", resp.get("text", ""))
                return resp
            if detect_passive_crisis(message):
                ctx.passive_crisis_count += 1

            msg_lower    = message.strip().lower()
            _is_greeting = re.match(r"^(hi+|hey+|hello+|hiya|sup|yo|howdy)[\s!?.]*$",
                                    msg_lower, re.IGNORECASE)
            text = self._llm(ctx,
                             "listen_neutral_greeting" if _is_greeting else "unclear_input_response",
                             message,
                             fallback="Hey again! 💜 What is on your mind?" if _is_greeting
                                      else "Take your time — I am listening whenever you are ready. 💜")
            self._record_history(ctx, "user", message, "neutral")
            self._record_history(ctx, "assistant", text)
            return self._resp(text, [], "spam_redirect")

        state, intensity = detect_state_and_intensity(message)

        ambiguity_class, _ = self._ambiguity.classify(message, state)
        if ambiguity_class == "ambiguous":
            ctx.ambiguity_count += 1
        elif ambiguity_class == "casual" and state.value == "suicidal":
            state     = UserState.NEUTRAL
            intensity = 0.2

        if self._game.check(uid, message, state, ctx.history):
            ctx.gaming_suspected = True
            text = self._llm(ctx, "gaming_detected_response",
                             fallback="Whatever brings you here, I am genuinely happy to talk. 💜")
            self._record_history(ctx, "user", message, state.value)
            self._record_history(ctx, "assistant", text)
            return self._resp(text, self._menu_options(ctx), "gaming_redirect")

        _is_short_greeting = len(message.strip().split()) <= 4
        if (not _is_short_greeting
                and not self._confidence.is_confident(message, state, intensity)
                and state not in (UserState.EXIT, UserState.PHYSICAL,
                                  UserState.SUICIDAL, UserState.PANIC,
                                  UserState.NEUTRAL, UserState.CALM)):
            ctx.low_confidence_count += 1
            if ctx.low_confidence_count <= 1:
                text = self._llm(ctx, "low_confidence_clarify",
                                 fallback="I am here. 💜 What is going on for you right now?")
                self._record_history(ctx, "user", message, "unclear")
                self._record_history(ctx, "assistant", text)
                return self._resp(text, [], "clarifying")
            ctx.low_confidence_count = 0

        self._risk.update(uid, message, state, intensity)
        ctx.session_risk_level = self._risk.level(uid)
        if (ctx.session_risk_level in ("high", "critical")
                and not ctx.had_crisis_this_session
                and state.value not in ("suicidal", "panic")):
            return self._multi_signal_escalation(ctx, uid, message)

        self._mood.record(uid, intensity)
        ctx.mood_trajectory     = self._mood.trajectory(uid)
        ctx.current_state       = state
        ctx.current_intensity   = intensity
        ctx.consecutive_neutral = (
            ctx.consecutive_neutral + 1
            if state in (UserState.NEUTRAL, UserState.CALM) else 0
        )

        goal = extract_goal(message)
        if goal and not ctx.detected_goal:
            ctx.detected_goal = goal

        if detect_passive_crisis(message) and state not in (UserState.SUICIDAL, UserState.PANIC):
            ctx.passive_crisis_count += 1
            if ctx.passive_crisis_count >= 2 and not ctx.passive_crisis_escalated:
                ctx.passive_crisis_escalated = True
                self._risk._scores[uid] = max(self._risk._scores.get(uid, 0.0) + 0.3, 0.4)
                ctx.session_risk_level = self._risk.level(uid)

        _silent_extract(ctx, message)
        if getattr(ctx, "_pending_summary_update", 0) >= 4:
            ctx._pending_summary_update = 0
            ctx.situation_summary       = _build_situation_summary(ctx)

        active_goal = ctx.assistant_goal or ctx.detected_goal or ""
        if active_goal:
            score = _compute_goal_proximity(ctx, active_goal)
            key   = active_goal[:40]
            ctx.goal_proximity_scores[key] = score
            hist  = ctx.goal_proximity_history.setdefault(key, [])
            hist.append(score)
            if len(hist) > 20:
                ctx.goal_proximity_history[key] = hist[-20:]

        # ── Stage 1: silent situation detection → auto tiny-step append ──────
        # (NEW v8.1) Appends to ctx.tiny_steps ONLY -- chat.py's existing
        # before/after diff picks up the new entry and handles the Firestore
        # write, so no duplicate persistence path is introduced here. Skipped
        # entirely for SUICIDAL/PANIC since the rest of this turn will be
        # short-circuited into crisis/panic routing via _route(), and a
        # silent task-add should never compete with that priority.
        if state not in (UserState.SUICIDAL, UserState.PANIC):
            self._run_stage1_silent(ctx, message)

        self._record_history(ctx, "user", message, state.value)
        resp = self._route(ctx, state, intensity, message)

        if "text" in resp and resp["text"]:
            needs_disclaimer = (
                self._filter.needs_disclaimer(resp["text"])
                and not ctx.disclaimer_shown
            )
            cleaned = self._filter.clean(resp["text"], add_disclaimer=needs_disclaimer)
            if cleaned:
                resp["text"] = self._trim(cleaned)
                if needs_disclaimer:
                    ctx.disclaimer_shown = True
            else:
                self._fallback.record_failure(uid)
                resp["text"] = self._llm(ctx, "empathetic_fallback",
                                          fallback="I am here with you. 💜")

        if self._fallback.should_restart(uid):
            resp["text"] = (resp.get("text", "") +
                            "\n\n_(If things feel unclear, we can always start fresh.)_")
            self._fallback.reset(uid)

        self._record_history(ctx, "assistant", resp.get("text", ""))
        return resp

    # ══════════════════════════════════════════════════════════════════════════
    # ROUTER
    # ══════════════════════════════════════════════════════════════════════════

    def _route(self, ctx: ConversationContext, state: UserState,
               intensity: float, message: str) -> Dict:
        msg = message.strip().lower()

        if state == UserState.SUICIDAL:
            ctx.in_panic_protocol       = False
            ctx.in_just_talk            = False
            ctx.active_technique        = None
            ctx.technique_state         = TechniqueState.NONE
            ctx.had_crisis_this_session = True
            ctx.panic_just_talk_mode    = False
            return self._crisis_route(ctx, message)

        if ctx.crisis_in_flow:
            trajectory = self._mood.trajectory(ctx.user_id)
            better = _user_seems_better(message, intensity, trajectory)
            if better and state != UserState.SUICIDAL:
                ctx.crisis_in_flow = False
                text = self._llm(
                    ctx, "crisis_post_stay", message,
                    fallback=(
                        "I am really glad you stayed. 💜 "
                        "How are you feeling right now?"
                    )
                )
                return self._resp(text, [], "crisis_recovery")
            text = self._llm(
                ctx, "just_talk_open", message,
                template_vars={"context_summary": self._context_summary(ctx)},
                fallback="I am still here. 💜 Keep going — I am listening."
            )
            return self._resp(text, [], "crisis_stay")

        if (ctx.passive_crisis_escalated
                and detect_passive_crisis(message)
                and not ctx.had_crisis_this_session):
            return self._passive_crisis_response(ctx, message)

        if state == UserState.PANIC and not ctx.in_panic_protocol:
            ctx.in_panic_protocol    = True
            ctx.panic_step           = 0
            ctx.active_technique     = None
            ctx.panic_just_talk_mode = False
            return self._panic_containment(ctx, message)

        if state == UserState.EXIT:
            return self._handle_exit(ctx)

        if ctx.in_panic_protocol and ctx.panic_just_talk_mode:
            return self._handle_panic_just_talk(ctx, message)

        if ctx.in_panic_protocol:
            return self._handle_panic_protocol(ctx, msg)

        if ctx.in_assistant_mode:
            return self._assistant_mode_handle(ctx, state, intensity, message)

        if ctx.in_routine_flow or ctx.in_routine_time:
            return self._handle_routine_flow(ctx, msg)

        if ctx.active_technique and ctx.technique_state != TechniqueState.NONE:
            result = self._handle_technique(ctx, msg, message)
            if result: return result

        if ctx.hope_capture_mode:
            return self._hope_capture(ctx, message)

        if ctx.menu_shown or ctx.emotional_stabilized:
            selected = self._match_menu_option(msg)
            if selected:
                return self._start_option(ctx, selected, message)

        if state in (UserState.NEUTRAL, UserState.CALM):
            if (ctx.consecutive_neutral >= 3
                    and ctx.listen_depth >= 1
                    and not ctx.menu_shown):
                ctx.emotional_stabilized = True
                return self._menu(ctx)

        if state == UserState.PHYSICAL:
            return self._physical_response(ctx, message)

        if state == UserState.STUCK:
            if not ctx.stuck_orientation_asked:
                ctx.stuck_orientation_asked = True
                return self._stuck_orientation(ctx, message)
            elif not ctx.stuck_two_choice_shown:
                ctx.stuck_two_choice_shown = True
                return self._stuck_two_choices(ctx, message)

        if (ctx.detected_goal and not ctx.emotional_stabilized
                and ctx.listen_depth >= 2 and not ctx.goal_question_asked):
            return self._goal_anchor(ctx, message)

        if not ctx.emotional_stabilized:
            return self._listen_phase(ctx, state, intensity, message)

        if ctx.in_just_talk:
            return self._just_talk(ctx, message)

        if not ctx.menu_shown:
            return self._menu(ctx)

        return self._empathetic_fallback(ctx, message)

    # ══════════════════════════════════════════════════════════════════════════
    # CRISIS FLOW — SINGLE LINEAR PATH
    # ══════════════════════════════════════════════════════════════════════════

    def _crisis_route(self, ctx: ConversationContext, message: str) -> Dict:
        ctx.crisis_round += 1
        ctx.crisis_in_flow = True

        if ctx.crisis_round == 1:
            text = self._llm(
                ctx, "crisis_round_1", message,
                fallback=(
                    "I hear you, and I am right here with you. 💜 "
                    "That kind of pain is real, and I am not going anywhere. "
                    "Can you tell me what has been going on?"
                )
            )
            return self._resp(text, [], "suicidal", priority="critical")

        if ctx.crisis_round == 2:
            text = self._llm(
                ctx, "crisis_round_2", message,
                fallback=(
                    "Thank you for trusting me with this. 💜 "
                    "The fact that you are still here and still talking — "
                    "something in you is still reaching, and that matters. "
                    "What has this been like for you day to day?"
                )
            )
            return self._resp(text, [], "suicidal", priority="critical")

        if ctx.crisis_round == 3:
            text = self._llm(
                ctx, "crisis_round_3", message,
                fallback=(
                    "You have been carrying so much. 💜 "
                    "The world is genuinely different with you in it, even when it does not feel that way. "
                    "Is there even one small thing — a person, a place, a moment — that has kept you here?"
                )
            )
            return self._resp(text, [], "suicidal", priority="critical")

        ctx.crisis_in_flow = False
        text = self._llm(
            ctx, "crisis_human_help", message,
            fallback=(
                "I care about you, and I want to be honest with you. 💜\n"
                "What you are carrying right now is more than a chatbot can hold alone — "
                "and a real person is ready to listen right now, no judgment.\n\n"
                + _SL_CONTACTS
            )
        )
        return self._resp(text, [
            {"id": "crisis_stay", "label": "Stay and keep talking with me"},
        ], "suicidal", priority="critical")

    # ══════════════════════════════════════════════════════════════════════════
    # LISTEN PHASE
    # ══════════════════════════════════════════════════════════════════════════

    def _listen_phase(self, ctx: ConversationContext, state: UserState,
                      intensity: float, message: str) -> Dict:
        ctx.listen_depth += 1
        depth = ctx.listen_depth

        if ctx.passive_crisis_escalated and not ctx.had_crisis_this_session:
            return self._passive_crisis_response(ctx, message)

        _msg_lower   = message.lower()
        _is_positive = re.search(
            r"\b(good|great|fine|well|happy|excited|okay|ok|better|positive|looking forward|feel good)\b",
            _msg_lower, re.IGNORECASE) is not None

        if depth == 1:
            template_key = ("listen_first_contact"
                            if state in (UserState.NEUTRAL, UserState.CALM) and intensity < 0.3
                            else intensity_to_listen_template(intensity))
        elif depth == 2:
            template_key = ("listen_neutral_greeting"
                            if _is_positive and intensity < 0.3
                            else ("listen_reflect_light" if intensity < 0.5
                                  else "listen_reflect_medium"))
        elif depth == 3:
            template_key = "listen_reflect_medium" if intensity < 0.7 else "listen_reflect_deep"
        elif depth == 4:
            template_key = "listen_reflect_deep"
        elif depth == 5:
            template_key = "listen_transition_to_menu"
        else:
            if ctx.detected_goal and not ctx.goal_question_asked:
                return self._goal_anchor(ctx, message)
            ctx.emotional_stabilized = True
            text = self._llm(ctx, "listen_transition_to_menu", message,
                             fallback="Thank you for sharing. 💜 What would feel most helpful right now?")
            return self._menu_with_preamble(ctx, text)

        text = self._llm(ctx, template_key, message,
                         fallback="I am here with you. 💜 What is going on for you right now?")

        if depth >= 5 or (depth == 4 and intensity > 0.7):
            ctx.emotional_stabilized = True
            return {"text": text, "options": self._menu_options(ctx),
                    "metadata": {"state": state.value, "phase": f"listen_{depth}"}}

        return {"text": text, "options": [],
                "metadata": {"state": state.value, "phase": f"listen_{depth}"}}

    # ══════════════════════════════════════════════════════════════════════════
    # PHYSICAL
    # ══════════════════════════════════════════════════════════════════════════

    def _physical_response(self, ctx: ConversationContext, message: str) -> Dict:
        text = self._llm(ctx, "physical_illness_response", message,
                         fallback="Oh no, that sounds rough. 💜 Rest as much as you can. Is there anything else on your mind?")
        return self._resp(text, [
            {"id": "just_talk",           "label": "Just want some company"},
            {"id": "physical_tiny_steps", "label": "What can I do to feel better?"},
        ], "physical")

    def _physical_tiny_steps(self, ctx: ConversationContext, message: str) -> Dict:
        situa = situation_bucket(ctx.history, ctx.current_state)
        text  = self._llm(ctx, "physical_tiny_steps", message,
                          template_vars={"illness_context": situa},
                          fallback="1. Drink a glass of water now. 2. Lie down and rest. 3. Let someone know you are not well. 💜")
        return self._resp(text, [
            {"id": "just_talk", "label": "I just want to talk"},
            {"id": "hear_hope", "label": "Hear something kind"},
        ], "physical_steps")

    # ══════════════════════════════════════════════════════════════════════════
    # STUCK
    # ══════════════════════════════════════════════════════════════════════════

    def _stuck_orientation(self, ctx: ConversationContext, message: str) -> Dict:
        text = self._llm(ctx, "stuck_normalize", message,
                         fallback="Feeling stuck like this makes complete sense. 💜 Does this feel more like sadness, exhaustion, or something else?")
        return self._resp(text, [
            {"id": "sadness",    "label": "Sadness"},
            {"id": "exhaustion", "label": "Exhaustion"},
            {"id": "buildup",    "label": "It has been building up"},
            {"id": "specific",   "label": "Something specific happened"},
        ], "stuck_orient")

    def _stuck_two_choices(self, ctx: ConversationContext, message: str) -> Dict:
        text = self._llm(ctx, "stuck_two_choices", message,
                         fallback="That is completely okay — no rush at all. 💜 What would feel most helpful right now?")
        return self._resp(text, [
            {"id": "just_talk",    "label": "I just need someone to listen"},
            {"id": "calm_feeling", "label": "Help me calm this feeling"},
        ], "stuck_two_choices")

    # ══════════════════════════════════════════════════════════════════════════
    # PANIC
    # ══════════════════════════════════════════════════════════════════════════

    def _panic_containment(self, ctx: ConversationContext, message: str) -> Dict:
        text = self._llm(
            ctx, "panic_empathy_response", message,
            fallback=(
                "I am right here with you. 💜 "
                "What you are feeling right now is real, and it will pass. "
                "You are safe — take one slow breath with me."
            )
        )
        return self._resp(text, [
            {"id": "panic_healing_methods", "label": "Show me healing methods"},
            {"id": "panic_just_talk",       "label": "I just want to talk"},
        ], "panic", priority="high")

    def _panic_show_healing_methods(self, ctx: ConversationContext, message: str) -> Dict:
        ctx.panic_just_talk_mode = False
        text = (
            "Here are some things that can help right now. 💜 "
            "Pick whichever feels right — there is no wrong choice."
        )
        return self._resp(text, [
            {"id": "bilateral",  "label": "Bilateral tapping (shoulder tap)"},
            {"id": "breathing",  "label": "Slow breathing"},
            {"id": "grounding",  "label": "5-4-3-2-1 grounding"},
            {"id": "havening",   "label": "Havening (arm stroking)"},
            {"id": "just_talk",  "label": "Actually, I'd rather just talk"},
        ], "panic_healing_menu")

    def _handle_panic_just_talk(self, ctx: ConversationContext, message: str) -> Dict:
        ctx.panic_just_talk_exchanges += 1

        if ctx.panic_just_talk_exchanges >= 5:
            ctx.panic_just_talk_exchanges = 0
            text = self._llm(
                ctx, "just_talk_transition", message,
                fallback="You have been so brave talking through this. 💜 Would any of the calming methods feel helpful now?"
            )
            return self._resp(text, [
                {"id": "panic_healing_methods", "label": "Yes, show me a method"},
                {"id": "panic_just_talk",       "label": "Keep talking"},
            ], "panic_just_talk_offer")

        text = self._llm(
            ctx, "panic_just_talk", message,
            template_vars={"context_summary": self._context_summary(ctx)},
            fallback="I am here. 💜 Keep going — I am listening to every word."
        )
        return self._resp(text, [
            {"id": "panic_healing_methods", "label": "I want to try a calming method"},
            {"id": "panic_just_talk",       "label": "Keep talking"},
        ], "panic_just_talk")

    def _handle_panic_protocol(self, ctx: ConversationContext, msg: str) -> Dict:
        if any(w in msg for w in ["just talk", "want to talk", "just_talk", "panic_just_talk"]):
            ctx.panic_just_talk_mode      = True
            ctx.panic_just_talk_exchanges = 0
            return self._handle_panic_just_talk(ctx, msg)

        if any(w in msg for w in ["panic_healing_methods", "healing methods", "show me", "heal"]):
            return self._panic_show_healing_methods(ctx, msg)

        if any(w in msg for w in ["bilateral", "breathing", "grounding", "havening",
                                   "calm panic", "calm_panic", "yes"]):
            technique = "bilateral"
            for t in ["bilateral", "breathing", "grounding", "havening"]:
                if t in msg:
                    technique = t
                    break
            ctx.panic_step = 1
            return self._deliver_technique(ctx, technique, msg)

        if any(w in msg for w in ["little calmer", "calmer", "better", "calmed", "helped"]):
            ctx.in_panic_protocol        = False
            ctx.panic_just_talk_mode     = False
            ctx.emotional_stabilized     = True
            text = self._llm(
                ctx, "technique_worked",
                template_vars={"technique_name": TECHNIQUE_LABELS.get(ctx.active_technique or "bilateral", "that")},
                fallback="I am really glad that helped. 💜 Take a moment — you are safe."
            )
            return self._menu_with_preamble(ctx, text)

        if any(w in msg for w in ["still", "intense", "not working", "try another", "try_another"]):
            ctx.panic_step += 1
            panic_techniques = ["bilateral", "breathing", "havening", "grounding"]
            if ctx.panic_step <= len(panic_techniques):
                return self._deliver_technique(ctx, panic_techniques[ctx.panic_step - 1], msg)
            ctx.in_panic_protocol    = False
            ctx.panic_just_talk_mode = False
            text = self._llm(ctx, "panic_just_talk", msg,
                             template_vars={"context_summary": self._context_summary(ctx)},
                             fallback="We can pause — I am here. 💜 What does this feel like right now?")
            return self._resp(text, [], "panic_co_reg")

        return self._resp("Take your time. How are you feeling right now? 💜", [
            {"id": "calmer",                "label": "A little calmer"},
            {"id": "still",                 "label": "Still intense"},
            {"id": "panic_healing_methods", "label": "Try a different method"},
        ], "panic")

    # ══════════════════════════════════════════════════════════════════════════
    # PASSIVE CRISIS
    # ══════════════════════════════════════════════════════════════════════════

    def _passive_crisis_response(self, ctx: ConversationContext, message: str) -> Dict:
        if ctx.passive_crisis_count >= 3:
            text = self._llm(ctx, "passive_crisis_gentle_check", message,
                             fallback=(
                                 "I want to make sure I understand what you are carrying right now. 💜 "
                                 "Are you having any thoughts of not wanting to be here?"
                             ))
            return self._resp(text, [
                {"id": "passive_yes",  "label": "Yes, I am having those thoughts"},
                {"id": "passive_no",   "label": "No, I am just really struggling"},
                {"id": "just_talk",    "label": "I just want to talk"},
                {"id": "crisis_help",  "label": "I need to talk to someone"},
            ], "passive_crisis_check", priority="high")

        text = self._llm(ctx, "passive_crisis_acknowledge", message,
                         fallback=(
                             "It sounds like you have been carrying something really heavy. 💜 "
                             "What has been weighing on you most?"
                         ))
        return self._resp(text, [
            {"id": "just_talk",   "label": "I want to talk about it"},
            {"id": "calm_feeling","label": "Help me with this feeling"},
            {"id": "crisis_help", "label": "I need to talk to someone"},
        ], "passive_crisis", priority="high")

    # ══════════════════════════════════════════════════════════════════════════
    # TECHNIQUES
    # ══════════════════════════════════════════════════════════════════════════

    def _route_calm_technique(self, ctx: ConversationContext, message: str) -> Dict:
        state    = ctx.current_state
        combined = " ".join(h["content"] for h in ctx.history[-8:]
                            if h.get("role") == "user").lower()
        if any(w in combined for w in ["numb", "empty", "shutdown", "disconnected", "nothing"]):
            technique = "sensory"
        elif any(w in combined for w in ["spinning", "overthink", "loop", "can't stop thinking"]):
            technique = "binary"
        elif state == UserState.SAD:
            technique = "inner_hug"
        elif state == UserState.ANXIOUS and ctx.current_intensity > 0.6:
            technique = "breathing"
        elif state == UserState.ANXIOUS:
            technique = "safe_place"
        elif state == UserState.STUCK:
            technique = "binary"
        else:
            technique = "inner_hug"
        return self._ask_technique_permission(ctx, technique, message)

    def _ask_technique_permission(self, ctx: ConversationContext,
                                   technique: str, message: str) -> Dict:
        ctx.active_technique = technique
        ctx.technique_state  = TechniqueState.PERMISSION
        ctx.technique_step   = 0
        label = TECHNIQUE_LABELS.get(technique, technique)
        text  = self._llm(ctx, "technique_permission_ask", message,
                          template_vars={"technique_name": label},
                          fallback=f"I am here with you. 💜 If you are open to it, we could try {label} together — no pressure.")
        return self._resp(text, [
            {"id": technique,   "label": "Yes, let's try"},
            {"id": "just_talk", "label": "I'd rather just talk"},
        ], "pre_technique")

    def _deliver_technique(self, ctx: ConversationContext,
                            technique: str, message: str) -> Dict:
        ctx.active_technique  = technique
        ctx.technique_state   = TechniqueState.ACTIVE
        ctx.technique_step   += 1
        template_map = {
            "breathing":  "technique_delivery_breathing",
            "grounding":  "technique_delivery_grounding",
            "inner_hug":  "technique_delivery_inner_hug",
            "safe_place": "technique_delivery_safe_place",
            "havening":   "technique_delivery_havening",
            "bilateral":  "technique_delivery_bilateral",
            "sensory":    "technique_delivery_sensory",
            "binary":     "technique_delivery_binary_choice",
        }
        fallbacks = {
            "breathing":  "Let us breathe together. 🌬️ Breathe in slowly… breathe out slowly.",
            "grounding":  "Let us ground you. 🌿 Name 5 things you can see right now.",
            "inner_hug":  "Wrap your arms gently around yourself. 💜 Breathe in slowly…",
            "safe_place": "Close your eyes if comfortable. 💜 Imagine a safer place — what do you notice first?",
            "havening":   "Cross your arms gently. 🤗 Slowly rub from shoulders down to elbows.",
            "bilateral":  "Pause with me. 💜 Tap left shoulder, then right. Left… right…",
            "sensory":    "Right now — what is one thing you can feel against your skin? Just notice. 💜",
            "binary":     "Tiny choice to interrupt the loop. 💜 Stand up or stay sitting — pick one.",
        }
        text = self._llm(ctx, template_map.get(technique, "technique_delivery_breathing"), message,
                         template_vars={"step_number": str(ctx.technique_step)},
                         fallback=fallbacks.get(technique, "Let us try something gentle together. 💜"))
        return self._resp(text, [
            {"id": "calmer",      "label": "A little calmer"},
            {"id": "still",       "label": "Still intense"},
            {"id": "try_another", "label": "Try another method"},
        ], "technique_active")

    def _handle_technique(self, ctx: ConversationContext,
                           msg: str, original: str) -> Optional[Dict]:
        t = ctx.active_technique
        if not t: return None

        if ctx.technique_state == TechniqueState.PERMISSION:
            if any(w in msg for w in ["just talk", "rather talk", "no", "not now"]):
                ctx.active_technique = None
                ctx.technique_state  = TechniqueState.NONE
                return self._switch_to_just_talk(ctx, original)
            ctx.technique_state = TechniqueState.ACTIVE
            return self._deliver_technique(ctx, t, original)

        if any(w in msg for w in ["little calmer", "calmer", "better", "helped", "lighter"]):
            text = self._llm(ctx, "technique_worked",
                             template_vars={"technique_name": TECHNIQUE_LABELS.get(t, "that")},
                             fallback="I am really glad that helped. 💜")
            ctx.active_technique = None
            ctx.technique_state  = TechniqueState.NONE
            return self._menu_with_preamble(ctx, text)

        if any(w in msg for w in ["try another", "try_another", "not working", "another method"]):
            old_t                = t
            ctx.technique_step   = 0
            ctx.active_technique = None
            ctx.technique_state  = TechniqueState.NONE
            text = self._llm(ctx, "technique_not_worked",
                             template_vars={"technique_name": TECHNIQUE_LABELS.get(old_t, "that")},
                             fallback="That is okay — different things work at different times. 💜 Want to try something else?")
            alternatives = [k for k in ["breathing","grounding","inner_hug","safe_place","sensory"]
                            if k != old_t][:3]
            return self._resp(text, [
                {"id": alt, "label": TECHNIQUE_LABELS[alt].capitalize()} for alt in alternatives
            ] + [{"id": "just_talk", "label": "Just talk"}], "technique_choice")

        if any(w in msg for w in ["just talk", "rather talk", "stop", "done"]):
            ctx.active_technique = None
            ctx.technique_state  = TechniqueState.NONE
            return self._switch_to_just_talk(ctx, original)

        if t == "grounding" and ctx.technique_step < 4:
            return self._deliver_technique(ctx, t, original)
        if t == "breathing" and ctx.technique_step < 3:
            return self._deliver_technique(ctx, t, original)

        if t in ("binary", "sensory", "inner_hug", "safe_place", "havening"):
            ctx.active_technique = None
            ctx.technique_state  = TechniqueState.NONE
            text = self._llm(ctx, "technique_checkin", original,
                             template_vars={
                                 "technique_name": TECHNIQUE_LABELS.get(t, "that"),
                                 "user_summary":   self._context_summary(ctx)[:80],
                             },
                             fallback="You did something kind for yourself. 💜 How do you feel?")
            return self._menu_with_preamble(ctx, text)

        if ctx.technique_step < 4:
            return self._deliver_technique(ctx, t, original)

        ctx.active_technique = None
        ctx.technique_state  = TechniqueState.NONE
        text = self._llm(ctx, "technique_checkin", original,
                         template_vars={
                             "technique_name": TECHNIQUE_LABELS.get(t, "that"),
                             "user_summary":   self._context_summary(ctx)[:80],
                         },
                         fallback="You did that. 💜 How are you feeling now?")
        return self._menu_with_preamble(ctx, text)

    # ══════════════════════════════════════════════════════════════════════════
    # JUST TALK
    # ══════════════════════════════════════════════════════════════════════════

    def _just_talk(self, ctx: ConversationContext, message: str) -> Dict:
        ctx.in_just_talk        = True
        ctx.active_technique    = None
        ctx.technique_state     = TechniqueState.NONE
        ctx.just_talk_exchanges += 1

        if ctx.just_talk_exchanges >= 7:
            ctx.in_just_talk        = False
            ctx.just_talk_exchanges = 0
            text = self._llm(ctx, "just_talk_transition", message,
                             fallback="You have shared so much. 💜 What would feel most helpful right now?")
            return self._menu_with_preamble(ctx, text)

        if (ctx.detected_goal and ctx.just_talk_exchanges == 2
                and not ctx.goal_question_asked):
            ctx.goal_question_asked = True
            text = self._llm(ctx, "just_talk_goal_noticed", message,
                             template_vars={"goal": ctx.detected_goal[:60]},
                             fallback="I noticed you mentioned something that matters to you. 💜 What would it mean to achieve that?")
            return self._resp(text, [
                {"id": "just_talk", "label": "Let's talk about it"},
                {"id": "hear_hope", "label": "I need some hope about it"},
            ], "just_talk")

        text = self._llm(ctx, "just_talk_open", message,
                         template_vars={
                             "context_summary": self._context_summary(ctx),
                             "memory_hint":     self._memory_hint(ctx) or "",
                         },
                         fallback="I am here. 💜 Tell me more — what is going on for you?")
        return self._resp(text, [], "just_talk")

    def _switch_to_just_talk(self, ctx: ConversationContext, message: str) -> Dict:
        ctx.in_just_talk        = True
        ctx.active_technique    = None
        ctx.technique_state     = TechniqueState.NONE
        ctx.just_talk_exchanges = 0
        return self._just_talk(ctx, message)

    # ══════════════════════════════════════════════════════════════════════════
    # PERSONAL ASSISTANT MODE
    # ══════════════════════════════════════════════════════════════════════════

    def _enter_assistant_mode(self, ctx: ConversationContext,
                               source: str, message: str) -> Dict:
        ctx.in_assistant_mode      = True
        ctx.assistant_mode_source  = source
        ctx.assistant_discovery_step = 0
        ctx.assistant_plan         = ""

        active_goal = ctx.detected_goal or ""
        for tf in ["3_months", "1_year", "2_years"]:
            if ctx.hope_goals.get(tf):
                active_goal = ctx.hope_goals[tf][0]; break
        if not ctx.assistant_goal:
            ctx.assistant_goal = active_goal

        if ctx.current_intensity >= 0.7:
            text = self._llm(ctx, "assistant_confused_user", message,
                             template_vars={"situation_summary": _build_situation_summary(ctx)},
                             fallback="It sounds like a lot is going on. 💜 Before we plan anything — what is feeling heaviest right now?")
            return self._resp(text, [
                {"id": "asst_continue", "label": "I want to keep going"},
                {"id": "just_talk",     "label": "I just need to talk"},
            ], "assistant_low_capacity")

        if self._assistant_should_create_plan(ctx):
            return self._assistant_create_plan(ctx, message)

        return self._assistant_discover(ctx, message)

    def _assistant_should_create_plan(self, ctx: ConversationContext) -> bool:
        return (bool(ctx.assistant_goal or ctx.detected_goal)
                and bool(ctx.assistant_free_time)
                and bool(ctx.assistant_habits)
                and bool(ctx.assistant_blockers))

    def _assistant_discover(self, ctx: ConversationContext, message: str) -> Dict:
        step  = ctx.assistant_discovery_step
        situa = _build_situation_summary(ctx)
        goal  = ctx.assistant_goal or ctx.detected_goal or "your goal"
        cap   = intensity_to_capacity(ctx.current_intensity)

        if self._assistant_should_create_plan(ctx):
            ctx.assistant_discovery_step = 4
            return self._assistant_create_plan(ctx, message)

        if step == 0:
            ctx.assistant_discovery_step = 1
            if ctx.assistant_goal or ctx.detected_goal:
                if not ctx.assistant_goal:
                    ctx.assistant_goal = ctx.detected_goal
                text = self._llm(ctx, "assistant_discover_freetime", message,
                                 template_vars={"active_goal": (ctx.assistant_goal or goal)[:60]},
                                 fallback=f"To help you with {(ctx.assistant_goal or goal)[:40]}, when do you usually have free time — mornings, afternoons, or evenings?")
            else:
                text = self._llm(ctx, "assistant_discover_situation", message,
                                 template_vars={"situation_summary": situa, "capacity_level": cap},
                                 fallback="I would love to help you plan something. 💜 What is the main thing you are working toward right now?")
            return self._resp(text, [], "assistant_discover")

        if step == 1:
            if not ctx.assistant_goal and message.strip():
                possible_goal = auto_detect_goal_label(message)
                ctx.assistant_goal = possible_goal or message.strip()[:100]
            tod = extract_time_of_day(message)
            if tod:
                ctx.assistant_free_time = tod
            if not ctx.assistant_free_time:
                ctx.assistant_discovery_step = 2
                text = self._llm(ctx, "assistant_discover_freetime", message,
                                 template_vars={"active_goal": (ctx.assistant_goal or goal)[:60]},
                                 fallback="When do you usually have free time? Mornings, afternoons, or evenings work best for you?")
                return self._resp(text, [
                    {"id": "asst_time_morning",   "label": "Mornings"},
                    {"id": "asst_time_afternoon",  "label": "Afternoons"},
                    {"id": "asst_time_evening",    "label": "Evenings"},
                    {"id": "asst_time_weekend",    "label": "Weekends"},
                ], "assistant_discover_time")
            else:
                ctx.assistant_discovery_step = 2
                text = self._llm(ctx, "assistant_discover_habits", message,
                                 template_vars={"active_goal": (ctx.assistant_goal or goal)[:60]},
                                 fallback="Good to know. 💜 Do you tend to focus better in short bursts or longer sessions?")
                return self._resp(text, [
                    {"id": "asst_short",  "label": "Short bursts"},
                    {"id": "asst_long",   "label": "Longer sessions"},
                    {"id": "asst_varies", "label": "It varies"},
                ], "assistant_discover")

        if step == 2:
            if not ctx.assistant_habits:
                ctx.assistant_habits = message.strip()
            ctx.assistant_discovery_step = 3
            text = self._llm(ctx, "assistant_discover_blockers", message,
                             template_vars={"active_goal": (ctx.assistant_goal or goal)[:60]},
                             fallback="That is helpful. 💜 What feels like the biggest thing getting in the way right now?")
            return self._resp(text, [], "assistant_discover")

        if step == 3:
            if not ctx.assistant_blockers:
                ctx.assistant_blockers = message.strip()
            ctx.assistant_discovery_step = 4
            return self._assistant_create_plan(ctx, message)

        return self._assistant_post_plan(ctx, message)

    def _assistant_create_plan(self, ctx: ConversationContext, message: str) -> Dict:
        goal           = ctx.assistant_goal or ctx.detected_goal or "your goal"
        cap            = intensity_to_capacity(ctx.current_intensity)
        situa          = _build_situation_summary(ctx)
        free_time      = ctx.assistant_free_time or "whenever you have time"
        habits         = ctx.assistant_habits or "varies"
        blockers       = ctx.assistant_blockers or "not specified"
        days_available = "unknown"

        if "exam" in ctx.situation_profile:
            urgency = ctx.situation_profile["exam"].get("urgency", "medium")
            days_available = "about 2 weeks" if urgency == "high" else "1 month"
        elif "work" in ctx.situation_profile:
            days_available = "ongoing"

        plan_text = self._llm(ctx, "assistant_create_plan", message,
                              template_vars={
                                  "active_goal":       goal[:60],
                                  "free_time":         free_time[:80],
                                  "user_habits":       habits[:80],
                                  "blockers":          blockers[:80],
                                  "capacity_level":    cap,
                                  "situation_summary": situa,
                                  "days_available":    days_available,
                              },
                              fallback=(
                                  f"Here is a simple plan for {goal[:40]}:\n"
                                  f"1. Start with 15 minutes in the {free_time}.\n"
                                  f"2. Focus on one small topic at a time.\n"
                                  f"3. Take a 5-minute break after each session.\n"
                                  f"You are doing something real by planning this. 💜"
                              ))
        ctx.assistant_plan = plan_text

        confirm_text = self._llm(ctx, "assistant_plan_confirm", message,
                                  template_vars={"plan_text": plan_text[:400]},
                                  fallback=f"Here is what I put together for you. 💜\n\n{plan_text}\n\nDoes this feel doable, or would you like to adjust it?")
        return self._resp(confirm_text, [
            {"id": "asst_plan_ok",     "label": "This looks good"},
            {"id": "asst_plan_adjust", "label": "Can we adjust it?"},
            {"id": "asst_plan_save",   "label": "Save this and add tasks"},
        ], "assistant_plan")

    def _assistant_post_plan(self, ctx: ConversationContext, message: str) -> Dict:
        msg = message.strip().lower()
        if any(w in msg for w in ["asst_plan_adjust","adjust","change","too much","too little","different","maybe"]):
            text = self._llm(ctx, "assistant_plan_adjust", message,
                             template_vars={
                                 "original_plan":  ctx.assistant_plan[:300],
                                 "user_feedback":  message[:100],
                                 "capacity_level": intensity_to_capacity(ctx.current_intensity),
                             },
                             fallback="Of course — let us tweak it. What would you like to change?")
            return self._resp(text, [
                {"id": "asst_plan_ok",   "label": "This version works"},
                {"id": "asst_plan_save", "label": "Save this and add tasks"},
            ], "assistant_plan_adjust")

        if any(w in msg for w in ["asst_plan_ok","asst_plan_save","looks good","save","add tasks","yes","perfect","great","this version works"]):
            return self._assistant_save_and_surface(ctx, message)

        text = self._llm(ctx, "just_talk_open", message,
                         template_vars={
                             "context_summary": self._context_summary(ctx),
                             "memory_hint":     ctx.assistant_plan[:100] if ctx.assistant_plan else "",
                         },
                         fallback="Tell me more — what is on your mind about this? 💜")
        return self._resp(text, [
            {"id": "asst_plan_ok",     "label": "Let's go with the plan"},
            {"id": "asst_plan_adjust", "label": "I want to adjust it"},
        ], "assistant_chat")

    def _assistant_save_and_surface(self, ctx: ConversationContext, message: str) -> Dict:
        today_str = datetime.utcnow().strftime("%A %d %B")
        cap       = intensity_to_capacity(ctx.current_intensity)
        goal      = ctx.assistant_goal or ctx.detected_goal or "your goal"

        tasks_json_str = self._llm(ctx, "assistant_generate_tasks", message,
                                    template_vars={
                                        "plan_text":         ctx.assistant_plan[:300],
                                        "active_goal":       goal[:60],
                                        "capacity_level":    cap,
                                        "situation_summary": _build_situation_summary(ctx),
                                        "today_str":         today_str,
                                    },
                                    fallback=f'{{"tasks": ["Start with one small step toward {goal[:30]} today"]}}')

        generated_tasks: List[str] = []
        try:
            clean  = tasks_json_str.replace("```json","").replace("```","").strip()
            parsed = json.loads(clean)
            generated_tasks = parsed.get("tasks", [])
        except Exception:
            lines           = [l.strip("- •123456789. ").strip()
                               for l in tasks_json_str.split("\n") if l.strip()]
            generated_tasks = [l for l in lines if len(l) > 5][:3]

        if not generated_tasks:
            free_time = ctx.assistant_free_time or "when you have time"
            if cap == "LOW":
                generated_tasks = [f"Open your notes for 5 minutes in the {free_time}"]
            elif cap == "MEDIUM":
                generated_tasks = [
                    f"Study one topic for 15 minutes in the {free_time}",
                    f"Write down one thing you understood today",
                ]
            else:
                generated_tasks = [
                    f"Study for 30 minutes in the {free_time}",
                    f"Review yesterday's notes for 10 minutes",
                    f"Write a summary of what you learned",
                ]

        situa_summary = _build_situation_summary(ctx)
        if self._sbert and self._sbert.is_ready and len(generated_tasks) > 1:
            try:
                generated_tasks = self._sbert.rank_tasks(situa_summary, generated_tasks)
            except Exception:
                pass

        for task in generated_tasks:
            if task:
                ctx.tiny_steps.insert(0, task)
                ctx.healing_points += 5

        goal_update_text = ""
        if ctx.assistant_mode_source == "hope_goals" and ctx.assistant_goal:
            saved = any(ctx.assistant_goal in goals for goals in ctx.hope_goals.values())
            if not saved:
                ctx.hope_goals["3_months"].append(ctx.assistant_goal)
                ctx.healing_points += 15
            goal_update_text = f"\n\n🌸 I've also added your goal to your FutureBloom page."

        first_task = generated_tasks[0] if generated_tasks else f"One small step toward {goal[:30]}"

        surface_text = self._llm(ctx, "assistant_surface_task", message,
                                  template_vars={
                                      "task_text":      first_task[:80],
                                      "active_goal":    goal[:60],
                                      "capacity_level": cap,
                                  },
                                  fallback=(
                                      f"Your plan is saved. 🌱 Here's your first task:\n\n"
                                      f"➡️ {first_task}\n\n"
                                      f"Want to add this to your daily page?"
                                  ))

        task_count_note = f"\n\n({len(generated_tasks)} task(s) added to your daily page.)" if len(generated_tasks) > 1 else ""

        ctx.in_assistant_mode        = False
        ctx.assistant_discovery_step = 0
        ctx.menu_shown               = True
        ctx.emotional_stabilized     = True

        return self._resp(surface_text + goal_update_text + task_count_note, [
            {"id": "asst_see_tasks", "label": "Show me all tasks"},
            {"id": "just_talk",      "label": "Let's keep talking"},
            {"id": "tiny_plan",      "label": "Add another step"},
        ], "assistant_saved")

    def _assistant_mode_handle(self, ctx: ConversationContext,
                                state: UserState, intensity: float,
                                message: str) -> Dict:
        msg = message.strip().lower()

        if intensity >= 0.7 or state in (UserState.SAD, UserState.ANXIOUS):
            ctx.in_assistant_mode = False
            text = self._llm(ctx, "listen_reflect_medium", message,
                             fallback="I can hear this is weighing on you. 💜 The plan can wait — what is going on right now?")
            return self._resp(text, [
                {"id": "asst_resume",  "label": "Resume planning when ready"},
                {"id": "calm_feeling", "label": "Help me calm this first"},
                {"id": "just_talk",    "label": "I just need to talk"},
            ], "assistant_paused")

        if "asst_resume" in msg or any(w in msg for w in ["resume", "back to planning", "continue planning"]):
            ctx.in_assistant_mode = True
            if self._assistant_should_create_plan(ctx):
                return self._assistant_create_plan(ctx, message)
            return self._assistant_discover(ctx, message)

        if _CHANGE_RE.search(message) and ctx.assistant_plan:
            text = self._llm(ctx, "assistant_change_detected", message,
                             template_vars={
                                 "change_description": message[:80],
                                 "previous_situation": _build_situation_summary(ctx),
                             },
                             fallback="That sounds like something shifted. 💜 Want to update your plan?")
            return self._resp(text, [
                {"id": "asst_plan_adjust", "label": "Yes, update the plan"},
                {"id": "just_talk",        "label": "Just wanted to mention it"},
            ], "assistant_change")

        tod = extract_time_of_day(message)
        if tod and not ctx.assistant_free_time:
            ctx.assistant_free_time = tod

        if self._assistant_should_create_plan(ctx):
            ctx.assistant_discovery_step = 4
            return self._assistant_create_plan(ctx, message)

        if ctx.assistant_discovery_step <= 3:
            if not ctx.assistant_goal and ctx.assistant_discovery_step == 0:
                possible_goal = auto_detect_goal_label(message)
                ctx.assistant_goal = possible_goal or message.strip()[:100]
            return self._assistant_discover(ctx, message)

        if ctx.assistant_plan:
            return self._assistant_post_plan(ctx, message)

        return self._assistant_discover(ctx, message)

    def _assistant_proactive_check(self, ctx: ConversationContext) -> Optional[Dict]:
        if ctx.proactive_shown_this_session: return None
        if ctx.current_intensity >= 0.45:    return None
        if ctx.had_crisis_this_session:      return None
        if ctx.chat_count < 6:              return None
        if not ctx.situation_profile:       return None

        active_goal = ctx.assistant_goal or ctx.detected_goal or ""
        for tf in ["3_months","1_year","2_years"]:
            if ctx.hope_goals.get(tf):
                active_goal = ctx.hope_goals[tf][0]; break
        if not active_goal:
            return None

        goal_kws    = [w for w in active_goal.lower().split() if len(w) > 3][:4]
        recent_msgs = [h["content"].lower() for h in ctx.history[-30:]
                       if h.get("role") == "user"]
        days_since  = next(
            (i // 2 for i, m in enumerate(reversed(recent_msgs))
             if any(kw in m for kw in goal_kws)), 999)

        key       = active_goal[:40]
        prox_hist = ctx.goal_proximity_history.get(key, [])
        if len(prox_hist) >= 2:
            trend     = prox_hist[-1] - prox_hist[-2]
            prox_desc = "improving" if trend > 0.05 else "declining" if trend < -0.05 else "steady"
        else:
            prox_desc = "early stages"

        should_fire = days_since > 7 or prox_desc == "declining" or (
            prox_desc == "improving" and ctx.current_intensity < 0.3)
        if not should_fire:
            return None

        ctx.proactive_shown_this_session = True
        text = self._llm(ctx, "assistant_proactive_checkin", "",
                         template_vars={
                             "active_goal":           active_goal[:60],
                             "days_since":            str(days_since) if days_since < 999 else "a while",
                             "proximity_description": prox_desc,
                             "situation_summary":     _build_situation_summary(ctx),
                             "capacity_level":        intensity_to_capacity(ctx.current_intensity),
                         },
                         fallback=f"I have been thinking about what you shared. 💜 How is {active_goal[:40]} feeling right now?")
        return self._resp(text, [
            {"id": "asst_continue", "label": "Let's work on it"},
            {"id": "just_talk",     "label": "Tell me more"},
            {"id": "hear_hope",     "label": "I need some hope"},
        ], "proactive_coach")

    def notify_manual_change(self, uid: str, change_type: str,
                              change_detail: str) -> Optional[Dict]:
        ctx  = self._ctx(uid)
        text = self._llm(ctx, "assistant_manual_change_detected", "",
                         template_vars={"change_description": f"{change_type}: {change_detail}"[:100]},
                         fallback=f"I noticed you updated {change_type}. 💜 How are you feeling about that change?")
        return self._resp(text, [
            {"id": "just_talk",     "label": "Let's talk about it"},
            {"id": "asst_continue", "label": "Help me plan around it"},
        ], "manual_change")

    # ══════════════════════════════════════════════════════════════════════════
    # TINY PLAN
    # ══════════════════════════════════════════════════════════════════════════

    def _tiny_plan_start(self, ctx: ConversationContext, message: str) -> Dict:
        return self._enter_assistant_mode(ctx, "tiny_plan", message)

    def _tiny_plan_suggest(self, ctx: ConversationContext, message: str) -> Dict:
        situa    = situation_bucket(ctx.history, ctx.current_state)
        capacity = intensity_to_capacity(ctx.current_intensity)
        text     = self._llm(ctx, "tiny_plan_suggest_ideas", message,
                             template_vars={"situation": situa, "capacity_level": capacity},
                             fallback="Here are a few ideas — pick whichever feels right:")
        return self._resp(text, [
            {"id": "tp_s0",  "label": "Option 1"},
            {"id": "tp_s1",  "label": "Option 2"},
            {"id": "tp_s2",  "label": "Option 3"},
            {"id": "tp_own", "label": "I have my own idea"},
        ], "tiny_plan_suggest")

    def _tiny_plan_handle(self, ctx: ConversationContext,
                           msg: str, original: str) -> Optional[Dict]:
        step = ctx.technique_step
        if any(w in msg for w in ["tp_offer","not sure","give me ideas"]):
            return self._tiny_plan_suggest(ctx, original)
        if any(w in msg for w in ["tp_own","own idea"]):
            ctx.technique_step = 5
            text = self._llm(ctx, "tiny_plan_open_ask", original,
                             template_vars={
                                 "situation":     situation_bucket(ctx.history, ctx.current_state),
                                 "capacity_level": intensity_to_capacity(ctx.current_intensity),
                             },
                             fallback="I love that. 🌱 What is your tiny step?")
            return self._resp(text, [], "tiny_plan_own")
        if step == 5:
            ctx.routine_step_text = original.strip()
            ctx.technique_step    = 6
            return self._tiny_plan_personalize_and_ask_routine(ctx, original)
        if re.match(r"^tp_s\d+$", msg):
            ctx.routine_step_text = original.strip()
            ctx.technique_step    = 6
            return self._tiny_plan_personalize_and_ask_routine(ctx, original)
        if step == 1 and msg not in ["tp_offer","just_talk","tp_own"]:
            ctx.routine_step_text = original.strip()
            ctx.technique_step    = 6
            return self._tiny_plan_personalize_and_ask_routine(ctx, original)
        if step >= 6:
            return self._handle_routine_flow(ctx, msg)
        return None

    def _tiny_plan_personalize_and_ask_routine(self, ctx: ConversationContext,
                                                message: str) -> Dict:
        situa    = situation_bucket(ctx.history, ctx.current_state)
        capacity = intensity_to_capacity(ctx.current_intensity)
        personalized = self._llm(ctx, "tiny_plan_personalize_step", message,
                                  template_vars={
                                      "step_text":      ctx.routine_step_text[:80],
                                      "situation":      situa,
                                      "capacity_level": capacity,
                                  },
                                  fallback="That is a good one. 🌱")
        routine_ask = self._llm(ctx, "tiny_plan_add_to_routine_ask", message,
                                 template_vars={"step_text": ctx.routine_step_text[:80]},
                                 fallback="Would you like to build this into your daily routine?")
        ctx.in_routine_flow = True
        return self._resp(f"{personalized}\n\n{routine_ask}", [
            {"id": "routine_yes", "label": "Yes, add to my routine"},
            {"id": "routine_no",  "label": "Not now"},
        ], "tiny_plan_routine_ask")

    def _handle_routine_flow(self, ctx: ConversationContext, msg: str) -> Dict:
        if ctx.in_routine_flow and not ctx.in_routine_time:
            if any(w in msg for w in ["routine_yes","yes","sure","add"]):
                ctx.in_routine_flow = False
                ctx.in_routine_time = True
                text = self._llm(ctx, "tiny_plan_routine_time_ask", msg,
                                  template_vars={"step_text": ctx.routine_step_text[:80]},
                                  fallback="What time of day works best for this? 🕐")
                return self._resp(text, [
                    {"id": "rt_morning",   "label": "Morning"},
                    {"id": "rt_afternoon", "label": "Afternoon"},
                    {"id": "rt_evening",   "label": "Evening"},
                ], "routine_time")
            ctx.in_routine_flow  = False
            ctx.active_technique = None
            ctx.technique_state  = TechniqueState.NONE
            text = self._llm(ctx, "tiny_plan_completion_celebrate", msg,
                             template_vars={
                                 "step_text":    ctx.routine_step_text[:80],
                                 "streak_days":  str(ctx.streak_days),
                             },
                             fallback="That is a solid step. 🌱 Well done for deciding it.")
            ctx.routine_step_text = ""
            ctx.healing_points   += 10
            return self._menu_with_preamble(ctx, text)

        if ctx.in_routine_time:
            ctx.in_routine_time = False
            time_label = {
                "rt_morning": "morning", "rt_afternoon": "afternoon", "rt_evening": "evening"
            }.get(msg, msg.strip() or "your chosen time")
            step = ctx.routine_step_text or "your tiny step"
            ctx.daily_routine.append({"step": step, "time": time_label})
            text = self._llm(ctx, "tiny_plan_routine_confirmed", msg,
                             template_vars={"step_text": step[:80], "time_of_day": time_label},
                             fallback=f"Added to your routine at {time_label}. 🌱 You are building something real.")
            ctx.routine_step_text = ""
            ctx.active_technique  = None
            ctx.technique_state   = TechniqueState.NONE
            ctx.healing_points   += 10
            return self._menu_with_preamble(ctx, text)

        ctx.in_routine_flow = False
        ctx.in_routine_time = False
        return self._menu(ctx)

    # ══════════════════════════════════════════════════════════════════════════
    # HOPE GOALS
    # ══════════════════════════════════════════════════════════════════════════

    def _hear_hope_entry(self, ctx: ConversationContext, message: str) -> Dict:
        return self._resp("What would feel better right now? 💜", [
            {"id": "hope_add_goal", "label": "Work on a hope or goal"},
            {"id": "hope_inspire",  "label": "Share something hopeful"},
        ], "hope_entry")

    def _hope_message(self, ctx: ConversationContext, message: str) -> Dict:
        situa = situation_bucket(ctx.history, ctx.current_state)
        text  = self._llm(ctx, "hope_message_situational", message,
                          template_vars={
                              "situation":       situa,
                              "context_summary": self._context_summary(ctx),
                          },
                          fallback="You have survived every hard day so far. That is real strength. 💜")
        return self._resp(text, [
            {"id": "another",       "label": "Tell me another"},
            {"id": "hope_add_goal", "label": "Add a hope or goal"},
            {"id": "tiny_plan",     "label": "Help me take a small step"},
            {"id": "just_talk",     "label": "I want to talk about it"},
        ], "hope")

    def _hope_prompt_input(self, ctx: ConversationContext, message: str) -> Dict:
        label = {"3_months": "3 months", "1_year": "1 year",
                 "2_years": "2 years"}.get(ctx.hope_timeframe, "your future")
        ctx.hope_capture_mode = True
        return self._resp(
            f"I love that. 💜\n\nWhat is something you would love to be, achieve, or feel in the next {label}?\n\nJust write it naturally — there is no wrong answer.",
            [], "hope_input"
        )

    def _hope_capture(self, ctx: ConversationContext, message: str) -> Dict:
        if message == "hope_own_text":
            return self._resp("Of course — what would you love to achieve or feel? 💜", [], "hope_input")
        goal_text             = message.strip()
        ctx.pending_hope_goal = goal_text
        ctx.hope_capture_mode = False
        label = {"3_months": "3 months", "1_year": "1 year",
                 "2_years": "2 years"}.get(ctx.hope_timeframe, "your future")
        text  = self._llm(ctx, "hope_goal_confirm_add", message,
                          template_vars={"goal_text": goal_text[:80], "timeframe": label},
                          fallback=f"That is something worth working toward. 💜 Shall I add this to your Hope page under {label}?")
        return self._resp(text, [
            {"id": "yes_add_hope", "label": "Yes, add it"},
            {"id": "no_add_hope",  "label": "No thanks"},
        ], "hope_confirm")

    def _hope_goal_confirmed(self, ctx: ConversationContext, message: str) -> Dict:
        if ctx.pending_hope_goal and ctx.hope_timeframe:
            ctx.hope_goals[ctx.hope_timeframe].append(ctx.pending_hope_goal)
            self._llm(ctx, "hope_goal_milestone_generate", message,
                      template_vars={
                          "goal_text":  ctx.pending_hope_goal[:80],
                          "timeframe":  ctx.hope_timeframe,
                      })
        ctx.healing_points += 15
        pending             = ctx.pending_hope_goal
        ctx.pending_hope_goal = None
        text = self._llm(ctx, "technique_worked", message,
                         template_vars={"technique_name": f"setting your goal: {(pending or '')[:40]}"},
                         fallback="Added to your Hope page. 💜 That goal is real — naming it is already a step.")
        return self._menu_with_preamble(ctx, text)

    # ══════════════════════════════════════════════════════════════════════════
    # GOAL ANCHOR
    # ══════════════════════════════════════════════════════════════════════════

    def _goal_anchor(self, ctx: ConversationContext, message: str) -> Dict:
        ctx.emotional_stabilized = True
        ctx.goal_question_asked  = True
        text = self._llm(ctx, "goal_anchor_reflect", message,
                         template_vars={"goal": (ctx.detected_goal or "something that matters")[:60]},
                         fallback="That matters to you — I can hear it. 💜 What would it mean to achieve that?")
        return self._resp(text, [
            {"id": "just_talk", "label": "I want to talk about it"},
            {"id": "tiny_plan", "label": "Help me take a small step"},
            {"id": "hear_hope", "label": "I need some hope right now"},
        ], "goal_anchor")

    # ══════════════════════════════════════════════════════════════════════════
    # INVALID INPUT & LOOPS
    # ══════════════════════════════════════════════════════════════════════════

    def _handle_invalid_input(self, ctx: ConversationContext,
                               uid: str, message: str, reason: str) -> Dict:
        self._record_history(ctx, "user", message, "invalid")
        self._fallback.record_failure(uid)
        if reason in ("empty", "too_short"):
            text = self._llm(ctx, "meaningless_input_response",
                             fallback="I am here whenever you are ready. 💜")
            return self._resp(text, [], "invalid_input")
        if reason in ("gibberish", "keyboard_mash", "numbers_only"):
            text    = self._llm(ctx, "unclear_input_response",
                                fallback="I am here — take your time. 💜")
            options = self._menu_options(ctx) if ctx.menu_shown else []
            self._record_history(ctx, "assistant", text)
            return self._resp(text, options, "unclear_input")
        if reason == "emoji_only":
            text = self._llm(ctx, "listen_first_contact", message,
                             fallback="I see you. 💜 I am here — what is going on?")
            self._record_history(ctx, "assistant", text)
            return self._resp(text, [], "emoji_input")
        if reason == "too_long":
            text = self._llm(ctx, "empathetic_fallback", message[:150],
                             fallback="That is a lot on your mind. 💜 What is the most important part right now?")
            self._record_history(ctx, "assistant", text)
            return self._resp(text, [], "too_long")
        text = self._llm(ctx, "unclear_input_response", fallback="I am here with you. 💜")
        self._record_history(ctx, "assistant", text)
        return self._resp(text, [], "invalid_input")

    def _handle_thought_loop(self, ctx: ConversationContext,
                              uid: str, message: str) -> Dict:
        state, intensity         = detect_state_and_intensity(message)
        ctx.current_state        = state
        ctx.current_intensity    = intensity
        self._risk.update(uid, message, state, intensity)
        text = self._llm(ctx, "thought_loop_response", message,
                         template_vars={"repeated_message": message[:60]},
                         fallback="It feels like this thought keeps pulling you back. 💜 What is underneath it?")
        self._record_history(ctx, "user", message, state.value)
        self._record_history(ctx, "assistant", text)
        return self._resp(text, [
            {"id": "just_talk",    "label": "I want to talk about it"},
            {"id": "calm_feeling", "label": "Help me calm this"},
        ], "thought_loop")

    def _multi_signal_escalation(self, ctx: ConversationContext,
                                  uid: str, message: str) -> Dict:
        ctx.had_crisis_this_session = True
        risk_signals = self._risk.get_signals(uid)
        signals_str  = ", ".join(risk_signals) if risk_signals else "distress across this session"
        trajectory   = self._mood.trajectory(uid)

        if trajectory == "improving":
            text = self._llm(ctx, "session_acknowledgment", message,
                             template_vars={"session_themes": signals_str[:80]},
                             fallback="You have shared a lot today. 💜 How are you feeling right now?")
            self._record_history(ctx, "user", message, "elevated_risk")
            self._record_history(ctx, "assistant", text)
            return self._resp(text, [
                {"id": "just_talk",   "label": "I am okay, let's keep talking"},
                {"id": "crisis_help", "label": "I want to talk to someone"},
            ], "multi_signal_check")

        text = self._llm(ctx, "multi_signal_escalation", message,
                         template_vars={"risk_level": ctx.session_risk_level},
                         fallback=(
                             "You have shared a lot and I am a little worried about you. 💜 "
                             "You deserve real human support.\n\n"
                             + _SL_CONTACTS
                         ))
        self._record_history(ctx, "user", message, "multi_signal_risk")
        self._record_history(ctx, "assistant", text)
        return self._resp(text, [
            {"id": "crisis_stay", "label": "Stay and talk with me"},
            {"id": "crisis_help", "label": "I need support now"},
        ], "multi_signal_escalation", priority="high")

    # ══════════════════════════════════════════════════════════════════════════
    # EXIT
    # ══════════════════════════════════════════════════════════════════════════

    def _handle_exit(self, ctx: ConversationContext) -> Dict:
        uid = ctx.user_id
        if ctx.exit_pending:
            ctx.exit_pending                 = False
            ctx.active_technique             = None
            ctx.technique_state              = TechniqueState.NONE
            ctx.in_just_talk                 = False
            ctx.in_panic_protocol            = False
            ctx.panic_just_talk_mode         = False
            ctx.panic_just_talk_exchanges    = 0
            ctx.menu_shown                   = False
            ctx.emotional_stabilized         = False
            ctx.listen_depth                 = 0
            ctx.crisis_in_flow               = False
            ctx.had_crisis_this_session      = False
            ctx.crisis_round                 = 0
            ctx.returning_user               = True
            ctx.just_talk_exchanges          = 0
            ctx.stuck_orientation_asked      = False
            ctx.stuck_two_choice_shown       = False
            ctx.proactive_shown_this_session = False
            ctx.session_risk_level           = "normal"
            ctx.mood_trajectory              = "unknown"
            ctx.ambiguity_count              = 0
            ctx.low_confidence_count         = 0
            ctx.gaming_suspected             = False
            ctx.disclaimer_shown             = False
            ctx.help_rejections              = 0
            ctx.passive_crisis_count         = 0
            ctx.passive_crisis_escalated     = False
            self._risk.reset(uid)
            self._mood.reset(uid)
            self._game.reset(uid)
            self._fallback.reset(uid)
            return self._menu(ctx)

        ctx.exit_pending = True
        text = self._llm(ctx, "exit_feeling_better", "",
                         fallback="I am really glad you are feeling better. 💜")
        return self._resp(text, [], "exit_glad")

    # ══════════════════════════════════════════════════════════════════════════
    # MENU
    # ══════════════════════════════════════════════════════════════════════════

    def _menu_options(self, ctx: ConversationContext) -> List[Dict]:
        state = ctx.current_state

        if "exam" in ctx.situation_profile:
            return [
                {"id": "tiny_plan",     "label": "Create my study plan"},
                {"id": "calm_feeling",  "label": "Calm my exam stress"},
                {"id": "just_talk",     "label": "Just talk"},
                {"id": "hear_hope",     "label": "I need some hope"},
            ]

        if "work" in ctx.situation_profile:
            return [
                {"id": "tiny_plan",     "label": "Help me plan my work"},
                {"id": "calm_feeling",  "label": "Calm work stress"},
                {"id": "just_talk",     "label": "Just talk"},
                {"id": "hope_add_goal", "label": "Share a career goal"},
            ]

        if "relationship" in ctx.situation_profile:
            return [
                {"id": "just_talk",     "label": "I need to talk about it"},
                {"id": "calm_feeling",  "label": "Help me calm this"},
                {"id": "hear_hope",     "label": "Hear something hopeful"},
                {"id": "hope_add_goal", "label": "Share a hope"},
            ]

        if state in (UserState.NEUTRAL, UserState.CALM, UserState.PHYSICAL):
            return [
                {"id": "just_talk",     "label": "Just talk"},
                {"id": "tiny_plan",     "label": "Make a tiny plan"},
                {"id": "hear_hope",     "label": "Hear something hopeful"},
                {"id": "hope_add_goal", "label": "Share a hope or goal"},
            ]

        return [
            {"id": "just_talk",    "label": "Just talk"},
            {"id": "calm_feeling", "label": "Calm this feeling"},
            {"id": "tiny_plan",    "label": "Make a tiny plan"},
            {"id": "hear_hope",    "label": "Hear something hopeful"},
        ]

    def _menu(self, ctx: ConversationContext) -> Dict:
        ctx.menu_shown  = True
        ctx.menu_cycle += 1
        proactive = self._assistant_proactive_check(ctx)
        if proactive:
            return proactive
        return self._resp("How can I support you right now?",
                          self._menu_options(ctx), "menu")

    def _menu_with_preamble(self, ctx: ConversationContext, preamble: str) -> Dict:
        menu          = self._menu(ctx)
        menu["text"]  = preamble + "\n\n" + menu["text"]
        return menu

    def _empathetic_fallback(self, ctx: ConversationContext, message: str) -> Dict:
        text = self._llm(ctx, "empathetic_fallback", message,
                         fallback="I am here with you. 💜 What is going on right now?")
        return self._resp(text, self._menu_options(ctx),
                          ctx.current_state.value)

    # ══════════════════════════════════════════════════════════════════════════
    # SILENCE
    # ══════════════════════════════════════════════════════════════════════════

    def handle_silence(self, uid: str, duration_seconds: int) -> Dict:
        ctx        = self._ctx(uid)
        risk_level = self._risk.level(uid)

        if ctx.had_crisis_this_session or risk_level in ("high", "critical"):
            text = self._llm(ctx, "silence_after_crisis", "",
                             fallback="I am still here with you. 💜")
            return self._resp(text, [], "silence_crisis")

        if ctx.hope_capture_mode and duration_seconds >= 15:
            return self._resp("That is okay — sometimes it is hard to put into words. 💜", [
                {"id": "hope_inspire", "label": "Share something hopeful"},
                {"id": "just_talk",    "label": "Just talk for now"},
            ], "silence_hope")

        if risk_level == "elevated" and duration_seconds > 20:
            text = self._llm(ctx, "silence_gentle_nudge", "",
                             fallback="I am here — whenever you are ready, even one word is fine. 💜")
            return self._resp(text, [
                {"id": "just_talk",   "label": "I am here"},
                {"id": "crisis_help", "label": "I need support"},
            ], "silence_elevated")

        text = self._llm(ctx, "silence_gentle_nudge", "",
                         fallback="No rush — I am still here whenever you are ready. 💜")
        if duration_seconds > 40:
            return self._resp(text, [], "silence_long")
        return self._resp(text, [{"id": "just_talk", "label": "Just talk"}], "silence_nudge")

    # ══════════════════════════════════════════════════════════════════════════
    # MENU OPTION MATCHER
    # ══════════════════════════════════════════════════════════════════════════

    def _match_menu_option(self, msg: str) -> Optional[str]:
        mappings = {
            "just_talk":               ["just talk","talk to me","just_talk","let me talk","just want some company"],
            "calm_feeling":            ["calm this feeling","calm feeling","help me calm","calm_feeling","yes let's try","calm my exam stress","calm work stress","calm this"],
            "tiny_plan":               ["make a tiny plan","tiny plan","tiny_plan","help me take","small step","what can i do to feel better","create my study plan","help me plan my work"],
            "hear_hope":               ["hear something hopeful","hear_hope","tell me another","another","i need some hope","something kind"],
            "hope_add_goal":           ["add a hope","add a goal","hope_add_goal","work on a hope","share a hope or goal","share a career goal","share a hope"],
            "hope_inspire":            ["share something hopeful","hope_inspire"],
            "hope_3mo":                ["hope_3mo","3 months","three months"],
            "hope_1yr":                ["hope_1yr","1 year","one year"],
            "hope_2yr":                ["hope_2yr","2 years","two years"],
            "yes_add_hope":            ["yes_add_hope","yes add it"],
            "no_add_hope":             ["no_add_hope","no thanks"],
            "routine_yes":             ["routine_yes","yes add to my routine","add to routine"],
            "routine_no":              ["routine_no","not now"],
            "rt_morning":              ["rt_morning","morning"],
            "rt_afternoon":            ["rt_afternoon","afternoon"],
            "rt_evening":              ["rt_evening","evening"],
            "tp_offer":                ["give me ideas","not sure","i'm not sure","tp_offer"],
            "tp_own":                  ["i have my own idea","own idea","tp_own"],
            "panic_healing_methods":   ["panic_healing_methods","healing methods","show me healing","show me methods","heal","show me calming"],
            "panic_just_talk":         ["panic_just_talk","just want to talk during panic","keep talking"],
            "calm_panic":              ["help me calm this panic","calm panic","calm_panic"],
            "crisis_help":             ["i need crisis support","crisis support","crisis_help","talk to someone now","call someone now","i need to talk to someone"],
            "crisis_stay":             ["crisis_stay","stay and talk","stay with me","keep talking with me"],
            "calmer":                  ["little calmer","calmer","a little calmer","helped"],
            "still":                   ["still intense","still panicky","still"],
            "try_another":             ["try another","another method","try_another"],
            "tp_s0":                   ["tp_s0","option 1"],
            "tp_s1":                   ["tp_s1","option 2"],
            "tp_s2":                   ["tp_s2","option 3"],
            "another":                 ["tell me another","another"],
            "physical_tiny_steps":     ["what can i do","physical_tiny_steps"],
            "sadness":                 ["sadness"],
            "exhaustion":              ["exhaustion"],
            "buildup":                 ["been building","buildup"],
            "specific":                ["something happened","specific"],
            "asst_continue":           ["asst_continue","let's work on it","resume planning","keep going","continue","i want to keep going"],
            "asst_plan_ok":            ["asst_plan_ok","this looks good","looks good","perfect","that works","sounds good","let's go with the plan"],
            "asst_plan_adjust":        ["asst_plan_adjust","can we adjust","adjust it","change it","too much","too little","i want to adjust it"],
            "asst_plan_save":          ["asst_plan_save","save this","add tasks","save and add","yes save"],
            "asst_see_tasks":          ["asst_see_tasks","show me the tasks","see tasks","show me all tasks"],
            "asst_resume":             ["asst_resume","resume","back to planning","resume planning when ready"],
            "asst_short":              ["asst_short","short bursts","short sessions"],
            "asst_long":               ["asst_long","longer sessions","long sessions"],
            "asst_varies":             ["asst_varies","it varies","depends"],
            "asst_time_morning":       ["asst_time_morning","mornings"],
            "asst_time_afternoon":     ["asst_time_afternoon","afternoons"],
            "asst_time_evening":       ["asst_time_evening","evenings"],
            "asst_time_weekend":       ["asst_time_weekend","weekends"],
            "privacy_info":            ["my data","privacy","delete my data","what do you store","data policy"],
            "passive_yes":             ["passive_yes","yes i am having those thoughts","yes those thoughts","having those thoughts"],
            "passive_no":              ["passive_no","no just struggling","no i am just","just struggling","not those thoughts"],
        }
        for tid, phrases in mappings.items():
            if any(p in msg for p in phrases):
                return tid
        return None

    # ══════════════════════════════════════════════════════════════════════════
    # START OPTION
    # ══════════════════════════════════════════════════════════════════════════

    def _start_option(self, ctx: ConversationContext,
                       option_id: str, message: str) -> Dict:

        if option_id == "just_talk":
            return self._switch_to_just_talk(ctx, message)
        if option_id == "calm_feeling":
            return self._route_calm_technique(ctx, message)
        if option_id in ("breathing","grounding","inner_hug","safe_place","havening","bilateral","sensory","binary"):
            return self._ask_technique_permission(ctx, option_id, message)
        if option_id == "tiny_plan":
            return self._tiny_plan_start(ctx, message)
        if option_id == "tp_offer":
            return self._tiny_plan_suggest(ctx, message)
        if option_id in ("tp_own","tp_s0","tp_s1","tp_s2"):
            result = self._tiny_plan_handle(ctx, option_id, message)
            return result if result else self._tiny_plan_start(ctx, message)
        if option_id in ("routine_yes","routine_no","rt_morning","rt_afternoon","rt_evening"):
            return self._handle_routine_flow(ctx, option_id)
        if option_id == "hear_hope":
            return self._hear_hope_entry(ctx, message)
        if option_id in ("hope_inspire","another"):
            return self._hope_message(ctx, message)
        if option_id == "hope_add_goal":
            return self._enter_assistant_mode(ctx, "hope_goals", message)
        if option_id in ("hope_3mo","hope_1yr","hope_2yr"):
            ctx.hope_timeframe = {"hope_3mo":"3_months","hope_1yr":"1_year","hope_2yr":"2_years"}[option_id]
            return self._hope_prompt_input(ctx, message)
        if option_id == "yes_add_hope":
            return self._hope_goal_confirmed(ctx, message)
        if option_id == "no_add_hope":
            ctx.pending_hope_goal  = None
            ctx.help_rejections   += 1
            self._risk.record_rejection(ctx.user_id)
            text = self._llm(ctx,
                             "repeated_rejection_of_help" if ctx.help_rejections >= 3 else "technique_not_worked",
                             message,
                             template_vars={"technique_name": "adding the goal"},
                             fallback="No problem — it is still yours whenever you are ready. 💜")
            return self._menu_with_preamble(ctx, text)

        if option_id == "crisis_help":
            text = (
                "Please reach out right now — they are ready and they care. 💜\n\n"
                + _SL_CONTACTS
            )
            return self._resp(text, [], "crisis", priority="critical")

        if option_id == "crisis_stay":
            ctx.crisis_in_flow   = True
            ctx.in_just_talk     = True
            ctx.just_talk_exchanges = 0
            text = self._llm(
                ctx, "crisis_post_stay", message,
                fallback=(
                    "I am really glad you stayed. 💜 "
                    "There is no agenda here — just us talking. "
                    "What is on your mind right now?"
                )
            )
            return self._resp(text, [], "crisis_stay")

        if option_id == "panic_healing_methods":
            ctx.in_panic_protocol    = True
            ctx.panic_just_talk_mode = False
            return self._panic_show_healing_methods(ctx, message)

        if option_id == "panic_just_talk":
            ctx.in_panic_protocol         = True
            ctx.panic_just_talk_mode      = True
            ctx.panic_just_talk_exchanges = 0
            return self._handle_panic_just_talk(ctx, message)

        if option_id == "calm_panic":
            ctx.in_panic_protocol    = True
            ctx.panic_just_talk_mode = False
            ctx.panic_step           = 1
            return self._deliver_technique(ctx, "bilateral", message)
        if option_id in ("calmer","still","try_another") and ctx.in_panic_protocol:
            return self._handle_panic_protocol(ctx, option_id)
        if option_id == "physical_tiny_steps":
            return self._physical_tiny_steps(ctx, message)
        if option_id in ("calmer","helped") and ctx.active_technique:
            result = self._handle_technique(ctx, "calmer", message)
            return result if result else self._menu(ctx)
        if option_id in ("still","try_another") and ctx.active_technique:
            result = self._handle_technique(ctx, option_id, message)
            return result if result else self._menu(ctx)
        if option_id in ("sadness","exhaustion","buildup","specific"):
            ctx.stuck_orientation_asked = True
            return self._stuck_two_choices(ctx, message)
        if option_id in ("asst_continue","asst_resume"):
            ctx.in_assistant_mode = True
            if self._assistant_should_create_plan(ctx):
                return self._assistant_create_plan(ctx, message)
            return self._assistant_discover(ctx, message)
        if option_id == "asst_plan_ok":
            return self._assistant_save_and_surface(ctx, message)
        if option_id == "asst_plan_adjust":
            return self._assistant_post_plan(ctx, message)
        if option_id == "asst_plan_save":
            return self._assistant_save_and_surface(ctx, message)
        if option_id == "asst_see_tasks":
            tasks = ctx.tiny_steps[:5]
            text  = (f"Here are your current tasks: 🌱\n\n" + "\n".join(f"• {t}" for t in tasks)
                     if tasks else "Your daily task page is empty — want to add something?")
            return self._resp(text, [
                {"id": "tiny_plan", "label": "Add a task"},
                {"id": "just_talk", "label": "Keep talking"},
            ], "assistant_tasks_view")
        if option_id in ("asst_short","asst_long","asst_varies"):
            ctx.assistant_habits = {
                "asst_short":  "short focused bursts",
                "asst_long":   "longer uninterrupted sessions",
                "asst_varies": "varies depending on the day",
            }[option_id]
            ctx.assistant_discovery_step = max(ctx.assistant_discovery_step, 2)
            if self._assistant_should_create_plan(ctx):
                return self._assistant_create_plan(ctx, message)
            return self._assistant_discover(ctx, message)

        if option_id in ("asst_time_morning","asst_time_afternoon","asst_time_evening","asst_time_weekend"):
            time_map = {
                "asst_time_morning":   "morning",
                "asst_time_afternoon": "afternoon",
                "asst_time_evening":   "evening",
                "asst_time_weekend":   "weekends",
            }
            ctx.assistant_free_time = time_map[option_id]
            ctx.assistant_discovery_step = max(ctx.assistant_discovery_step, 2)
            if self._assistant_should_create_plan(ctx):
                return self._assistant_create_plan(ctx, message)
            return self._assistant_discover(ctx, message)

        if option_id == "privacy_info":
            text = self._llm(ctx, "privacy_acknowledgment", message,
                             fallback=(
                                 "Your conversations are processed locally. 💜 "
                                 "No identifying info is stored with your content. "
                                 "You can delete all data anytime. This is AI support, not clinical care."
                             ))
            return self._resp(text, [{"id":"just_talk","label":"Thank you, let's continue"}],
                              "privacy_info")

        if option_id == "passive_yes":
            ctx.current_state           = UserState.SUICIDAL
            ctx.had_crisis_this_session = True
            ctx.crisis_in_flow          = False
            ctx.crisis_round            = 0
            return self._crisis_route(ctx, message)

        if option_id == "passive_no":
            ctx.in_just_talk        = True
            ctx.just_talk_exchanges = 0
            text = self._llm(ctx, "passive_crisis_acknowledge", message,
                             fallback="I hear you — just struggling is real and valid too. 💜 Tell me more about what has been going on.")
            return self._resp(text, [
                {"id": "just_talk",    "label": "I want to talk"},
                {"id": "calm_feeling", "label": "Help me calm this"},
                {"id": "hear_hope",    "label": "I need some hope"},
            ], "passive_struggle")

        return self._menu(ctx)

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC DATA API
    # ══════════════════════════════════════════════════════════════════════════

    def add_tiny_step(self, uid: str, step: str) -> bool:
        ctx = self._ctx(uid)
        ctx.tiny_steps.insert(0, step)
        ctx.healing_points += 10
        return True

    def complete_tiny_step(self, uid: str, step: str) -> Dict:
        ctx    = self._ctx(uid)
        points = 10 + int(ctx.streak_days * 1.5)
        ctx.healing_points += points
        ctx.streak_days    += 1
        celebrate = self._llm(ctx, "tiny_plan_completion_celebrate", step,
                              template_vars={
                                  "step_text":   step[:60],
                                  "streak_days": str(ctx.streak_days),
                              },
                              fallback=f"You did it. 💜 {ctx.streak_days} days in a row now.")
        return {"message": celebrate, "points_awarded": points,
                "total_points": ctx.healing_points, "streak": ctx.streak_days}

    def add_hope_goal(self, uid: str, goal: str, timeframe: str) -> bool:
        ctx = self._ctx(uid)
        if timeframe in ctx.hope_goals:
            ctx.hope_goals[timeframe].append(goal)
            ctx.healing_points += 15
            return True
        return False

    def get_user_data(self, uid: str) -> Dict:
        ctx = self._ctx(uid)
        return {
            "tiny_steps":          ctx.tiny_steps,
            "hope_goals":          ctx.hope_goals,
            "daily_routine":       ctx.daily_routine,
            "chat_count":          ctx.chat_count,
            "current_state":       ctx.current_state.value,
            "healing_points":      ctx.healing_points,
            "streak_days":         ctx.streak_days,
            "session_risk_level":  ctx.session_risk_level,
            "mood_trajectory":     ctx.mood_trajectory,
            "situation_summary":   ctx.situation_summary,
            "goal_proximity":      ctx.goal_proximity_scores,
            "assistant_plan":      ctx.assistant_plan,
            "assistant_free_time": ctx.assistant_free_time,
        }

    def get_session_analytics(self, uid: str) -> Dict:
        ctx = self._ctx(uid)
        return {
            "uid":                   uid,
            "chat_count":            ctx.chat_count,
            "session_risk_level":    ctx.session_risk_level,
            "risk_score":            self._risk.score(uid),
            "risk_signals":          self._risk.get_signals(uid),
            "mood_trajectory":       ctx.mood_trajectory,
            "current_intensity":     ctx.current_intensity,
            "had_crisis":            ctx.had_crisis_this_session,
            "crisis_round":          ctx.crisis_round,
            "crisis_in_flow":        ctx.crisis_in_flow,
            "ambiguity_count":       ctx.ambiguity_count,
            "help_rejections":       ctx.help_rejections,
            "gaming_suspected":      ctx.gaming_suspected,
            "goal_proximity":        ctx.goal_proximity_scores,
            "situation_profile":     ctx.situation_profile,
            "disclaimer_shown":      ctx.disclaimer_shown,
            "assistant_goal":        ctx.assistant_goal,
            "assistant_free_time":   ctx.assistant_free_time,
        }

    def get_history(self, uid: str) -> List[Dict]:
        return self._ctx(uid).history

    def delete_user_data(self, uid: str) -> bool:
        if uid in self.contexts:
            del self.contexts[uid]
        self._risk.reset(uid)
        self._mood.reset(uid)
        self._repetition.reset(uid)
        self._game.reset(uid)
        self._fallback.reset(uid)
        logger.info(f"User data deleted for uid={uid}")
        return True

    def reset_user(self, uid: str) -> bool:
        if uid not in self.contexts:
            return True
        ctx           = self.contexts[uid]
        tiny_steps    = ctx.tiny_steps[:]
        hope_goals    = {k: v[:] for k, v in ctx.hope_goals.items()}
        daily_routine = ctx.daily_routine[:]
        healing_pts   = ctx.healing_points
        streak        = ctx.streak_days
        self.contexts[uid] = ConversationContext(user_id=uid)
        new_ctx            = self.contexts[uid]
        new_ctx.tiny_steps     = tiny_steps
        new_ctx.hope_goals     = hope_goals
        new_ctx.daily_routine  = daily_routine
        new_ctx.healing_points = healing_pts
        new_ctx.streak_days    = streak
        new_ctx.returning_user = True
        self._risk.reset(uid)
        self._mood.reset(uid)
        self._game.reset(uid)
        self._fallback.reset(uid)
        return True