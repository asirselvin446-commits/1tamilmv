"""Main entry point for 1TamilVT-TG Telegram Bot."""
import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from bot.config import Config
from bot.scraper import TamilMVScraper

# ── Logging ──────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Globals ──────────────────────────────────────────────────────────
scraper = TamilMVScraper()
last_scrape_time: datetime = datetime.min
last_movies: List[Dict] = []
# Cache recent search and latest movie lists for callback lookups: {chat_id: [movies]}
movie_cache: Dict[int, List[Dict]] = {}
# History of posted URLs to prevent duplicates in channel
posted_topics: set = set()

# ── Helpers ──────────────────────────────────────────────────────────
def _build_main_menu() -> InlineKeyboardMarkup:
    """Build persistent quick action buttons."""
    buttons = [
        [
            InlineKeyboardButton("🆕 Latest Movies", callback_data="cmd_latest"),
            InlineKeyboardButton("📊 Bot Status", callback_data="cmd_status"),
        ],
    ]
    if Config.CHANNEL_USERNAME:
        buttons.append([InlineKeyboardButton("📢 Channel", url=f"https://t.me/{Config.CHANNEL_USERNAME}")])
    return InlineKeyboardMarkup(buttons)

async def _send_topic_details(target, context: ContextTypes.DEFAULT_TYPE, topic_url: str, title: str = ""):
    """Fetch and send movie topic details including poster and magnet links."""
    wait_msg = await target.reply_text("⏳ Fetching magnet links & details... Please wait.")
    details = await scraper.get_topic_details(topic_url)

    if not details or "error" in details:
        await wait_msg.edit_text(f"❌ Failed to fetch topic details: {details.get('error', 'Unknown error')}")
        return

    movie_title = details.get("title") or title or "Movie Details"
    poster_url = details.get("poster")
    torrents = details.get("torrents", [])

    text_parts = [
        f"🎬 <b>{movie_title}</b>\n",
        f"🔗 <a href='{topic_url}'>View on 1TamilMV</a>\n",
    ]

    if torrents:
        text_parts.append(f"🧲 <b>Available Torrent Releases ({len(torrents)}):</b>\n")
        for i, t in enumerate(torrents, 1):
            name = t.get("name", f"Release #{i}")
            size = t.get("size", "N/A")
            magnet = t.get("magnet", "")
            text_parts.append(
                f"<b>{i}. {name}</b>\n"
                f"📦 Size: <code>{size}</code>\n"
                f"🧲 <b>Magnet Link:</b> (Tap to copy)\n"
                f"<code>{magnet}</code>\n"
            )
    direct_links = details.get("direct_links", [])
    if direct_links:
        text_parts.append(f"\n📥 <b>Download Links / Mirrors ({len(direct_links)}):</b>\n")
        for j, d in enumerate(direct_links[:6], 1):
            d_name = d.get("name", f"Mirror #{j}")
            d_url = d.get("url", "")
            text_parts.append(f"• <a href='{d_url}'>{d_name}</a>\n")

    if not torrents and not direct_links:
        text_parts.append("\n⚠️ <i>No direct download links found in this topic. Open the website link to view topic details.</i>")

    full_text = "\n".join(text_parts)

    buttons = [
        [InlineKeyboardButton("🌐 Open 1TamilMV Topic", url=topic_url)],
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    # Try sending poster with caption if text length fits Telegram's 1024 caption limit
    poster_sent = False
    if poster_url and len(full_text) <= 1000:
        try:
            await wait_msg.delete()
            await target.reply_photo(
                photo=poster_url,
                caption=full_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            poster_sent = True
        except Exception as e:
            logger.debug(f"Could not send photo directly: {e}")

    if not poster_sent:
        # Edit waiting message with text
        # If text is longer than 4096 chars, chunk it
        if len(full_text) > 4000:
            await wait_msg.delete()
            # Send in chunks
            for chunk in [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]:
                await target.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        else:
            await wait_msg.edit_text(
                full_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )

# ── Handlers ─────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message and guide."""
    if not update.message:
        return

    welcome = (
        "👋 <b>Welcome to 1TamilVT-TG!</b>\n\n"
        "🎥 I automatically fetch and deliver the <b>latest Tamil, Telugu, Malayalam & Hindi movie torrents</b> "
        "and magnet links directly from <b>1TamilMV</b>.\n\n"
        "⚡ <b>Available Commands:</b>\n"
        "  /latest — Show recent movie uploads\n"
        "  /search <code>movie name</code> — Search movies & torrents\n"
        "  /status — View bot connection and scraper health\n"
        "  /help — Show commands & usage guide\n\n"
        "👇 Use the buttons below for quick access:"
    )
    await update.message.reply_text(welcome, reply_markup=_build_main_menu(), parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help guide."""
    await start(update, context)

async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and display latest movie releases with interactive buttons."""
    global last_scrape_time, last_movies

    msg_target = update.message or (update.callback_query.message if update.callback_query else None)
    chat_id = update.effective_chat.id if update.effective_chat else 0

    if not msg_target:
        return

    wait_msg = await msg_target.reply_text("⏳ Scraping latest releases from 1TamilMV... Please wait.")

    movies = await scraper.get_latest(limit=10)
    if not movies:
        await wait_msg.edit_text(
            "❌ Could not reach 1TamilMV.\n"
            "The site mirror may be blocked or undergoing maintenance. Try again in a few moments."
        )
        return

    last_movies = movies
    last_scrape_time = datetime.now()
    if chat_id:
        movie_cache[chat_id] = movies

    text = f"🆕 <b>Latest Movies on 1TamilMV</b> ({len(movies)} found)\n\n"
    for i, movie in enumerate(movies, 1):
        text += (
            f"<b>{i}. {movie['title']}</b>\n"
            f"   📊 Quality: <code>{movie['quality']}</code>\n\n"
        )
    text += "👇 <i>Tap a button below to get Magnet links & details:</i>"

    # Create grid of numbered buttons
    keyboard_buttons = []
    row = []
    for i in range(1, len(movies) + 1):
        row.append(InlineKeyboardButton(f"📥 #{i}", callback_data=f"get_{i-1}"))
        if len(row) == 5:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)

    await wait_msg.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard_buttons),
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search 1TamilMV by query."""
    if not update.message:
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/search Idhayam Murali</code>\n"
            "Please provide a movie name to search.",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(context.args)
    wait_msg = await update.message.reply_text(f"🔍 Searching 1TamilMV for '<b>{query}</b>'...", parse_mode=ParseMode.HTML)

    movies = await scraper.search(query, limit=10)
    if not movies:
        await wait_msg.edit_text(
            f"❌ No releases found for '<b>{query}</b>'.\n"
            f"Tip: Try searching with a single key word (e.g. <code>/search Idhayam</code> or <code>/search Murali</code>).",
            parse_mode=ParseMode.HTML,
        )
        return

    if chat_id:
        movie_cache[chat_id] = movies

    text = f"🔍 <b>Search Results for '{query}'</b> ({len(movies)} found)\n\n"
    for i, movie in enumerate(movies, 1):
        text += (
            f"<b>{i}. {movie['title']}</b>\n"
            f"   📊 Quality: <code>{movie['quality']}</code>\n\n"
        )
    text += "👇 <i>Tap a button below to get Magnet links:</i>"

    keyboard_buttons = []
    row = []
    for i in range(1, len(movies) + 1):
        row.append(InlineKeyboardButton(f"📥 #{i}", callback_data=f"get_{i-1}"))
        if len(row) == 5:
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)

    await wait_msg.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard_buttons),
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive inline buttons."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    chat_id = update.effective_chat.id if update.effective_chat else 0

    if data == "cmd_latest":
        await latest(update, context)
        return
    elif data == "cmd_status":
        await status(update, context)
        return
    elif data.startswith("get_"):
        try:
            idx = int(data.split("_")[1])
            cached = movie_cache.get(chat_id, last_movies)
            if 0 <= idx < len(cached):
                movie = cached[idx]
                await _send_topic_details(query.message, context, movie["url"], movie.get("title", ""))
            else:
                await query.message.reply_text("⚠️ Movie selection expired. Please run /latest or /search again.")
        except Exception as e:
            logger.error(f"Callback error: {e}")
            await query.message.reply_text("❌ Failed to load movie details.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot and scraper health status."""
    msg_target = update.message or (update.callback_query.message if update.callback_query else None)
    if not msg_target:
        return

    uptime = datetime.now() - last_scrape_time if last_scrape_time != datetime.min else None
    uptime_str = f"{uptime.total_seconds():.0f}s ago" if uptime else "Never"

    text = (
        f"🤖 <b>1TamilVT-TG Bot Status</b>\n\n"
        f"🌐 <b>Active Mirror:</b> <code>{scraper.working_domain or Config.TAMILMV_URL or 'N/A'}</code>\n"
        f"🕐 <b>Last Scrape:</b> {uptime_str}\n"
        f"📦 <b>Cached Releases:</b> {len(last_movies)}\n"
        f"⏱️ <b>Auto-Scrape Interval:</b> {Config.SCRAPE_INTERVAL}s\n"
        f"📢 <b>Target Channel:</b> @{Config.CHANNEL_USERNAME or 'Not Set'}\n"
        f"🟢 <b>Status:</b> Operational & Ready"
    )
    await msg_target.reply_text(text, parse_mode=ParseMode.HTML)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unknown commands."""
    if update.message:
        await update.message.reply_text(
            "❓ Unknown command. Use /help to see available options.",
            parse_mode=ParseMode.HTML,
        )

# ── Auto-Poster ──────────────────────────────────────────────────────
async def auto_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job: automatically scrape and push new movie releases to the channel."""
    global last_scrape_time, last_movies, posted_topics

    if not Config.CHANNEL_ID or Config.CHANNEL_ID in [0, -1001234567890, 8370772224]:
        return

    logger.info("Running auto-poster background job...")
    movies = await scraper.get_latest(limit=6)
    if not movies:
        logger.warning("Auto-post: no movies found on 1TamilMV.")
        return

    last_scrape_time = datetime.now()
    last_movies = movies

    for movie in movies[:3]:
        url = movie.get("url", "")
        if not url or url in posted_topics:
            continue

        posted_topics.add(url)
        # Fetch topic details for rich post
        details = await scraper.get_topic_details(url)
        torrents = details.get("torrents", [])
        poster = details.get("poster")
        title = details.get("title") or movie["title"]

        caption = (
            f"🎬 <b>{title}</b>\n"
            f"📊 Quality: <code>{movie['quality']}</code>\n"
        )
        if torrents:
            caption += f"📦 Releases: <code>{len(torrents)} versions</code>\n"
        caption += (
            f"🔗 <a href='{url}'>Download from 1TamilMV</a>\n\n"
            f"#TamilMV #Kollywood #Movies"
        )

        buttons = [
            [InlineKeyboardButton("🌐 Open 1TamilMV Topic", url=url)],
        ]
        if torrents and torrents[0].get("magnet"):
            buttons.append([InlineKeyboardButton("🧲 Copy Magnet Link", url=url)])

        keyboard = InlineKeyboardMarkup(buttons)

        try:
            if poster:
                await context.bot.send_photo(
                    chat_id=Config.CHANNEL_ID,
                    photo=poster,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            else:
                await context.bot.send_message(
                    chat_id=Config.CHANNEL_ID,
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Failed to push post to channel {Config.CHANNEL_ID}: {e}")

# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    """Start the bot."""
    Config.validate()

    application = Application.builder().token(Config.TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("status", status))

    # Interactive buttons callback handler
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Unknown command fallback
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    # Background auto-poster job
    job_queue = application.job_queue
    if job_queue and Config.CHANNEL_ID and Config.CHANNEL_ID not in [0, -1001234567890, 8370772224]:
        job_queue.run_repeating(auto_post, interval=Config.SCRAPE_INTERVAL, first=15)

    logger.info("🚀 1TamilVT-TG Bot starting in Polling Mode...")

    # Run
    if Config.WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=Config.PORT,
            webhook_url=Config.WEBHOOK_URL,
        )
    else:
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        try:
            asyncio.run(scraper.close())
        except Exception:
            pass
