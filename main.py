import os
import re
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")

# Buttons per row
BUTTONS_PER_ROW = 4

# Request settings
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Mobile Safari/537.36"
    )
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def make_rows(buttons, per_row=BUTTONS_PER_ROW):
    return [
        buttons[i:i + per_row]
        for i in range(0, len(buttons), per_row)
    ]


def classify_episode(title: str):
    """
    Detect normal episodes, OVA and Special from the episode title.

    Examples:
      Episode 1       -> Episodes
      Episode 12      -> Episodes
      OVA 1           -> OVA
      Special 1       -> Specials
      Special         -> Specials
    """
    t = title.lower().strip()

    if re.search(r"\bova\b", t):
        return "ova"

    if re.search(r"\bspecials?\b", t):
        return "special"

    return "episodes"


def episode_sort_key(item):
    title = item["title"]

    # Extract first number from title.
    match = re.search(r"(\d+(?:\.\d+)?)", title)

    if match:
        try:
            return (0, float(match.group(1)), title.lower())
        except ValueError:
            pass

    return (1, 0, title.lower())


# ============================================================
# PAGE PARSER
# ============================================================

def parse_anime_page(html: str, base_url: str):
    """
    Parse the exact episode structure found in the supplied HTML:

      .td-post-content
        .episode
          .episode-title
          .language
          .btn-group
            <a ...>

    Only the episode listing is extracted.
    Download/watch URLs are NOT opened or followed.
    """

    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(".td-post-content")

    if not content:
        # Fallback for pages using the episode class elsewhere.
        content = soup

    result = {
        "title": "",
        "episodes": [],
        "ova": [],
        "special": [],
    }

    # Try to get the post title.
    title_node = soup.select_one("h1.entry-title, h1.td-block-title, h1")
    if title_node:
        result["title"] = clean_text(title_node.get_text(" ", strip=True))

    # Exact structure used by the uploaded page.
    episode_nodes = content.select(".episode")

    for node in episode_nodes:
        title_node = node.select_one(".episode-title")

        if not title_node:
            continue

        title = clean_text(title_node.get_text(" ", strip=True))

        if not title:
            continue

        language_node = node.select_one(".language")
        language = (
            clean_text(language_node.get_text(" ", strip=True))
            if language_node
            else ""
        )

        links = []

        # We only collect the links; we do not visit them.
        for a in node.select(".btn-group a[href]"):
            href = a.get("href", "").strip()

            if not href:
                continue

            label = clean_text(a.get_text(" ", strip=True))

            links.append({
                "label": label,
                "url": urljoin(base_url, href),
            })

        item = {
            "title": title,
            "language": language,
            "links": links,
        }

        category = classify_episode(title)
        result[category].append(item)

    result["episodes"].sort(key=episode_sort_key)
    result["ova"].sort(key=episode_sort_key)
    result["special"].sort(key=episode_sort_key)

    return result


# ============================================================
# TELEGRAM UI
# ============================================================

def build_episode_keyboard(parsed):
    rows = []

    # ---------------- NORMAL EPISODES ----------------
    if parsed["episodes"]:
        rows.append([
            InlineKeyboardButton("📺  EPISODES", callback_data="noop")
        ])

        buttons = []

        for ep in parsed["episodes"]:
            # Episode button only.
            # The URL is intentionally not opened by the bot.
            #
            # callback_data is kept small because Telegram has
            # a 64-byte callback-data limit.
            #
            # We use an index instead of putting the URL in callback_data.
            index = parsed["episodes"].index(ep)

            buttons.append(
                InlineKeyboardButton(
                    ep["title"],
                    callback_data=f"ep:e:{index}"
                )
            )

        rows.extend(make_rows(buttons))

    # ---------------- OVA ----------------
    if parsed["ova"]:
        rows.append([
            InlineKeyboardButton("🎬  OVA", callback_data="noop")
        ])

        buttons = []

        for index, ep in enumerate(parsed["ova"]):
            buttons.append(
                InlineKeyboardButton(
                    ep["title"],
                    callback_data=f"ep:o:{index}"
                )
            )

        rows.extend(make_rows(buttons))

    # ---------------- SPECIALS ----------------
    if parsed["special"]:
        rows.append([
            InlineKeyboardButton("⭐  SPECIALS", callback_data="noop")
        ])

        buttons = []

        for index, ep in enumerate(parsed["special"]):
            buttons.append(
                InlineKeyboardButton(
                    ep["title"],
                    callback_data=f"ep:s:{index}"
                )
            )

        rows.extend(make_rows(buttons))

    return InlineKeyboardMarkup(rows)


# ============================================================
# COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me an anime page URL.\n\n"
        "I will read the episode list and create a clean "
        "Episode / OVA / Special button layout."
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    # Basic URL validation
    if not re.match(r"^https?://", url, re.IGNORECASE):
        await update.message.reply_text(
            "⚠️ Please send a valid http/https URL."
        )
        return

    status = await update.message.reply_text(
        "🔎 Reading the page and building the episode list..."
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()

        if "text/html" not in content_type and "<html" not in response.text.lower():
            await status.edit_text(
                "⚠️ The URL did not return an HTML page."
            )
            return

        parsed = parse_anime_page(response.text, response.url)

        total = (
            len(parsed["episodes"])
            + len(parsed["ova"])
            + len(parsed["special"])
        )

        if total == 0:
            await status.edit_text(
                "⚠️ No episode blocks were found on this page.\n\n"
                "The page may use a different structure or may be "
                "protected by Cloudflare/CAPTCHA."
            )
            return

        keyboard = build_episode_keyboard(parsed)

        page_title = parsed["title"] or "Anime"

        message = (
            f"🎬 <b>{page_title}</b>\n\n"
            f"📌 Episodes found: <b>{total}</b>\n"
            "👇 Select an episode:"
        )

        await status.edit_text(
            message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except requests.exceptions.Timeout:
        await status.edit_text(
            "⚠️ The website took too long to respond."
        )

    except requests.exceptions.RequestException as e:
        logger.warning("Request failed: %s", e)

        await status.edit_text(
            "⚠️ I could not access this page.\n\n"
            "If the website shows Cloudflare/CAPTCHA, the bot "
            "does not bypass that protection."
        )

    except Exception:
        logger.exception("Parser error")

        await status.edit_text(
            "⚠️ Something went wrong while reading the page."
        )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    if data == "noop":
        return

    # In this first version, buttons are only for the episode list.
    # No download/watch action is performed yet.
    if data.startswith("ep:"):
        await query.answer(
            "Episode selected. Action will be added in the next version.",
            show_alert=False,
        )


# ============================================================
# MAIN
# ============================================================

def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN is not set. Add your Telegram bot token "
            "as the BOT_TOKEN environment variable."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url)
    )
    app.add_handler(
        __import__("telegram.ext", fromlist=["CallbackQueryHandler"])
        .CallbackQueryHandler(button_handler)
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
