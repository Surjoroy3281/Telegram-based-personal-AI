# Telegram-based-personal-AI
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
