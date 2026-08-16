"""Main entry point for 1TamilVT-TG Telegram Bot."""
import asyncio
import html
import logging
import re
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
def is_authorized(user_id: int) -> bool:
    """Check if the user has permission to use the bot."""
    authorized_users = Config.get_authorized_users()
    if not authorized_users:
        return True  # Public mode if no restriction configured
    return user_id in authorized_users

def _build_main_menu() -> InlineKeyboardMarkup:
    """Build persistent quick action buttons."""
    buttons = [
        [
            InlineKeyboardButton("🆕 Latest Movies", callback_data="cmd_latest"),
            InlineKeyboardButton("📊 Bot Status", callback_data="cmd_status"),
        ],
    ]
    if Config.CHANNEL_INVITE_LINK:
        buttons.append([InlineKeyboardButton("🔒 Private Channel", url=Config.CHANNEL_INVITE_LINK)])
    elif Config.CHANNEL_USERNAME:
        buttons.append([InlineKeyboardButton("📢 Channel", url=f"https://t.me/{Config.CHANNEL_USERNAME}")])
    return InlineKeyboardMarkup(buttons)

async def _send_topic_details(target, context: ContextTypes.DEFAULT_TYPE, topic_url: str, title: str = ""):
    """Fetch and send movie topic details including poster, magnet links, and mirrors."""
    wait_msg = await target.reply_text("⏳ Fetching magnet links & details... Please wait.")
    try:
        details = await scraper.get_topic_details(topic_url)
    except Exception as e:
        logger.error(f"Failed to fetch details for {topic_url}: {e}", exc_info=True)
        details = {"error": str(e)}

    if not details or "error" in details:
        err_text = html.escape(str(details.get("error", "Unknown error") if details else "Unknown error"))
        await wait_msg.edit_text(f"❌ Failed to fetch topic details: {err_text}")
        return

    movie_title = details.get("title") or title or "Movie Details"
    poster_url = details.get("poster")
    releases = details.get("releases", [])
    torrents = details.get("torrents", [])
    direct_links = details.get("direct_links", [])

    safe_title = html.escape(movie_title)
    safe_topic_url = html.escape(topic_url)

    total_releases = len(releases) if releases else len(torrents)
    if total_releases > 0:
        header_text = (
            f"🎬 <b>{safe_title}</b>\n\n"
            f"📦 <b>Releases:</b> <code>{total_releases} available</code>\n"
            f"🔗 <a href='{safe_topic_url}'>View on 1TamilMV</a>\n\n"
            f"👇 <i>Tap any button below to start downloading:</i>"
        )
    else:
        header_text = (
            f"🎬 <b>{safe_title}</b>\n\n"
            f"📦 <b>Releases:</b> <code>0 direct torrents</code>\n"
            f"🔗 <a href='{safe_topic_url}'>View on 1TamilMV</a>\n\n"
            f"⚠️ <i>This specific forum post contains no direct torrent/magnet attachments. Check other search results (e.g. #2, #3) for complete torrent releases of this movie.</i>"
        )

    buttons = []
    # Add direct tap-to-download buttons for each release
    for i, r in enumerate(releases[:6], 1):
        row = []
        size_str = f" ({r['size']})" if r.get('size') and r['size'] != 'N/A' else ""
        if r.get("torrent_url"):
            row.append(InlineKeyboardButton(f"📥 Download #{i}{size_str}", url=r["torrent_url"]))
        if r.get("direct_url"):
            row.append(InlineKeyboardButton(f"⚡ Fast #{i}", url=r["direct_url"]))
        if row:
            buttons.append(row)

    buttons.append([InlineKeyboardButton("🌐 Open on 1TamilMV", url=topic_url)])
    reply_markup = InlineKeyboardMarkup(buttons)

    # 1. Send Header (with poster photo if available)
    header_sent = False
    if poster_url:
        try:
            await target.reply_photo(
                photo=poster_url,
                caption=header_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            header_sent = True
        except Exception as e:
            logger.debug(f"Could not send poster photo directly: {e}")

    if not header_sent:
        try:
            await target.reply_text(
                header_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
                reply_markup=reply_markup,
            )
            header_sent = True
        except Exception as e:
            logger.warning(f"Failed to send HTML header, falling back to plain text: {e}")
            plain_header = f"🎬 {movie_title}\n\n📦 Releases: {total_releases} available\n🔗 {topic_url}"
            try:
                await target.reply_text(
                    plain_header,
                    disable_web_page_preview=False,
                    reply_markup=reply_markup,
                )
            except Exception as e2:
                logger.error(f"Failed to send fallback header: {e2}")

    # Delete waiting message after header dispatch
    try:
        await wait_msg.delete()
    except Exception:
        pass

    # 2. Build release and mirror blocks with tap-to-download links
    release_blocks = []
    items_to_display = releases if releases else torrents
    for i, item in enumerate(items_to_display, 1):
        t_name = html.escape(item.get("name", f"Release #{i}"))
        t_size = html.escape(item.get("size", "N/A"))
        t_mag = html.escape(item.get("magnet", ""))
        t_torrent_url = html.escape(item.get("torrent_url", ""))
        t_direct_url = html.escape(item.get("direct_url", ""))

        lines = [
            f"🎬 <b>Release #{i}: {t_name}</b>",
            f"📦 <b>Size:</b> <code>{t_size}</code>",
        ]
        if t_torrent_url:
            lines.append(f"👉 <a href='{t_torrent_url}'>📥 <b>Tap to Download (.torrent file)</b></a>")
        if t_direct_url:
            lines.append(f"👉 <a href='{t_direct_url}'>⚡ <b>Tap for Fast Cloud Link</b></a>")

        release_blocks.append("\n".join(lines))

    mirror_blocks = []
    if direct_links and not releases:
        lines = ["📥 <b>Download Mirrors & Torrent Files:</b>"]
        for j, d in enumerate(direct_links[:10], 1):
            d_name = html.escape(d.get("name", f"Mirror #{j}"))
            d_url = html.escape(d.get("url", ""))
            lines.append(f"• <a href='{d_url}'>{d_name}</a>")
        mirror_blocks.append("\n".join(lines))

    # 3. Group blocks into messages under 3800 chars without breaking tags
    grouped_messages = []
    current_msg = ""
    for block in release_blocks + mirror_blocks:
        if len(current_msg) + len(block) + 2 > 3800:
            if current_msg:
                grouped_messages.append(current_msg.strip())
            current_msg = block + "\n\n"
        else:
            current_msg += block + "\n\n"
    if current_msg.strip():
        grouped_messages.append(current_msg.strip())

    # 4. Dispatch release messages
    for msg in grouped_messages:
        try:
            await target.reply_text(
                msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Error sending HTML chunk, retrying as plain text: {e}")
            plain_text = re.sub(r"<[^>]+>", "", msg)
            try:
                await target.reply_text(
                    plain_text,
                    disable_web_page_preview=True,
                )
            except Exception as e2:
                logger.error(f"Failed to send plain text message: {e2}")

# ── Handlers ─────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message and guide."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        await update.message.reply_text(
            "⛔ <b>Access Denied:</b> This bot is set to private mode for authorized users only.",
            parse_mode=ParseMode.HTML,
        )
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

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        if update.message:
            await update.message.reply_text("⛔ <b>Access Denied:</b> This bot is set to private mode.", parse_mode=ParseMode.HTML)
        elif update.callback_query:
            await update.callback_query.answer("⛔ Access Denied: Private mode.", show_alert=True)
        return

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
        safe_title = html.escape(movie["title"])
        safe_quality = html.escape(movie["quality"])
        text += (
            f"<b>{i}. {safe_title}</b>\n"
            f"   📊 Quality: <code>{safe_quality}</code>\n\n"
        )
    text += "👇 <i>Tap a button below to get download links & details:</i>"

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

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ <b>Access Denied:</b> This bot is set to private mode.", parse_mode=ParseMode.HTML)
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
    safe_query = html.escape(query)
    wait_msg = await update.message.reply_text(f"🔍 Searching 1TamilMV for '<b>{safe_query}</b>'...", parse_mode=ParseMode.HTML)

    movies = await scraper.search(query, limit=10)
    if not movies:
        await wait_msg.edit_text(
            f"❌ No releases found for '<b>{safe_query}</b>'.\n"
            f"Tip: Try searching with a single key word (e.g. <code>/search Idhayam</code> or <code>/search Murali</code>).",
            parse_mode=ParseMode.HTML,
        )
        return

    if chat_id:
        movie_cache[chat_id] = movies

    text = f"🔍 <b>Search Results for '{safe_query}'</b> ({len(movies)} found)\n\n"
    for i, movie in enumerate(movies, 1):
        safe_title = html.escape(movie["title"])
        safe_quality = html.escape(movie["quality"])
        text += (
            f"<b>{i}. {safe_title}</b>\n"
            f"   📊 Quality: <code>{safe_quality}</code>\n\n"
        )
    text += "👇 <i>Tap a button below to get download links:</i>"

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

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        await query.answer("⛔ Access Denied: This bot is in private mode.", show_alert=True)
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
            logger.exception(f"Callback error processing {data}: {e}")
            try:
                await query.message.reply_text("❌ Failed to load movie details. Please try again.")
            except Exception:
                pass

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot and scraper health status."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        if update.message:
            await update.message.reply_text("⛔ <b>Access Denied:</b> This bot is set to private mode.", parse_mode=ParseMode.HTML)
        elif update.callback_query:
            await update.callback_query.answer("⛔ Access Denied: Private mode.", show_alert=True)
        return

    msg_target = update.message or (update.callback_query.message if update.callback_query else None)
    if not msg_target:
        return

    uptime = datetime.now() - last_scrape_time if last_scrape_time != datetime.min else None
    uptime_str = f"{uptime.total_seconds():.0f}s ago" if uptime else "Never"

    active_mirror = html.escape(scraper.working_domain or Config.TAMILMV_URL or "N/A")
    channel_name = html.escape(Config.CHANNEL_USERNAME or "Not Set")
    auth_users = Config.get_authorized_users()
    privacy_status = f"Private ({len(auth_users)} authorized)" if auth_users else "Public"

    text = (
        f"🤖 <b>1TamilVT-TG Bot Status</b>\n\n"
        f"🌐 <b>Active Mirror:</b> <code>{active_mirror}</code>\n"
        f"🔒 <b>Privacy Mode:</b> <code>{privacy_status}</code>\n"
        f"🕐 <b>Last Scrape:</b> {uptime_str}\n"
        f"📦 <b>Cached Releases:</b> {len(last_movies)}\n"
        f"⏱️ <b>Auto-Scrape Interval:</b> {Config.SCRAPE_INTERVAL}s\n"
        f"📢 <b>Target Channel:</b> @{channel_name}\n"
        f"🟢 <b>Status:</b> Operational & Ready"
    )
    await msg_target.reply_text(text, parse_mode=ParseMode.HTML)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unknown commands."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        return

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

        safe_title = html.escape(title)
        safe_quality = html.escape(movie["quality"])
        safe_url = html.escape(url)

        caption = (
            f"🎬 <b>{safe_title}</b>\n"
            f"📊 Quality: <code>{safe_quality}</code>\n"
        )
        if torrents:
            caption += f"📦 Releases: <code>{len(torrents)} versions</code>\n"
        caption += (
            f"🔗 <a href='{safe_url}'>Download from 1TamilMV</a>\n\n"
            f"#TamilMV #Kollywood #Movies"
        )

        buttons = []
        releases = details.get("releases", [])
        if releases:
            for i, r in enumerate(releases[:4], 1):
                row = []
                size_str = f" ({r['size']})" if r.get('size') and r['size'] != 'N/A' else ""
                if r.get("torrent_url"):
                    row.append(InlineKeyboardButton(f"📥 Download #{i}{size_str}", url=r["torrent_url"]))
                if r.get("direct_url"):
                    row.append(InlineKeyboardButton(f"⚡ Fast #{i}", url=r["direct_url"]))
                if row:
                    buttons.append(row)

        buttons.append([InlineKeyboardButton("🌐 Open on 1TamilMV", url=url)])
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

def _start_health_server() -> None:
    """Lightweight background HTTP server for Render/Koyeb Web Service health checks."""
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"1TamilVT-TG Bot is Live and Healthy!\n")

        def log_message(self, format, *args):
            return  # Suppress health check logs

    def run_server():
        try:
            port = int(Config.PORT or 8080)
            server = HTTPServer(("0.0.0.0", port), HealthHandler)
            server.serve_forever()
        except Exception as e:
            logger.debug(f"Health server: {e}")

    threading.Thread(target=run_server, daemon=True).start()

# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    """Start the bot."""
    Config.validate()
    _start_health_server()

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
