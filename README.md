# Telegram-based Personal AI

A personal AI assistant that runs on your own machine or phone, reachable
through Telegram. Chat with it normally, ask it to set reminders, and it
remembers things about you across conversations. Available for **Linux**
(desktop, via BotManager) and **Android** (native app).

### What you can do with it

- Chat naturally - no special commands needed
- "remind me in 20 minutes to check the oven" - sets reminders
- Remembers durable facts you mention and can forget them on request
- Optional periodic check-ins if you've gone quiet for a while
- Choose your AI backend: **Groq** or **OpenRouter** (free hosted APIs) on
  both platforms, plus **Ollama** (fully local/offline) on Linux only

## Before you start (both platforms)

**1. Get a Telegram bot token**
- Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
  follow the prompts
- Copy the token it gives you (looks like
  `123456789:ABCdefGhIJKlmNoPQRstuVwXyz`)

**2. Get an AI provider key** (skip if using Ollama on Linux)
- **Groq** (recommended, generous free tier): https://console.groq.com/keys
- **OpenRouter**: https://openrouter.ai/keys
- **Ollama** (Linux only, local/offline): install from
  https://ollama.com/download, then pull a model, e.g.
  `ollama pull llama3.2:3b`

---

## Linux setup

1. Make `BotManager` executable: `chmod +x BotManager` (or via your file
   manager's Properties → Permissions)
2. Run it: `./BotManager`
3. Enter your Telegram token, pick your AI provider, and enter its key
4. Select `bot.py` from the script selector
5. Press **Start bot** (first run installs dependencies - give it a
   minute)
6. Message your bot on Telegram, send `/start`
7. Press **Stop bot** in BotManager when done - the bot only runs while
   BotManager is open with the toggle on

**Troubleshooting**
- *Won't open / permission denied* → re-check step 1
- *Stuck installing requirements* → check your internet connection, and
  that `python3`/`pip` are installed and on your `PATH`
- *Bot doesn't respond* → re-copy the token (watch for extra spaces),
  confirm BotManager shows it as running
- *Using Ollama and nothing happens* → make sure `ollama serve` is running
  and your chosen model is pulled

## Android setup

1. Download and install the APK (allow "install from unknown sources" for
   your browser/file app when prompted)
2. Open the app, enter your Telegram token and AI provider + key, tap
   **Save Credentials**
3. Optionally customize the persona, tap **Save Persona**
4. Tap **Allow running in background** (keeps Android from killing the
   bot)
5. Tap **Start bot**
6. Message your bot on Telegram, send `/start`

**Troubleshooting**
- *Bot doesn't respond* → check the app shows "running," re-check the
  token for extra spaces
- *"Invalid token" on start* → re-copy the token from BotFather
- *Bot stops responding when phone is idle* → make sure background running
  is allowed; some brands (Xiaomi, Huawei, Samsung, etc.) have their own
  extra battery/auto-start settings to check too
- *AI replies slow or failing* → check your API key and provider's
  rate limits
