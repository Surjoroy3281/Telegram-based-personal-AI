"""
Turns natural sentences like:
    "remind me in 20 minutes to check the oven"
    "remind me tomorrow at 6pm to call mom"
    "remind me at 18:00 to submit the report"
into a (datetime, reminder_text) pair - no rigid command syntax required.

Relative phrases ("in N minutes/hours/days") are computed directly.
Absolute-ish phrases ("tomorrow at 6pm", "at 18:00", "tonight") are handed
to dateparser just for that isolated phrase, which is far more reliable
than asking dateparser to search the whole free-form sentence.
"""
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

import dateparser
from tzlocal import get_localzone

TRIGGER_RE = re.compile(r"\bremind me\b", re.IGNORECASE)
GLUE_WORDS = re.compile(r"^\s*(to|that|about)\b[:,]?\s*", re.IGNORECASE)

# Detected once at import time. All reminder times are anchored to this so
# there's never ambiguity about which timezone a stored/scheduled time means
# (python-telegram-bot's scheduler defaults to UTC for naive datetimes, which
# silently misfires reminders on any machine not already set to UTC).
LOCAL_TZ = get_localzone()

RELATIVE_RE = re.compile(
    r"\bin\s+(\d+)\s*"
    r"(minutes?|mins?|hours?|hrs?|days?|seconds?|secs?)\b",
    re.IGNORECASE,
)

UNIT_TO_KWARG = {
    "minute": "minutes", "minutes": "minutes", "min": "minutes", "mins": "minutes",
    "hour": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
    "day": "days", "days": "days",
    "second": "seconds", "seconds": "seconds", "sec": "seconds", "secs": "seconds",
}

# Checked in order after RELATIVE_RE. Each alternative's whole match is what
# gets handed to dateparser and stripped out of the reminder text. Only
# explicit times are matched here - bare "tomorrow"/"today"/"tonight" with no
# attached time used to fall back to a hardcoded guess (e.g. always 9am for
# "tomorrow"), which silently produced a wrong time whenever the guess didn't
# happen to match what the user meant. Anything that vague now falls through
# to the AI instead of us blindly guessing.
TIME_PHRASE_RE = re.compile(
    r"\b(?:tomorrow|today|tonight)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b"
    r"|\bat\s+\d{1,2}:\d{2}\s*(?:am|pm)?\b"
    r"|\bat\s+\d{1,2}\s*(?:am|pm)\b",
    re.IGNORECASE,
)


def is_reminder_request(text: str) -> bool:
    return bool(TRIGGER_RE.search(text))


def parse_reminder(text: str) -> Optional[Tuple[datetime, str]]:
    """
    Only succeeds for genuinely explicit times ("in 20 minutes", "at 6pm",
    "tomorrow at 18:00"). Returns None for anything vaguer - spelled-out
    times ("ten in the morning"), relative offsets ("half an hour earlier"),
    or a bare "tomorrow"/"today" with no time attached - rather than
    guessing, since a wrong guess is worse than admitting it doesn't know.
    The caller falls through to the AI (which actually understands natural
    language time expressions) when this returns None.
    """
    now = datetime.now(LOCAL_TZ)

    m = RELATIVE_RE.search(text)
    if m:
        amount = int(m.group(1))
        unit = UNIT_TO_KWARG[m.group(2).lower()]
        when = now + timedelta(**{unit: amount})
        return when, _strip(text, m.span())

    m = TIME_PHRASE_RE.search(text)
    if m:
        phrase = m.group(0)
        when = dateparser.parse(
            phrase,
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": now.replace(tzinfo=None),
            },
        )
        if when is not None:
            when = when.replace(tzinfo=LOCAL_TZ)

        if when:
            if when <= now:
                when = when + timedelta(days=1)
            return when, _strip(text, m.span())

    return None


LEADING_FILLER_RE = re.compile(
    r"^\s*(can you|could you|would you|please)\b[\s,]*", re.IGNORECASE
)


def _strip(text: str, span: tuple[int, int]) -> str:
    start, end = span
    remainder = text[:start] + text[end:]
    remainder = TRIGGER_RE.sub("", remainder)
    remainder = LEADING_FILLER_RE.sub("", remainder)
    remainder = GLUE_WORDS.sub("", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip(" ,.-")
    return remainder or "this"
