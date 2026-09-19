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
  rate limits# Telegram-based-personal-AI
An app to setup a personal AI assistant using Telegram as a frontend and Ollama/Groq/OpenRouter as a backend AI provider.
This app works on Linux and android.


## Android Version

A native Android app version is also available - no Linux machine or
always-on computer needed, it runs right on your phone.

### 1. Get a Telegram bot token

- Open Telegram and message [@BotFather](https://t.me/BotFather)
- Send `/newbot` and follow the prompts (pick a name and a username for
  your bot)
- BotFather will give you a token that looks like
  `123456789:ABCdefGhIJKlmNoPQRstuVwXyz` - copy it, you'll need it in a
  moment

### 2. Get a free AI API key

Pick one:

- **Groq** (recommended, generous free tier) - sign up and grab a key at
  https://console.groq.com/keys
- **OpenRouter** - sign up and grab a key at https://openrouter.ai/keys

### 3. Install the app

- Download the APK from the [Releases page](#) *(link this to your
  actual GitHub Releases URL)*
- Open the downloaded file to install it. Android will likely warn about
  installing from an unknown source the first time - tap **Settings** in
  that prompt and allow it for whichever app you downloaded the file with
  (Chrome, Files, etc.)

### 4. Set it up

Open the app and fill in:

- **Telegram Bot token** - paste what BotFather gave you
- **AI provider** - choose Groq or OpenRouter, and paste the matching API
  key
- **Persona** (optional) - describe how you want the assistant to talk,
  or leave the default

Tap **Save Credentials**, then **Save Persona**.

Tap **Allow running in background** and accept the prompt - this keeps
Android from killing the bot to save battery.

### 5. Start the bot

Tap **Start bot**. Once the status says "running," open Telegram and
message your bot - send `/start` for a quick rundown of what it can do
(chat, set reminders, remember things, etc.).

The app needs to stay installed and the bot toggled on for it to keep
responding - it runs as a background service on your phone rather than
needing a separate server.

### Troubleshooting

- **Bot doesn't respond on Telegram** - make sure the status in the app
  says "running," not "stopped." Double check the bot token was pasted
  correctly (no extra spaces).
- **"Invalid token" or similar error right after starting** - re-copy the
  token from BotFather; a token with the wrong format won't work.
- **Bot stops responding after a while / your phone is asleep** - make
  sure you tapped "Allow running in background." Some phone brands
  (Xiaomi, Huawei, Samsung, etc.) have their own extra battery settings
  beyond Android's standard one - check your phone's battery/auto-start
  settings for the app if it still gets killed.
- **AI replies are slow or failing** - check your API key is correct and
  that you haven't hit your provider's free-tier rate limit.


This app was vibecoded with Claude code sonnet 5.
