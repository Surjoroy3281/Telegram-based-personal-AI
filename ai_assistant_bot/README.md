# Personal Assistant Telegram Bot

A free Telegram bot that:
- Chats with you normally (powered by Groq's free API by default)
- Sets reminders from natural language ("remind me in 20 minutes to check the oven")
- Searches the web when you ask ("search for the weather in Dhaka")
- Remembers your conversation and specific facts you tell it, even across restarts

Runs on your own machine (e.g. your Debian laptop) at zero cost.

## 1. Get a Telegram bot token (2 minutes, free)

1. Open Telegram, search for **@BotFather**, and start a chat.
2. Send `/newbot` and follow the prompts (choose a name and a username ending in `bot`).
3. BotFather will give you a token that looks like `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`. Save it.

## 2. Get a free Groq API key (1 minute, free, no card)

1. Go to https://console.groq.com/keys
2. Sign up with an email or Google account.
3. Create an API key and save it.

(Skip this step if you plan to use local Ollama instead — see "Switching to local AI" below.)

## 3. Install and run

```bash
# 1. Go into the project folder
cd ai_assistant_bot

# 2. Create a virtual environment (keeps this project's packages separate)
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your secrets
cp .env.example .env
nano .env     # paste in your TELEGRAM_BOT_TOKEN and GROQ_API_KEY

# 5. Run it
python bot.py
```

Open Telegram, find the bot you created, and send `/start`. That's it.

## 4. Keep it running in the background (optional but recommended)

So it keeps running after you close the terminal / reboot, set it up as a
systemd service:

```bash
sudo nano /etc/systemd/system/assistant-bot.service
```

Paste this (adjust the paths to match where you put the project):

```ini
[Unit]
Description=Personal Assistant Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/YOUR_USERNAME/ai_assistant_bot
ExecStart=/home/YOUR_USERNAME/ai_assistant_bot/venv/bin/python bot.py
Restart=on-failure
User=YOUR_USERNAME

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now assistant-bot
sudo systemctl status assistant-bot   # check it's running
journalctl -u assistant-bot -f        # watch live logs
```

## How to use it

- **Chat**: just type normally.
- **Reminders**: say something containing "remind me", with an explicit time,
  e.g.:
  - "remind me in 20 minutes to check the oven"
  - "remind me tomorrow at 6pm to call mom"
  - "remind me at 18:00 to submit the report"
  - Vaguer phrasing ("remind me half an hour before I leave", spelled-out
    times like "ten in the morning") isn't parsed by a fixed pattern - it's
    handed to the AI instead, which actually understands natural language
    time expressions rather than guessing. This also means a genuine
    question like "when will you remind me?" gets answered normally
    instead of being mistaken for a new reminder request.
  - `/reminders` — lists everything still pending, with an id
  - `/cancel <id>` — cancels one
  - `/cancelall` — cancels everything pending (asks for `/cancelall confirm` first)
- **Web search**: two ways this happens -
  - Explicitly: start your message with "search for", "search", "look up",
    or "google" (e.g. "search for the weather in Dhaka") for a direct,
    fast lookup.
  - Automatically: in normal conversation, the AI has a real search tool
    it can call whenever it actually needs to - e.g. "make up a unique
    username, then check online that it's not taken" will genuinely search
    partway through answering, rather than just claiming to. It won't
    narrate fake "searching..." theater - if it says it looked something
    up, it actually did.
- **Remembering and forgetting facts**: entirely conversational - no
  command or trigger phrase needed. The AI has real `remember` / `forget` /
  `forget_everything` tools and decides on its own when to use them, the
  same way it decides when to search. Mention an allergy in passing and
  it'll likely remember it; later say "forget that, it's not true anymore"
  and it'll remove it - all in plain conversation.
  - `/memories` — lists everything currently remembered, if you'd rather check manually
  - `/forget <text>` — manually forget anything matching that text
  - `/forgetall` — forgets everything (asks for `/forgetall confirm` first)
- **Automatic reminders**: similarly, if you mention something with a clear
  future time in normal chat - "dentist appointment tomorrow at 3pm",
  "call the bank Monday morning" - it can set a reminder on its own,
  without needing "remind me". This *does* get confirmed in the reply
  (since it's an action with a real future consequence, unlike a quiet
  memory note), and it only ever acts when a time was actually stated - it
  won't invent one. Turn this off with `AUTO_REMINDER=false` in `.env`.
- **Proactive check-ins**: if you haven't messaged in a while (default 24h,
  configurable via `CHECKIN_AFTER_HOURS`), the bot will send a short,
  casual "hey, how's it going" on its own - once per idle stretch (it won't
  repeat until you message again and then go quiet again), and never
  during quiet hours (default 10pm-8am local, configurable via
  `CHECKIN_QUIET_HOUR_START` / `CHECKIN_QUIET_HOUR_END`). Turn it off
  entirely with `AUTO_CHECKIN=false` in `.env`.
- `/reset` — clears the *conversation* history (fresh start); reminders and
  remembered facts are untouched

## What's stored where

- **Reminders and conversation history** live in `assistant.db` (SQLite).
  Reminders survive restarts, and fire even if the bot was briefly offline
  (it'll send a "missed while offline" message on the next startup). The
  last ~12 exchanges of conversation reload automatically after a restart
  so the AI doesn't lose context - `/reset` wipes this.
- **Remembered facts** live in `memories/<chat_id>.txt` - a plain text
  file, one fact per line. Open it in any text editor to see (or
  hand-edit) exactly what's remembered; no database, no ids to track. It's
  always included in the AI's context (not just recent conversation), so
  it can recall facts long after the conversation that mentioned them has
  scrolled away. `/reset` does *not* clear this - use `/forget` or
  `/forgetall` for that, or just edit the file directly.

Everything lives only on your own machine — nothing is sent anywhere except
to Groq (or Ollama, if local) to generate replies, and to DuckDuckGo when you
ask it to search.

## Customizing the bot's personality

Open `persona.txt` in any text editor and rewrite it however you like -
this is what gets sent to the AI as its personality instructions. For
example:

```
You are a blunt, no-nonsense assistant. Skip pleasantries, get straight
to the point, and don't pad replies with filler.
```

or

```
You are Nova, a warm and upbeat assistant. Use a friendly, encouraging
tone and the occasional emoji, but keep replies short.
```

Save the file and restart the bot (`Ctrl+C` then `python bot.py` again) for
the change to take effect. This only affects normal chat replies - reminder
confirmations and search summaries are separate, fixed messages.

## Switching AI providers (OpenRouter or local Ollama)

`ai_brain.py` supports three backends behind one `get_ai_reply()` function -
switching is just a `.env` change, no code changes needed.

**OpenRouter** (free hosted, different model catalog than Groq - useful as a
backup, or if you specifically want a model Groq doesn't offer, like Gemma):

```
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...    # free key at https://openrouter.ai/keys
OPENROUTER_MODEL=google/gemma-4-31b-it:free
```

**Ollama** (fully offline, no API dependency at all):

```bash
# On Debian:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
```

Then in `.env`:

```
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b
```

Local models will be noticeably slower on 8GB RAM / no dedicated GPU, and a
bit less sharp in conversation, but zero cost and fully private.

## Notes on free-tier limits

Groq's free tier allows roughly 30 requests/minute and 14,400/day per
account — far more than a personal assistant bot will ever need for one
person messaging it throughout the day. OpenRouter's free models are
rate-limited too (varies by model). If you ever hit a limit, the bot will
just show you the error message rather than crashing; wait a bit and try
again, or switch providers in `.env`.

## Project structure

```
ai_assistant_bot/
├── bot.py               # Telegram handlers, message routing, reminder firing
├── ai_brain.py           # Swappable chat backend (Groq / OpenRouter / Ollama) + AI tools
├── memory_notepad.py     # Plain-text remembered-facts storage (one fact per line)
├── persona.txt           # Edit this to change the bot's personality
├── web_search.py         # Free DuckDuckGo search
├── reminder_parser.py    # Natural-language time parsing for reminders
├── db.py                 # SQLite storage for reminders + conversation history
├── memories/             # Created automatically - one <chat_id>.txt per chat
├── requirements.txt
├── .env.example          # Copy to .env and fill in your keys
└── README.md
```
