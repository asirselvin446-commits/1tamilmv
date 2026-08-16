"""Main entry point for 1TamilVT-TG Telegram Bot."""
import asyncio
import html
import logging
import re
import sys
from datetime import datetime
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    InlineQueryHandler,
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
# Dynamic list of allowed users added via /allow command
dynamic_allowed_users: set = set()

# ── Helpers ──────────────────────────────────────────────────────────
def is_authorized(user_id: int) -> bool:
    """Check if the user has permission to use the bot."""
    authorized_users = Config.get_authorized_users().union(dynamic_allowed_users)
    if not authorized_users:
        return True  # Public mode if no restriction configured
    return user_id in authorized_users

def is_admin(user_id: int) -> bool:
    """Check if the user is the bot administrator."""
    return Config.ADMIN_ID != 0 and user_id == Config.ADMIN_ID

async def _send_access_denied(msg_or_query, user_id: int):
    """Send user-friendly access denied message showing their user ID."""
    denied_text = (
        f"⛔ <b>Access Denied:</b> This bot is set to private mode.\n\n"
        f"👤 <b>Your Telegram User ID:</b> <code>{user_id}</code>\n"
        f"<i>Share this ID with the bot admin to get access.</i>"
    )
    if hasattr(msg_or_query, "reply_text"):
        await msg_or_query.reply_text(denied_text, parse_mode=ParseMode.HTML)
    elif hasattr(msg_or_query, "answer"):
        await msg_or_query.answer(f"⛔ Access Denied (ID: {user_id}). Ask admin for access.", show_alert=True)

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
        if t_mag:
            lines.append(f"👉 <a href='{t_mag}'>🧲 <b>Tap to Open Magnet Link</b></a>")
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
        await _send_access_denied(update.message, user_id)
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

def _build_page_message(
    title_header: str,
    movies: List[Dict],
    page: int = 0,
    page_size: int = 5,
    page_type: str = "search"
) -> tuple:
    """Build a Rexxie-style paginated movie result message with interactive controls."""
    total = len(movies)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total)
    current_batch = movies[start_idx:end_idx]

    text = f"{title_header} (<b>{total}</b> found)\n"
    text += f"📄 <b>Page {page + 1} of {total_pages}</b>\n\n"

    for i, movie in enumerate(current_batch, start_idx + 1):
        safe_title = html.escape(movie["title"])
        safe_quality = html.escape(movie.get("quality", "Unknown"))
        is_official = movie.get("score", 0) >= 2
        badge = " ⭐️ <i>Official</i>" if is_official else ""
        text += (
            f"<b>{i}. {safe_title}</b>\n"
            f"   📊 Quality: <code>{safe_quality}</code>{badge}\n\n"
        )
    text += "👇 <i>Tap a button below to get download links:</i>"

    keyboard_buttons = []
    # Row 1: Item buttons for this page
    item_row = []
    for i in range(start_idx, end_idx):
        item_row.append(InlineKeyboardButton(f"📥 #{i + 1}", callback_data=f"get_{i}"))
    if item_row:
        keyboard_buttons.append(item_row)

    # Row 2: Navigation controls
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page_type}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page_type}_{page + 1}"))
    keyboard_buttons.append(nav_row)

    # Row 3: Close button
    keyboard_buttons.append([InlineKeyboardButton("❌ Close", callback_data="cmd_close")])

    return text, InlineKeyboardMarkup(keyboard_buttons)

async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and display latest movie releases with interactive pagination."""
    global last_scrape_time, last_movies

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        await _send_access_denied(update.message or update.callback_query, user_id)
        return

    msg_target = update.message or (update.callback_query.message if update.callback_query else None)
    chat_id = update.effective_chat.id if update.effective_chat else 0

    if not msg_target:
        return

    wait_msg = await msg_target.reply_text("⏳ Scraping latest releases from 1TamilMV... Please wait.")

    movies = await scraper.get_latest(limit=25)
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

    text, markup = _build_page_message(
        "🆕 <b>Latest Movies on 1TamilMV</b>",
        movies,
        page=0,
        page_size=5,
        page_type="latest"
    )

    await wait_msg.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=markup,
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search 1TamilMV by query with deep multi-page search and interactive pagination."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        await _send_access_denied(update.message, user_id)
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

    movies = await scraper.search(query, limit=50)
    if not movies:
        await wait_msg.edit_text(
            f"❌ No releases found for '<b>{safe_query}</b>'.\n"
            f"Tip: Try searching with a single key word (e.g. <code>/search Idhayam</code> or <code>/search Murali</code>).",
            parse_mode=ParseMode.HTML,
        )
        return

    if chat_id:
        movie_cache[chat_id] = movies

    text, markup = _build_page_message(
        f"🔍 <b>Search Results for '{safe_query}'</b>",
        movies,
        page=0,
        page_size=5,
        page_type="search"
    )

    await wait_msg.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=markup,
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
    elif data == "cmd_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return
    elif data == "noop":
        return
    elif data.startswith("page_"):
        parts = data.split("_")
        page_type = parts[1]
        target_page = int(parts[2])
        cached = movie_cache.get(chat_id, last_movies)
        if not cached:
            await query.message.reply_text("⚠️ Search results expired. Please run /search or /latest again.")
            return
        header = "🔍 <b>Search Results</b>" if page_type == "search" else "🆕 <b>Latest Movies on 1TamilMV</b>"
        text, markup = _build_page_message(header, cached, page=target_page, page_size=5, page_type=page_type)
        try:
            await query.edit_message_text(
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=markup,
            )
        except Exception as e:
            logger.debug(f"Pagination edit error: {e}")
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
        await _send_access_denied(update.message or update.callback_query, user_id)
        return

    msg_target = update.message or (update.callback_query.message if update.callback_query else None)
    if not msg_target:
        return

    uptime = datetime.now() - last_scrape_time if last_scrape_time != datetime.min else None
    uptime_str = f"{uptime.total_seconds():.0f}s ago" if uptime else "Never"

    active_mirror = html.escape(scraper.working_domain or Config.TAMILMV_URL or "N/A")
    channel_name = html.escape(Config.CHANNEL_USERNAME or "Not Set")
    all_auth = Config.get_authorized_users().union(dynamic_allowed_users)
    privacy_status = f"Private ({len(all_auth)} authorized)" if all_auth else "Public"

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

async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle direct plain text queries (Rexxie style) as movie searches."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        await _send_access_denied(update.message, user_id)
        return

    query = update.message.text.strip()
    if query.startswith("/"):
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0
    safe_query = html.escape(query)
    wait_msg = await update.message.reply_text(f"🔍 Searching 1TamilMV for '<b>{safe_query}</b>'...", parse_mode=ParseMode.HTML)

    movies = await scraper.search(query, limit=50)
    if not movies:
        await wait_msg.edit_text(
            f"❌ No releases found for '<b>{safe_query}</b>'.\n"
            f"Tip: Try searching with a single key word (e.g. <code>Idhayam</code>, <code>Murali</code>, or <code>Beast</code>).",
            parse_mode=ParseMode.HTML,
        )
        return

    if chat_id:
        movie_cache[chat_id] = movies

    text, markup = _build_page_message(
        f"🔍 <b>Search Results for '{safe_query}'</b>",
        movies,
        page=0,
        page_size=5,
        page_type="search"
    )

    await wait_msg.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=markup,
    )

async def inline_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries (@bot query) for quick movie search across Telegram."""
    if not update.inline_query:
        return

    query = update.inline_query.query.strip()
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_authorized(user_id):
        return

    if not query:
        return

    movies = await scraper.search(query, limit=15)
    results = []
    for idx, m in enumerate(movies):
        safe_title = html.escape(m["title"])
        safe_quality = html.escape(m.get("quality", "HD"))
        text = f"🎬 <b>{safe_title}</b>\n📊 Quality: <code>{safe_quality}</code>\n🔗 <a href='{m['url']}'>View on 1TamilMV</a>"
        buttons = [[InlineKeyboardButton("📥 Open on 1TamilMV", url=m["url"])]]
        results.append(
            InlineQueryResultArticle(
                id=str(idx),
                title=m["title"][:64],
                description=f"Quality: {m.get('quality', 'HD')}",
                input_message_content=InputTextMessageContent(text, parse_mode=ParseMode.HTML, disable_web_page_preview=False),
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        )

    try:
        await update.inline_query.answer(results, cache_time=300)
    except Exception as e:
        logger.debug(f"Inline query answer error: {e}")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Telegram user ID, chat ID, and authorization status."""
    if not update.message:
        return
    user = update.effective_user
    user_id = user.id if user else 0
    chat_id = update.effective_chat.id if update.effective_chat else 0
    auth = "Authorized ✅" if is_authorized(user_id) else "Unauthorized ❌"
    admin_badge = " (Admin 👑)" if is_admin(user_id) else ""
    text = (
        f"👤 <b>Your Telegram User ID:</b> <code>{user_id}</code>\n"
        f"💬 <b>Chat ID:</b> <code>{chat_id}</code>\n"
        f"🔒 <b>Status:</b> <code>{auth}</code>{admin_badge}\n\n"
        f"<i>Share your User ID with the bot admin to get access.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def allow_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: authorize a friend / user ID."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Only the bot admin can add authorized users.", parse_mode=ParseMode.HTML)
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/allow 123456789</code>\n"
            "Please provide a numeric Telegram User ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    target_id = int(context.args[0])
    dynamic_allowed_users.add(target_id)
    await update.message.reply_text(
        f"✅ User <code>{target_id}</code> is now authorized to use this bot!",
        parse_mode=ParseMode.HTML,
    )

async def revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: revoke a user ID."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Only the bot admin can revoke access.", parse_mode=ParseMode.HTML)
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/revoke 123456789</code>\n"
            "Please provide a numeric Telegram User ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    target_id = int(context.args[0])
    dynamic_allowed_users.discard(target_id)
    if target_id in Config.ALLOWED_USERS:
        Config.ALLOWED_USERS.remove(target_id)
    await update.message.reply_text(
        f"🚫 Access revoked for user <code>{target_id}</code>.",
        parse_mode=ParseMode.HTML,
    )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: list all authorized users."""
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Only the bot admin can view authorized users.", parse_mode=ParseMode.HTML)
        return

    all_auth = Config.get_authorized_users().union(dynamic_allowed_users)
    lines = [f"👥 <b>Authorized Users ({len(all_auth)} total):</b>"]
    if Config.ADMIN_ID:
        lines.append(f"👑 <b>Admin:</b> <code>{Config.ADMIN_ID}</code>")
    for uid in sorted(all_auth):
        if uid != Config.ADMIN_ID:
            lines.append(f"• <code>{uid}</code>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

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
    application.add_handler(CommandHandler(["id", "myid"], id_cmd))
    application.add_handler(CommandHandler(["allow", "add"], allow_user))
    application.add_handler(CommandHandler(["revoke", "remove"], revoke_user))
    application.add_handler(CommandHandler(["users", "allowed"], list_users))

    # Interactive buttons callback handler
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Inline query handler (@bot query)
    application.add_handler(InlineQueryHandler(inline_search))

    # Plain text movie search handler (Rexxie style)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search))

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
