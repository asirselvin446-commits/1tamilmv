<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=700&size=28&duration=3000&pause=1000&color=F97316&center=true&vCenter=true&width=600&lines=1TamilVT-TG+%F0%9F%8E%AC;Tamil+Movie+Torrent+Bot;Auto-Scraper+%7C+Magnet+Links+%7C+TG+Channel">
  <source media="(prefers-color-scheme: light)" srcset="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=700&size=28&duration=3000&pause=1000&color=EA580C&center=true&vCenter=true&width=600&lines=1TamilVT-TG+%F0%9F%8E%AC;Tamil+Movie+Torrent+Bot;Auto-Scraper+%7C+Magnet+Links+%7C+TG+Channel">
  <img alt="1TamilVT-TG" src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=700&size=28&duration=3000&pause=1000&color=F97316&center=true&vCenter=true&width=600&lines=1TamilVT-TG+%F0%9F%8E%AC;Tamil+Movie+Torrent+Bot;Auto-Scraper+%7C+Magnet+Links+%7C+TG+Channel">
</picture>

<h3>The Ultimate <strong>1TamilMV</strong> Telegram Bot — Auto-Scrape, Auto-Post, Zero Effort.</h3>

<p>
  <a href="https://github.com/aj-2-c-2-a/1tamilvtg_bot/stargazers"><img src="https://img.shields.io/github/stars/aj-2-c-2-a/1tamilvt-tg?style=for-the-badge&logo=github&color=F97316" alt="Stars"></a>
  <a href="https://github.com/aj-2-c-2-a/1tamilvtg_bot/network/members"><img src="https://img.shields.io/github/forks/aj-2-c-2-a/1tamilvt-tg?style=for-the-badge&logo=github&color=3B82F6" alt="Forks"></a>
  <a href="https://github.com/aj-2-c-2-a/1tamilvtg_bot/issues"><img src="https://img.shields.io/github/issues/aj-2-c-2-a/1tamilvt-tg?style=for-the-badge&logo=github&color=EF4444" alt="Issues"></a>
  <a href="https://github.com/aj-2-c-2-a/1tamilvtg_bot/blob/main/LICENSE"><img src="https://img.shields.io/github/license/aj-2-c-2-a/1tamilvt-tg?style=for-the-badge&logo=opensourceinitiative&color=10B981" alt="License"></a>
</p>

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Telegram-Bot API-26A5E4?style=flat-square&logo=telegram&logoColor=white" alt="Telegram">
  <img src="https://img.shields.io/badge/1TamilMV-Scraper-orange?style=flat-square" alt="1TamilMV">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square" alt="Platform">
</p>

</div>

---

## 🎬 What is 1TamilVT-TG?

**1TamilVT-TG** is a powerful, open-source Telegram bot built for **Tamil cinema enthusiasts** who want instant access to the latest Tamil, Telugu, Malayalam, and Hindi movie torrents from **1TamilMV** — directly inside Telegram.

> 🔥 **No more hunting for working 1TamilMV proxy links.** This bot does it automatically.

### Why Users Love It

| Feature | Description |
|---------|-------------|
| 🤖 **Auto-Scraper** | Automatically fetches the latest movies from 1TamilMV every few minutes |
| 🧲 **Magnet Links** | Extracts and delivers clean magnet links + `.torrent` files |
| 📤 **Auto-Post to Channel** | Pushes new releases straight to your Telegram channel with thumbnails |
| 🖼️ **Rich Previews** | Every post includes movie poster, quality info, size, and metadata |
| ⚡ **One-Click Deploy** | Single CMD command on Windows — zero config headache |
| 🛡️ **Proxy Rotation** | Built-in proxy fallback when 1TamilMV domains change |
| 📱 **User Commands** | `/start`, `/latest`, `/search`, `/help` — intuitive and fast |
| 🔔 **Instant Alerts** | Get notified the moment a new movie drops on 1TamilMV |

---

## 🚀 Quick Start

1. Clone or download this repository.
2. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your Telegram Bot Token.
4. Start the bot:
   ```bash
   python -m bot
   ```

---

## 📦 Manual Installation

### Prerequisites
- Python 3.10 or higher
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- A Telegram Channel (make the bot an admin)

### Step 1 — Clone

```bash
git clone https://github.com/aj-2-c-2-a/1tamilvtg_bot.git
cd 1tamilvt-tg
```

### Step 2 — Install

```bash
pip install -r requirements.txt
```

### Step 3 — Configure

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Required
TOKEN=your_telegram_bot_token_here
CHANNEL_ID=-1001234567890
CHANNEL_USERNAME=your_channel_username

# Optional (defaults work out of the box)
TAMILMV_URL=https://www.1tamilmv.fi
WEBHOOK_URL=https://your-app.onrender.com
PORT=8080
SCRAPE_INTERVAL=300
LOG_LEVEL=INFO
```

### Step 4 — Run

```bash
python -m bot
```

---

## 🐳 Docker Deploy (Recommended for Servers)

```bash
docker-compose up -d
```

Or one-liner:

```bash
curl -fsSL https://get.docker.com | sh && git clone https://github.com/aj-2-c-2-a/1tamilvtg_bot.git && cd 1tamilvt-tg && docker-compose up -d
```

---

## ☁️ Cloud Deploy

### Render.com
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/aj-2-c-2-a/1tamilvtg_bot)

### Heroku
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/aj-2-c-2-a/1tamilvtg_bot)

### Koyeb
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=github.com/aj-2-c-2-a/1tamilvt-tg&branch=main&name=1tamilvt-tg)

---

## 🎮 Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message with channel links |
| `/latest` | Show the 10 newest movies from 1TamilMV |
| `/search <query>` | Search TamilMV by movie name |
| `/help` | Show all available commands |
| `/status` | Check bot health and last scrape time |

---

## 🏗️ Tech Stack

```
┌─────────────────────────────────────────┐
│  Python 3.10+                           │
│  ├── python-telegram-bot 20+ (async)   │
│  ├── aiohttp (async HTTP)              │
│  ├── BeautifulSoup4 (HTML parsing)     │
│  ├── Flask (webhook server)            │
│  └── python-dotenv (config)            │
└─────────────────────────────────────────┘
```

---

## 📸 Preview

<div align="center">

| Start Command | Auto Torrent Post |
|:-------------:|:-----------------:|
| <img src="assets/start-cmd.png" width="280" alt="Start"> | <img src="assets/torrent-post.png" width="280" alt="Post"> |

</div>

---

## 🔑 SEO Keywords

`1tamilmv`, `tamilmv`, `tamilmv bot`, `1tamilmv telegram`, `tamil movie torrent bot`, `tamilmv scraper`, `tamil movie downloader telegram`, `1tamilmv proxy`, `tamilmv magnet link`, `kollywood telegram bot`, `tamil movie tracker`, `1tamilmv new link`, `tamilmv auto poster`, `tamil torrent bot`, `1tamilmv 2026`

---

## ⚠️ Disclaimer

> This project is for **educational and research purposes only**. We do not host, distribute, or promote pirated content. The bot scrapes publicly available metadata from 1TamilMV. Users are responsible for complying with their local copyright laws. The authors assume no liability for misuse.

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=aj-2-c-2-a/1tamilvt-tg&type=Date)](https://star-history.com/#aj-2-c-2-a/1tamilvt-tg&Date)

---

## 💬 Community

- 📢 Updates: [@Tamilmv_Magnet_Link](https://t.me/Tamilmv_Magnet_Link)
- 🆘 Support: [@Opleech_WD](https://t.me/Opleech_WD)

---

<div align="center">

**Made with ❤️ for Tamil Cinema Fans**

<a href="https://github.com/aj-2-c-2-a"> <img src="https://img.shields.io/badge/GitHub-aj--2--c--2--a-181717?style=flat-square&logo=github" alt="GitHub"></a>

</div>
