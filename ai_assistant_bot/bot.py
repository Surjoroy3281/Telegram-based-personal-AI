"""
Personal assistant Telegram bot: reminders + chat + web search.

Setup:
    1. cp .env.example .env   and fill in TELEGRAM_BOT_TOKEN (+ GROQ_API_KEY)
    2. pip install -r requirements.txt
    3. python bot.py

See README.md for full setup instructions.
"""
import difflib
import logging
import os
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()  # must run before any local imports below - several read env vars at import time

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

import db
import memory_notepad
from ai_brain import (
    generate_checkin_message,
    get_ai_reply,
    split_reply_and_auto_reminder,
    summarize_search_results,
)
from reminder_parser import LOCAL_TZ, is_reminder_request, parse_reminder
from web_search import search_web

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Proactive check-ins ---
CHECKIN_ENABLED = os.getenv("AUTO_CHECKIN", "true").strip().lower() != "false"
CHECKIN_AFTER_HOURS = float(os.getenv("CHECKIN_AFTER_HOURS", "24"))
CHECKIN_QUIET_START = int(os.getenv("CHECKIN_QUIET_HOUR_START", "22"))  # 10pm
CHECKIN_QUIET_END = int(os.getenv("CHECKIN_QUIET_HOUR_END", "8"))  # 8am
CHECKIN_JOB_INTERVAL_SECONDS = 30 * 60  # how often we check whether it's time

# Rolling chat history per chat, cached in memory and backed by SQLite so it
# survives restarts. MAX_HISTORY_TURNS caps how many exchanges get sent to the
# AI each time (keeps requests small/fast) - full history still lives in the DB.
MAX_HISTORY_TURNS = 12
chat_histories: dict[int, list[dict]] = {}

SEARCH_TRIGGER_RE = re.compile(
    r"^(search( the web)?( for)?|look up|google)\b[:,]?\s*", re.IGNORECASE
)


def get_history(chat_id: int) -> list[dict]:
    """In-memory cache of recent history, lazily loaded from the DB the first
    time a chat is touched after a (re)start."""
    if chat_id not in chat_histories:
        chat_histories[chat_id] = db.get_recent_messages(chat_id, limit=MAX_HISTORY_TURNS * 2)
    return chat_histories[chat_id]


def build_memory_context(chat_id: int) -> str:
    facts = memory_notepad.read_all(chat_id)
    if not facts:
        return ""
    bullet_list = "\n".join(f"- {f}" for f in facts)
    return f"Known facts about the user (remembered from past conversation):\n{bullet_list}"


def parse_auto_reminder(raw: str):
    """
    Parses and validates the "<iso datetime>|<task>" string the AI produces
    for auto-detected reminders. Returns (when, task) or None if the format
    is malformed, the task text is empty, or the time isn't genuinely in the
    future - any of which means "don't trust this, skip it silently" rather
    than surface something wrong to the user.
    """
    if "|" not in raw:
        return None
    iso_part, _, task = raw.partition("|")
    task = task.strip()
    if not task:
        return None
    try:
        when = datetime.fromisoformat(iso_part.strip())
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=LOCAL_TZ)
    now = datetime.now(LOCAL_TZ)
    if when <= now:
        return None
    return when, task


# ---------- Commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db.touch_activity(update.effective_chat.id)
    await update.message.reply_text(
        "Hey! I'm your personal assistant. A few things I can do:\n\n"
        "- Just chat with me normally - I'll pick up on things worth "
        "remembering, look things up, or forget things you ask me to, all "
        "in plain conversation. No special phrasing needed.\n"
        "- \"remind me in 20 minutes to check the oven\" - I'll set a reminder.\n\n"
        "- /reminders - see what's still pending\n"
        "- /cancel <id> - cancel a reminder\n"
        "- /cancelall - cancel every pending reminder\n"
        "- /memories - see everything I remember\n"
        "- /forget <text> - manually forget something matching that text\n"
        "- /forgetall - make me forget everything remembered\n"
        "- /reset - clear our chat history (fresh start; doesn't touch reminders "
        "or remembered facts)\n\n"
        "I'll also check in on my own if I haven't heard from you in a while "
        "(default: 24h, never at night) - you can turn that off in .env if "
        "you'd rather I didn't."
    )


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    pending = db.get_pending_reminders(chat_id)
    if not pending:
        await update.message.reply_text("Nothing pending. You're all clear.")
        return
    lines = []
    for r in pending:
        when = datetime.fromisoformat(r["remind_at"]).strftime("%a %d %b, %H:%M")
        lines.append(f"#{r['id']} - {when} - {r['text']}")
    await update.message.reply_text("\n".join(lines))


async def cancel_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            "Usage: /cancel <id>  (see /reminders for ids), or /cancelall for everything."
        )
        return
    try:
        reminder_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("That doesn't look like a valid id.")
        return

    ok = db.delete_reminder(reminder_id, chat_id)
    # Also remove the scheduled job if it's still pending
    for job in context.job_queue.get_jobs_by_name(f"reminder_{reminder_id}"):
        job.schedule_removal()

    await update.message.reply_text(
        "Cancelled." if ok else "Couldn't find a reminder with that id."
    )


async def cancel_all_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    pending = db.get_pending_reminders(chat_id)

    if not pending:
        await update.message.reply_text("Nothing pending to cancel.")
        return

    if not (context.args and context.args[0].lower() == "confirm"):
        await update.message.reply_text(
            f"This will cancel all {len(pending)} pending reminder(s). "
            f"Send /cancelall confirm to go ahead."
        )
        return

    deleted_ids = db.delete_all_pending_reminders(chat_id)
    for reminder_id in deleted_ids:
        for job in context.job_queue.get_jobs_by_name(f"reminder_{reminder_id}"):
            job.schedule_removal()

    await update.message.reply_text(f"Cancelled all {len(deleted_ids)} pending reminder(s).")


async def safe_typing(update: Update) -> None:
    """The 'typing...' indicator is a nice-to-have, not essential - a flaky
    network blip here shouldn't abort the whole reply."""
    try:
        await update.message.chat.send_action("typing")
    except Exception as e:
        logger.warning("Couldn't send typing indicator (continuing anyway): %s", e)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches anything unhandled so a network blip or API error logs cleanly
    and, where possible, tells the user instead of just going silent."""
    logger.exception("Unhandled exception while processing update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Hit a hiccup reaching a service just now (probably a brief network "
                "blip) - mind trying that again?"
            )
        except Exception:
            pass  # if we can't even send this, there's nothing more we can do


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    db.clear_conversation(chat_id)
    await update.message.reply_text(
        "Fresh start - chat history cleared. (Reminders and remembered facts are untouched.)"
    )


KNOWN_COMMANDS = [
    "start",
    "reminders",
    "cancel",
    "cancelall",
    "memories",
    "forget",
    "forgetall",
    "reset",
]


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches any /command that didn't match one of the real ones above -
    without this, a typo like /memory just gets silently ignored."""
    db.touch_activity(update.effective_chat.id)
    text = update.message.text or ""
    attempted = text.split()[0].lstrip("/").split("@")[0]  # strips "/" and any "@botname" suffix

    close = difflib.get_close_matches(attempted, KNOWN_COMMANDS, n=1, cutoff=0.5)
    if close:
        await update.message.reply_text(f"I don't have a /{attempted} command - did you mean /{close[0]}?")
    else:
        available = ", ".join(f"/{c}" for c in KNOWN_COMMANDS)
        await update.message.reply_text(f"I don't have a /{attempted} command. Available: {available}")


async def list_memories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    facts = memory_notepad.read_all(update.effective_chat.id)
    if not facts:
        await update.message.reply_text("Nothing remembered yet.")
        return
    await update.message.reply_text("\n".join(f"- {f}" for f in facts))


async def forget_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            "Usage: /forget <text to match>  (see /memories for the exact wording), "
            "or /forgetall for everything. You can also just tell me in normal "
            "conversation - \"forget that I mentioned X\" works too."
        )
        return
    text = " ".join(context.args)
    removed = memory_notepad.remove_matching(chat_id, text)
    if removed:
        await update.message.reply_text(
            "Forgot: " + "; ".join(removed) if len(removed) > 1 else f"Forgot: {removed[0]}"
        )
    else:
        await update.message.reply_text("Couldn't find anything matching that.")


async def forget_all_memories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    facts = memory_notepad.read_all(chat_id)

    if not facts:
        await update.message.reply_text("Nothing to forget.")
        return

    if not (context.args and context.args[0].lower() == "confirm"):
        await update.message.reply_text(
            f"This will forget all {len(facts)} remembered fact(s). "
            f"Send /forgetall confirm to go ahead."
        )
        return

    count = memory_notepad.clear(chat_id)
    await update.message.reply_text(f"Forgot all {count} remembered fact(s).")


# ---------- Reminder firing ----------

async def fire_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id, reminder_id, text = job.data["chat_id"], job.data["reminder_id"], job.data["text"]
    await context.bot.send_message(chat_id=chat_id, text=f"⏰ Reminder: {text}")
    db.mark_fired(reminder_id)


def schedule_reminder(app: Application, chat_id: int, reminder_id: int, text: str, when: datetime) -> None:
    app.job_queue.run_once(
        fire_reminder,
        when=when,
        data={"chat_id": chat_id, "reminder_id": reminder_id, "text": text},
        name=f"reminder_{reminder_id}",
    )


def migrate_legacy_memories() -> None:
    """One-time, idempotent migration from the old SQLite memories table to
    the new plain-text notepad files - only touches a chat whose notepad
    file doesn't exist yet, so it's safe to run on every startup."""
    legacy = db.get_legacy_memories()
    for chat_id, facts in legacy.items():
        if memory_notepad.read_all(chat_id):
            continue  # already has a notepad (migrated before, or started fresh there)
        for fact in facts:
            memory_notepad.append(chat_id, fact)
        logger.info("Migrated %d legacy memory row(s) for chat %s to notepad", len(facts), chat_id)


async def reschedule_pending_on_startup(app: Application) -> None:
    """So reminders survive a bot restart instead of silently vanishing."""
    now = datetime.now(LOCAL_TZ)
    for r in db.get_pending_reminders():
        when = datetime.fromisoformat(r["remind_at"])
        if when <= now:
            # Missed while the bot was offline - fire it shortly after startup
            await app.bot.send_message(
                chat_id=r["chat_id"], text=f"⏰ (missed while offline) Reminder: {r['text']}"
            )
            db.mark_fired(r["id"])
        else:
            schedule_reminder(app, r["chat_id"], r["id"], r["text"], when)
    logger.info("Rescheduled pending reminders from the database.")


# ---------- Proactive check-ins ----------

def should_send_checkin(
    now: datetime,
    last_message_at: datetime,
    last_checkin_at: datetime | None,
    after_hours: float = CHECKIN_AFTER_HOURS,
    quiet_start: int = CHECKIN_QUIET_START,
    quiet_end: int = CHECKIN_QUIET_END,
) -> bool:
    """
    Pure decision logic, kept separate from the actual sending so it's easy
    to test without a real bot/clock. True only when:
    - the user has been idle long enough, AND
    - we haven't already sent a check-in during this same idle stretch
      (i.e. no new message has come in since the last check-in), AND
    - it isn't currently quiet hours (a wraparound range like 22->8 is fine)
    """
    if now - last_message_at < timedelta(hours=after_hours):
        return False
    if last_checkin_at is not None and last_checkin_at >= last_message_at:
        return False  # already checked in since the user last spoke

    hour = now.hour
    if quiet_start > quiet_end:  # wraps past midnight, e.g. 22 -> 8
        in_quiet_hours = hour >= quiet_start or hour < quiet_end
    else:
        in_quiet_hours = quiet_start <= hour < quiet_end
    return not in_quiet_hours


async def checkin_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(LOCAL_TZ)
    for row in db.get_all_chat_activity():
        chat_id = row["chat_id"]
        last_message_at = datetime.fromisoformat(row["last_message_at"])
        last_checkin_at = (
            datetime.fromisoformat(row["last_checkin_at"]) if row["last_checkin_at"] else None
        )
        if not should_send_checkin(now, last_message_at, last_checkin_at):
            continue

        idle_hours = (now - last_message_at).total_seconds() / 3600
        memories = memory_notepad.read_all(chat_id)
        try:
            message = generate_checkin_message(idle_hours, memories, chat_id)
            await context.bot.send_message(chat_id=chat_id, text=message)
            db.set_last_checkin(chat_id, now)
            logger.info("Sent check-in to chat %s after %.1fh idle", chat_id, idle_hours)
        except Exception as e:
            logger.warning("Failed to send check-in to chat %s: %s", chat_id, e)


# ---------- Main message routing ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    db.touch_activity(chat_id)

    # 1. Reminder? Only acts on genuinely explicit times ("in 20 minutes",
    # "at 6pm") - anything vaguer (spelled-out times, relative offsets like
    # "half an hour earlier", or a message that just happens to contain
    # "remind me" while actually being a question) falls through to the AI
    # below instead of guessing wrong or hard-failing.
    if is_reminder_request(text):
        parsed = parse_reminder(text)
        if parsed is not None:
            when, what = parsed
            reminder_id = db.add_reminder(chat_id, what, when)
            schedule_reminder(context.application, chat_id, reminder_id, what, when)
            confirmation = (
                f"Got it - I'll remind you to \"{what}\" on "
                f"{when.strftime('%a %d %b, %H:%M')}. (#{reminder_id})"
            )
            # Log to conversation history too, so a later follow-up like
            # "when will you remind me?" has the actual answer in context.
            history = get_history(chat_id)
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": confirmation})
            history[:] = history[-MAX_HISTORY_TURNS * 2 :]
            db.add_message(chat_id, "user", text)
            db.add_message(chat_id, "assistant", confirmation)
            await update.message.reply_text(confirmation)
            return
        # parsed is None - fall through to search/normal chat below rather
        # than dead-ending here.

    # 2. Web search?
    if SEARCH_TRIGGER_RE.match(text):
        query = SEARCH_TRIGGER_RE.sub("", text).strip()
        await safe_typing(update)
        results = search_web(query)
        if not results:
            await update.message.reply_text(
                "Couldn't get search results just now - DuckDuckGo's free search "
                "backend rate-limits pretty aggressively and sometimes needs a "
                "minute to cool down. Try again shortly."
            )
            return
        answer = summarize_search_results(query, results, chat_id)
        db.add_message(chat_id, "user", text)
        db.add_message(chat_id, "assistant", answer)
        await update.message.reply_text(answer)
        return

    # 3. Otherwise, normal chat - remembering/forgetting facts and searching
    # mid-conversation are handled by the AI's own tools now (see ai_brain.py),
    # not guessed here from trigger phrases.
    await safe_typing(update)
    history = get_history(chat_id)
    history.append({"role": "user", "content": text})
    history[:] = history[-MAX_HISTORY_TURNS * 2 :]  # cap length (user+assistant pairs)

    extra_context = build_memory_context(chat_id)
    raw_reply = get_ai_reply(history, chat_id, extra_context)
    reply, auto_reminder_raw = split_reply_and_auto_reminder(raw_reply)

    if auto_reminder_raw:
        parsed = parse_auto_reminder(auto_reminder_raw)
        if parsed:
            when, task = parsed
            reminder_id = db.add_reminder(chat_id, task, when)
            schedule_reminder(context.application, chat_id, reminder_id, task, when)
            reply += (
                f"\n\n(Also set a reminder: \"{task}\" for "
                f"{when.strftime('%a %d %b, %H:%M')}. #{reminder_id} - /cancel "
                f"{reminder_id} if that's not right.)"
            )
            logger.info("Auto-reminder set for chat %s: %s at %s", chat_id, task, when)
        else:
            logger.warning("Model produced an unusable auto-reminder, skipping: %r", auto_reminder_raw)

    history.append({"role": "assistant", "content": reply})
    db.add_message(chat_id, "user", text)
    db.add_message(chat_id, "assistant", reply)

    # Telegram's API rejects empty text, AND strips/rejects whitespace-only
    # and zero-width-only content too (confirmed - a zero-width space alone
    # still gets "Text must be non-empty"). There's no way to send a truly
    # blank message on this platform, so this is the smallest real character
    # that reliably passes - about as close to "blank" as Telegram allows.
    await update.message.reply_text(reply if reply.strip() else "·")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and fill it in."
        )

    db.init_db(os.getenv("DB_PATH", "assistant.db"))
    migrate_legacy_memories()

    # A bit more forgiving than PTB's defaults (5s connect / 5s read) - helps
    # on home connections that occasionally hiccup for a few seconds.
    request = HTTPXRequest(
        connect_timeout=15.0, read_timeout=30.0, write_timeout=15.0, pool_timeout=15.0
    )

    app = (
        Application.builder()
        .token(token)
        .request(request)
        .post_init(lambda a: reschedule_pending_on_startup(a))
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reminders", list_reminders))
    app.add_handler(CommandHandler("cancel", cancel_reminder))
    app.add_handler(CommandHandler("cancelall", cancel_all_reminders))
    app.add_handler(CommandHandler("memories", list_memories))
    app.add_handler(CommandHandler("forget", forget_memory))
    app.add_handler(CommandHandler("forgetall", forget_all_memories))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))  # must come after real commands above
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    if CHECKIN_ENABLED:
        app.job_queue.run_repeating(
            checkin_job, interval=CHECKIN_JOB_INTERVAL_SECONDS, first=CHECKIN_JOB_INTERVAL_SECONDS
        )

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
