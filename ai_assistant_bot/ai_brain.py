"""
The "brain" of the assistant. Everything else in the bot talks to this
module through get_ai_reply() only - it doesn't know or care whether the
reply came from Groq, OpenRouter, or a local Ollama model.

To switch providers later: change AI_PROVIDER in your .env file.
No other code needs to change.
"""
import json
import os
from datetime import datetime

import requests
from dotenv import load_dotenv
from tzlocal import get_localzone

import memory_notepad
from web_search import search_web

# Defensive, not just belt-and-suspenders: this module reads env vars at
# import time below, so if something ever imports ai_brain before the entry
# point's own load_dotenv() runs, those reads would silently see stale/
# missing values. load_dotenv() is idempotent, so calling it again here (or
# from bot.py) is harmless either way - this just guarantees correctness
# regardless of import order.
load_dotenv()

AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
AUTO_REMINDER_ENABLED = os.getenv("AUTO_REMINDER", "true").strip().lower() != "false"
LOCAL_TZ = get_localzone()

_PERSONA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.txt")

_DEFAULT_PERSONA = (
    "You are a helpful, friendly personal assistant reachable over Telegram. "
    "Keep replies concise and conversational, like a text message - not a "
    "formal essay."
)

_TECHNICAL_NOTE = (
    "You can also set reminders when asked, but that is handled outside of "
    "you - just chat naturally otherwise. You DO have real tools available "
    "(see tools): web_search for checking current/real-world information, "
    "and remember / forget / forget_everything for managing a persistent "
    "notepad of facts about the user - use them naturally, whenever it "
    "actually makes sense, without needing the user to use a specific "
    "command or phrase. Call remember when the user shares something "
    "durable worth keeping (preferences, allergies, important details) - "
    "conservatively, not for casual chit-chat. Call forget when they ask "
    "you to forget something specific, and forget_everything only when they "
    "clearly and explicitly want everything wiped. NEVER narrate or claim "
    "to be doing any of this (no '*searching*', no 'noted, I'll remember "
    "that') unless you are actually calling the corresponding tool - if you "
    "don't call it, don't pretend to. Be efficient with searches - one or "
    "two well-chosen queries are usually enough."
)

_AUTO_REMINDER_INSTRUCTION = (
    "\n\nAlso decide whether the user's message describes something they "
    "should be reminded about at a specific future time - an appointment, "
    "deadline, or event. Only do this if a clear date/time is stated or "
    "obviously implied (e.g. \"tomorrow at 3pm\", \"next Friday\", \"in two "
    "hours\") - never invent or guess a time, and never flag anything if no "
    "real time was given. Use the current date/time above to resolve "
    "relative expressions into an exact moment. On its own final line, "
    "output exactly one of:\n"
    "REMINDER: <ISO 8601 datetime, e.g. 2026-09-14T15:00:00>|<short task>\n"
    "REMINDER: NONE\n"
    "This line is parsed by a program and stripped before the user ever "
    "sees your reply - always include it on its own final line."
)


def _current_time_note() -> str:
    now = datetime.now(LOCAL_TZ)
    return f"Current date and time: {now.strftime('%A, %Y-%m-%d %H:%M')} (timezone: {LOCAL_TZ})."


def _load_persona() -> str:
    """Reads persona.txt fresh on every call (cheap - it's a tiny file), so
    editing the persona and restarting the bot is all that's needed - no
    caching to worry about."""
    try:
        with open(_PERSONA_PATH, "r", encoding="utf-8") as f:
            text = f.read().strip()
            return text if text else _DEFAULT_PERSONA
    except FileNotFoundError:
        return _DEFAULT_PERSONA


def _system_prompt() -> str:
    prompt = f"{_load_persona()}\n\n{_TECHNICAL_NOTE}\n\n{_current_time_note()}"
    if AUTO_REMINDER_ENABLED:
        prompt += _AUTO_REMINDER_INSTRUCTION
    return prompt


# ---------- Tools ----------

_WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current, real-world information. Use this "
            "whenever you need to verify a fact, check whether something "
            "(like a username or name) already exists, or answer anything "
            "that needs up-to-date information you can't be sure of from "
            "memory alone."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The search query"}},
            "required": ["query"],
        },
    },
}

_REMEMBER_TOOL = {
    "type": "function",
    "function": {
        "name": "remember",
        "description": (
            "Save a durable fact about the user to the persistent memory "
            "notepad, for recall in future conversations. Only for things "
            "genuinely worth keeping long-term - preferences, allergies, "
            "important dates, routines, personal details - not casual chit-chat."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to remember, as a short standalone statement",
                }
            },
            "required": ["fact"],
        },
    },
}

_FORGET_TOOL = {
    "type": "function",
    "function": {
        "name": "forget",
        "description": (
            "Remove a specific remembered fact. Any currently-remembered "
            "fact containing the given text will be removed - use text "
            "from the fact itself (see the remembered facts listed in "
            "context), not a paraphrase."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to match against remembered facts for removal",
                }
            },
            "required": ["text"],
        },
    },
}

_FORGET_EVERYTHING_TOOL = {
    "type": "function",
    "function": {
        "name": "forget_everything",
        "description": (
            "Erase ALL remembered facts about the user. Only call this if "
            "the user clearly and explicitly asks to forget everything or "
            "wipe all memory - never on an ambiguous or partial request."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

_ALL_TOOLS = [_WEB_SEARCH_TOOL, _REMEMBER_TOOL, _FORGET_TOOL, _FORGET_EVERYTHING_TOOL]

MAX_TOOL_ROUNDS = 4


def _run_web_search_tool(query: str) -> str:
    results = search_web(query) if query else []
    if not results:
        return "No search results found."
    return "\n".join(f"- {r.get('title', '')}: {r.get('body', '')}" for r in results[:5])


def _dispatch_tool(name: str, args: dict, chat_id: int) -> str:
    if name == "web_search":
        return _run_web_search_tool(args.get("query", ""))

    if name == "remember":
        fact = (args.get("fact") or "").strip()
        if not fact:
            return "No fact provided - nothing saved."
        added = memory_notepad.append(chat_id, fact)
        return f'Saved: "{fact}"' if added else "That's already remembered (skipped duplicate)."

    if name == "forget":
        text = (args.get("text") or "").strip()
        removed = memory_notepad.remove_matching(chat_id, text)
        if removed:
            return f"Removed {len(removed)} matching fact(s): " + "; ".join(removed)
        return "No matching remembered fact found."

    if name == "forget_everything":
        count = memory_notepad.clear(chat_id)
        return f"Cleared all {count} remembered fact(s)."

    return f"Unknown tool: {name}"


def get_ai_reply(history: list[dict], chat_id: int, extra_context: str = "") -> str:
    """
    history: list of {"role": "user"|"assistant", "content": str}, oldest first.
    chat_id: which chat's memory notepad the remember/forget tools act on.
    extra_context: optional extra text appended to the system prompt - used
    for injecting the user's currently-remembered facts.
    Returns the assistant's reply text.
    """
    system_content = _system_prompt()
    if extra_context:
        system_content = f"{system_content}\n\n{extra_context}"

    if AI_PROVIDER == "ollama":
        return _ollama_reply(history, system_content, chat_id)
    if AI_PROVIDER == "openrouter":
        return _openrouter_reply(history, system_content, chat_id)
    return _groq_reply(history, system_content, chat_id)


def _groq_reply(history: list[dict], system_content: str, chat_id: int) -> str:
    from groq import Groq  # imported lazily so Ollama-only users don't need it installed

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return (
            "I can't reach my AI brain yet - GROQ_API_KEY is missing from your "
            ".env file. Grab a free key at https://console.groq.com/keys"
        )

    client = Groq(api_key=api_key)
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    messages = [{"role": "system", "content": system_content}] + history

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=600,
                tools=_ALL_TOOLS,
                tool_choice="auto",
            )
        except Exception as e:  # rate limit, network blip, etc.
            return f"(AI error, try again in a moment: {e})"

        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return (msg.content or "").strip()

        # Model wants to use a tool before answering - run it for real and
        # feed the actual result back, rather than letting it guess/hallucinate.
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result_text = _dispatch_tool(tc.function.name, args, chat_id)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})

    # Hit the round cap while the model still wanted to use tools more -
    # force one last answer using everything already gathered instead of
    # just giving up, since useful results are likely already in `messages`.
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.7, max_tokens=600, tool_choice="none"
        )
        return (resp.choices[0].message.content or "").strip() or (
            "Took a few steps there but couldn't quite wrap it up - mind trying again?"
        )
    except Exception as e:
        return f"(AI error, try again in a moment: {e})"


def _ollama_reply(history: list[dict], system_content: str, chat_id: int) -> str:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    messages = [{"role": "system", "content": system_content}] + history

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = requests.post(
                f"{host}/api/chat",
                json={"model": model, "messages": messages, "stream": False, "tools": _ALL_TOOLS},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return (
                f"(Couldn't reach Ollama at {host} - is it running? `ollama serve`. "
                f"Error: {e})"
            )

        message = data.get("message", {})
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return (message.get("content") or "").strip()

        # Not every local model actually supports tool calling well - if it
        # tries but the format is unusable, just fall back to its plain text.
        messages.append(message)
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name")
            args = func.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            result_text = _dispatch_tool(name, args, chat_id)
            messages.append({"role": "tool", "content": result_text})

    # Same rationale as the Groq path above: force a final text answer from
    # what's already been gathered instead of discarding it.
    try:
        resp = requests.post(
            f"{host}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        content = (resp.json().get("message", {}).get("content") or "").strip()
        return content or "Took a few steps there but couldn't quite wrap it up - mind trying again?"
    except Exception as e:
        return f"(Couldn't reach Ollama at {host} - is it running? `ollama serve`. Error: {e})"


def _openrouter_reply(history: list[dict], system_content: str, chat_id: int) -> str:
    """
    OpenRouter is OpenAI-compatible, so this mirrors the Groq path's shape
    (JSON dicts instead of SDK objects, matching the Ollama path's style
    instead, since this uses plain requests rather than a dedicated SDK).
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return (
            "I can't reach my AI brain yet - OPENROUTER_API_KEY is missing from "
            "your .env file. Grab a free key at https://openrouter.ai/keys"
        )

    model = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Optional per OpenRouter's docs, but recommended - identifies your
        # app in their dashboard/rankings, doesn't affect functionality.
        "HTTP-Referer": "https://github.com/",
        "X-Title": "Personal Telegram Assistant Bot",
    }
    messages = [{"role": "system", "content": system_content}] + history

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 600,
                    "tools": _ALL_TOOLS,
                    "tool_choice": "auto",
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # rate limit, network blip, etc.
            return f"(AI error, try again in a moment: {e})"

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return (message.get("content") or "").strip()

        messages.append(message)
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name")
            raw_args = func.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            result_text = _dispatch_tool(name, args, chat_id)
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": result_text})

    # Same rationale as the Groq path: force a final answer from what's
    # already been gathered instead of discarding it.
    try:
        resp = requests.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 600,
                "tool_choice": "none",
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = ((resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
        return content or "Took a few steps there but couldn't quite wrap it up - mind trying again?"
    except Exception as e:
        return f"(AI error, try again in a moment: {e})"


# ---------- Auto-reminder detection (memory now goes through real tools above) ----------


def split_reply_and_auto_reminder(raw_reply: str) -> tuple[str, str]:
    """
    Pulls a trailing hidden "REMINDER: ..." marker the model was instructed
    to append off of its reply. Uses the LAST case-insensitive occurrence of
    "REMINDER:" in the text rather than requiring it to start its own line -
    models sometimes glue it directly onto the visible text with no newline
    (e.g. "...anything?REMINDER: NONE"), which a line-anchored match would
    miss entirely, leaking the raw marker into what the user sees.

    Returns (visible_reply, auto_reminder_raw) where auto_reminder_raw is ""
    if no reminder was flagged, otherwise the raw "<iso datetime>|<task>"
    string for the caller to parse and validate. Fails safe: if
    AUTO_REMINDER is disabled or the marker isn't present, it comes back
    empty rather than guessing. visible_reply CAN legitimately be "" if the
    model's entire reply was just the marker (e.g. the user asked for a
    blank response) - the caller decides how to handle that, not this
    function pretending it didn't happen by resurrecting the raw text.
    """
    text = raw_reply.rstrip()
    auto_reminder_raw = ""

    if AUTO_REMINDER_ENABLED:
        idx = text.upper().rfind("REMINDER:")
        if idx != -1:
            value = text[idx + len("REMINDER:") :].strip().strip("\"'")
            auto_reminder_raw = "" if (not value or value.upper() == "NONE") else value
            text = text[:idx].rstrip()

    return text, auto_reminder_raw


def generate_checkin_message(hours_idle: float, memories: list[str], chat_id: int) -> str:
    """A short, in-persona 'haven't heard from you in a while' message,
    sent proactively after real inactivity (see AUTO_CHECKIN in bot.py)."""
    days = hours_idle / 24
    idle_desc = f"about {days:.0f} day(s)" if days >= 1 else f"about {hours_idle:.0f} hour(s)"
    context = ""
    if memories:
        context = "\nA couple of things you know about the user: " + "; ".join(memories[:3])

    prompt = (
        f"You haven't heard from the user in {idle_desc}. Send a short, "
        "casual check-in message - one or two sentences, low-key, not "
        "clingy or dramatic. Just a friendly 'hey, how's it going' type "
        f"nudge, in your own persona's voice.{context}"
    )
    return get_ai_reply([{"role": "user", "content": prompt}], chat_id).strip()


def summarize_search_results(query: str, results: list[dict], chat_id: int) -> str:
    """Feed raw search snippets to the AI and get a short, spoken-language answer."""
    snippets = "\n\n".join(
        f"- {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})" for r in results
    )
    prompt = (
        f'The user asked: "{query}"\n\n'
        f"Here are web search results:\n\n{snippets}\n\n"
        "Write a short, plain-language answer (2-5 sentences) based on these "
        "results, as if replying in a chat. Mention a source name only if it "
        "matters; don't dump raw links."
    )
    return get_ai_reply([{"role": "user", "content": prompt}], chat_id)
