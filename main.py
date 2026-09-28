import os
import re
import html
import requests
from bs4 import BeautifulSoup

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 20


# =========================================================
# HTTP
# =========================================================

def fetch_page(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        return response

    except requests.RequestException as e:
        print("REQUEST ERROR:", e)
        return None


# =========================================================
# CLOUDFLARE DETECTION
# =========================================================

def is_cloudflare_page(response):
    if response is None:
        return False

    text = response.text.lower()

    # Strong indicators only.
    strong_indicators = [
        "cf-chl-challenge",
        "challenge-platform",
        "just a moment...",
        "verify you are human",
        "checking your browser",
        "/cdn-cgi/challenge-platform/",
    ]

    for indicator in strong_indicators:
        if indicator in text:
            return True

    # HTTP 403/503 + Cloudflare markers
    if response.status_code in (403, 503):
        if "cloudflare" in text or "cf-ray" in response.headers:
            return True

    return False


# =========================================================
# TITLE
# =========================================================

def get_title(soup):
    title = soup.title

    if title:
        text = title.get_text(" ", strip=True)

        if text:
            return text

    h1 = soup.find("h1")

    if h1:
        return h1.get_text(" ", strip=True)

    return "Anime"


# =========================================================
# SEASON DETECTION
# =========================================================

def detect_season(text):
    if not text:
        return 1

    patterns = [
        r"\bseason[\s\-]*(\d+)\b",
        r"\bs(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass

    return 1


# =========================================================
# EPISODE DETECTION
# =========================================================

def detect_episode(text):
    if not text:
        return None

    patterns = [
        r"\bepisode[\s\-]*(\d+)\b",
        r"\bep[\s\-]*(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass

    return None


# =========================================================
# MAIN ANIME PAGE PARSER
# IMPORTANT:
# This function DOES NOT open download1.php
# =========================================================

def parse_anime_page(page_url, page_html):

    soup = BeautifulSoup(page_html, "lxml")

    title = get_title(soup)

    # Detect season from page URL + title + page text
    season_source = (
        str(page_url)
        + " "
        + str(title)
    )

    season = detect_season(season_source)

    episodes = []

    # Exact structure from the supplied source:
    #
    # <div class="episode">
    #   <span class="episode-title">Episode 1</span>
    #   ...
    #   <a class="download-480p" href="...download1.php?...">
    #
    episode_blocks = soup.select("div.episode")

    print("EPISODE BLOCKS FOUND:", len(episode_blocks))

    for block in episode_blocks:

        title_element = block.select_one(".episode-title")

        if not title_element:
            continue

        episode_title = title_element.get_text(" ", strip=True)

        episode_number = detect_episode(episode_title)

        if episode_number is None:
            episode_number = detect_episode(
                block.get_text(" ", strip=True)
            )

        if episode_number is None:
            continue

        downloads = []

        # IMPORTANT:
        # We only READ the href.
        # We DO NOT request/open it here.
        for link in block.select("a[href]"):

            href = link.get("href", "").strip()

            if not href:
                continue

            href = html.unescape(href)

            # Only save actual download1.php links
            if "download1.php" in href:

                quality = link.get_text(
                    " ",
                    strip=True
                )

                downloads.append({
                    "quality": quality,
                    "url": href,
                })

        # Optional watch-online URL
        watch_link = None

        watch_element = block.select_one(
            "a.watch-online[href]"
        )

        if watch_element:
            watch_link = html.unescape(
                watch_element.get("href", "").strip()
            )

        if downloads:

            episodes.append({
                "episode": episode_number,
                "title": episode_title,
                "downloads": downloads,
                "watch": watch_link,
            })

    # Sort episodes
    episodes.sort(
        key=lambda x: x["episode"]
    )

    return {
        "title": title,
        "season": season,
        "episodes": episodes,
    }


# =========================================================
# GDFlix EXTRACTION
# =========================================================

def find_gdflix_links(page_html):

    soup = BeautifulSoup(page_html, "lxml")

    results = []

    # Exact server structure seen in the supplied source:
    #
    # <a class="server-btn"
    #    href="https://new4.gdflix.io/file/..."
    #    data-label="GDFlix">
    #
    for link in soup.select("a.server-btn[href]"):

        href = html.unescape(
            link.get("href", "").strip()
        )

        label = link.get(
            "data-label",
            ""
        ).strip()

        text = link.get_text(
            " ",
            strip=True
        )

        combined = (
            label
            + " "
            + text
            + " "
            + href
        ).lower()

        if "gdflix" in combined:

            if href not in results:
                results.append(href)

    # Fallback:
    # Search normal links if server-btn wasn't used.
    if not results:

        for link in soup.select("a[href]"):

            href = html.unescape(
                link.get("href", "").strip()
            )

            text = link.get_text(
                " ",
                strip=True
            )

            combined = (
                text
                + " "
                + href
            ).lower()

            if "gdflix" in combined:

                if href.startswith("http"):
                    if href not in results:
                        results.append(href)

    return results


# =========================================================
# TELEGRAM /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = (
        "👋 Send me the main anime page URL.\n\n"
        "Example:\n"
        "https://hindianimeszone.com/..."
    )

    await update.message.reply_text(message)


# =========================================================
# HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Send the main anime page URL.\n\n"
        "The bot will show Season and Episode buttons."
    )


# =========================================================
# RECEIVE MAIN ANIME URL
# =========================================================

async def receive_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    url = update.message.text.strip()

    if not url.startswith(("http://", "https://")):

        await update.message.reply_text(
            "❌ Please send a valid HTTP/HTTPS URL."
        )

        return

    # IMPORTANT:
    # Only main anime page is fetched here.
    # NO download1.php is requested here.

    status = await update.message.reply_text(
        "🔎 Reading anime page..."
    )

    response = fetch_page(url)

    if response is None:

        await status.edit_text(
            "❌ Could not open the page."
        )

        return

    if is_cloudflare_page(response):

        await status.edit_text(
            "⚠️ Cloudflare/CAPTCHA detected on the "
            "main anime page.\n\n"
            "Bot cannot bypass the verification."
        )

        return

    data = parse_anime_page(
        url,
        response.text
    )

    if not data["episodes"]:

        await status.edit_text(
            "❌ No episode blocks were found.\n\n"
            "The page structure may have changed."
        )

        return

    # Store data for this Telegram user
    context.user_data["anime"] = data
    context.user_data["source_url"] = url

    # Show season button
    keyboard = [
        [
            InlineKeyboardButton(
                f"📺 Season {data['season']}",
                callback_data=f"season:{data['season']}"
            )
        ]
    ]

    await status.edit_text(
        f"🎬 {data['title']}\n\n"
        "Select a season:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# SHOW EPISODES
# =========================================================

async def show_season(
    query,
    context
):

    data = context.user_data.get("anime")

    if not data:
        await query.edit_message_text(
            "❌ Session expired. Send the anime URL again."
        )
        return

    episodes = data["episodes"]

    keyboard = []

    row = []

    for item in episodes:

        number = item["episode"]

        row.append(
            InlineKeyboardButton(
                f"EP {number}",
                callback_data=f"episode:{number}"
            )
        )

        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(
            "🏠 Home",
            callback_data="home"
        )
    ])

    await query.edit_message_text(
        f"📺 Season {data['season']}\n\n"
        "Select an episode:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# PROCESS EPISODE
# =========================================================

async def process_episode(
    query,
    context,
    episode_number
):

    data = context.user_data.get("anime")

    if not data:
        await query.edit_message_text(
            "❌ Session expired. Send the anime URL again."
        )
        return

    episode = None

    for item in data["episodes"]:

        if item["episode"] == episode_number:
            episode = item
            break

    if not episode:

        await query.edit_message_text(
            "❌ Episode not found."
        )

        return

    await query.edit_message_text(
        f"⏳ Processing Episode {episode_number}...\n\n"
        "Checking download pages..."
    )

    gdflix_links = []

    # IMPORTANT:
    # download1.php is opened ONLY NOW,
    # after user clicked an episode.

    for item in episode["downloads"]:

        download_url = item["url"]

        print(
            "Opening download page:",
            download_url
        )

        response = fetch_page(
            download_url
        )

        if response is None:
            continue

        if is_cloudflare_page(response):

            await query.edit_message_text(
                "⚠️ Cloudflare/CAPTCHA detected.\n\n"
                "The download page requires verification, "
                "so the bot stopped here.\n\n"
                f"Episode: {episode_number}\n"
                f"Quality: {item['quality']}"
            )

            return

        found = find_gdflix_links(
            response.text
        )

        for link in found:

            if link not in gdflix_links:
                gdflix_links.append(link)

    # =====================================================
    # RESULT
    # =====================================================

    if not gdflix_links:

        await query.edit_message_text(
            f"❌ No GDFlix link found for "
            f"Episode {episode_number}."
        )

        return

    # We send GDFlix links directly.
    # No quality-selection buttons.

    keyboard = []

    for index, link in enumerate(
        gdflix_links,
        start=1
    ):

        keyboard.append([
            InlineKeyboardButton(
                f"🔗 GDFlix {index}",
                url=link
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Episodes",
            callback_data=f"season:{data['season']}"
        )
    ])

    await query.edit_message_text(
        f"✅ Episode {episode_number}\n\n"
        "GDFlix link found:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    # HOME
    if data == "home":

        anime = context.user_data.get("anime")

        if not anime:

            await query.edit_message_text(
                "Send the anime page URL again."
            )

            return

        keyboard = [[
            InlineKeyboardButton(
                f"📺 Season {anime['season']}",
                callback_data=f"season:{anime['season']}"
            )
        ]]

        await query.edit_message_text(
            f"🎬 {anime['title']}\n\n"
            "Select a season:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # SEASON
    if data.startswith("season:"):

        await show_season(
            query,
            context
        )

        return

    # EPISODE
    if data.startswith("episode:"):

        try:
            episode_number = int(
                data.split(":", 1)[1]
            )

        except ValueError:

            await query.edit_message_text(
                "❌ Invalid episode."
            )

            return

        await process_episode(
            query,
            context,
            episode_number
        )

        return


# =========================================================
# MAIN
# =========================================================

def main():

    print("Starting Telegram bot...")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_url
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback
        )
    )

    print("Bot is running.")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
