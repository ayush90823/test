import os
import re
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_page(url: str, timeout: int = 25):
    """Fetch a page without attempting to bypass Cloudflare/CAPTCHA."""
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
        allow_redirects=True,
    )
    return response


def is_cloudflare_challenge(response) -> bool:
    """
    Detect an actual Cloudflare/challenge page.

    Normal Cloudflare scripts such as Rocket Loader and Insights are NOT
    treated as a challenge.
    """
    text = response.text.lower()
    final_url = response.url.lower()

    strong_markers = [
        "cf-chl-challenge",
        "challenge-platform",
        "cf-chl-widget",
        "turnstile-challenge",
        "just a moment...",
        "verify you are human",
        "checking your browser",
        "/cdn-cgi/challenge-platform/",
    ]

    if any(marker in text or marker in final_url for marker in strong_markers):
        return True

    if response.status_code in (403, 503):
        headers = {k.lower(): v.lower() for k, v in response.headers.items()}
        if "cf-ray" in headers or "cf-mitigated" in headers:
            return True

    return False


def extract_season(page_url: str, title: str) -> str:
    source = f"{page_url} {title}"

    match = re.search(r"season[\s\-_]*(\d+)", source, re.IGNORECASE)
    if match:
        return f"Season {match.group(1)}"

    match = re.search(r"\bs(\d+)\b", source, re.IGNORECASE)
    if match:
        return f"Season {match.group(1)}"

    return "Season"


def episode_number(text: str) -> int:
    match = re.search(r"(\d+)", text or "")
    return int(match.group(1)) if match else 999999


def parse_anime_page(page_url: str, html: str):
    soup = BeautifulSoup(html, "lxml")

    # This is only a promotional popup. It is not needed for parsing.
    popup = soup.select_one("#tg-popup-root")
    if popup:
        popup.decompose()

    title = ""
    if soup.title:
        title = soup.title.get_text(" ", strip=True)

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(" ", strip=True)

    season = extract_season(page_url, title)

    episodes = []

    for block in soup.select("div.episode"):
        title_el = block.select_one(".episode-title")
        ep_title = title_el.get_text(" ", strip=True) if title_el else ""

        if not ep_title:
            continue

        download_links = []
        watch_link = None

        for a in block.select("a[href]"):
            href = urljoin(page_url, a.get("href", "").strip())
            if not href:
                continue

            if "download1.php" in href.lower():
                if href not in download_links:
                    download_links.append(href)

            if "playonline.php" in href.lower():
                watch_link = href

        if download_links:
            episodes.append(
                {
                    "title": ep_title,
                    "number": episode_number(ep_title),
                    "download_links": download_links,
                    "watch_link": watch_link,
                }
            )

    episodes.sort(key=lambda x: x["number"])

    return {
        "title": title or "Anime",
        "season": season,
        "episodes": episodes,
        "url": page_url,
    }


def find_gdflix_links(html: str, base_url: str):
    soup = BeautifulSoup(html, "lxml")
    found = []

    # First check normal server buttons.
    for a in soup.select("a.server-btn[href]"):
        href = urljoin(base_url, a.get("href", "").strip())
        label = (
            a.get("data-label", "")
            + " "
            + a.get_text(" ", strip=True)
            + " "
            + href
        ).lower()

        if "gdflix" in label and href not in found:
            found.append(href)

    # Fallback: search all links.
    if not found:
        for a in soup.select("a[href]"):
            href = urljoin(base_url, a.get("href", "").strip())
            label = (a.get_text(" ", strip=True) + " " + href).lower()

            if "gdflix" in label and href not in found:
                found.append(href)

    return found


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "Anime page ka URL bhejo.\n\n"
        "Bot pehle sirf anime page parse karega.\n"
        "Episode select karne ke baad hi us episode ke download pages check honge."
    )


async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if not re.match(r"^https?://", url, re.IGNORECASE):
        await update.message.reply_text(
            "⚠️ Valid http/https URL bhejo."
        )
        return

    status = await update.message.reply_text(
        "🔎 Anime page read kar raha hoon..."
    )

    try:
        response = fetch_page(url)

        logger.info(
            "Main page status=%s final_url=%s",
            response.status_code,
            response.url,
        )

        # IMPORTANT:
        # Main page par normal Cloudflare Rocket Loader/Insights scripts
        # ko challenge nahi maana ja raha. Sirf actual challenge page
        # detect hone par stop karenge.
        if is_cloudflare_challenge(response):
            await status.edit_text(
                "⚠️ Main anime page par Cloudflare/CAPTCHA challenge mila.\n\n"
                "Bot protected challenge ko bypass nahi karta, isliye yahin ruk gaya."
            )
            return

        if response.status_code != 200:
            await status.edit_text(
                f"⚠️ Main page open nahi hua.\nHTTP status: {response.status_code}"
            )
            return

        anime = parse_anime_page(url, response.text)

        logger.info(
            "Parsed title=%r season=%r episodes=%d",
            anime["title"],
            anime["season"],
            len(anime["episodes"]),
        )

        if not anime["episodes"]:
            await status.edit_text(
                "⚠️ Page mil gaya, lekin episode blocks nahi mile.\n\n"
                "Expected format: div.episode + .episode-title + download1.php links."
            )
            return

        context.user_data["anime"] = anime

        keyboard = [
            [
                InlineKeyboardButton(
                    anime["season"],
                    callback_data="season:0",
                )
            ]
        ]

        await status.edit_text(
            f"📺 {anime['title']}\n\n"
            f"Season detected: {anime['season']}\n"
            f"Episodes found: {len(anime['episodes'])}\n\n"
            "Season select karo:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except requests.RequestException as e:
        logger.exception("Main page request failed")
        await status.edit_text(
            f"❌ Main page request failed.\n{type(e).__name__}: {e}"
        )
    except Exception as e:
        logger.exception("Unexpected error")
        await status.edit_text(
            f"❌ Error: {type(e).__name__}: {e}"
        )


async def show_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    anime = context.user_data.get("anime")

    if not anime:
        await query.edit_message_text(
            "⚠️ Session data nahi mila. /start karke dobara URL bhejo."
        )
        return

    episodes = anime["episodes"]

    keyboard = []
    row = []

    for index, ep in enumerate(episodes):
        row.append(
            InlineKeyboardButton(
                ep["title"],
                callback_data=f"episode:{index}",
            )
        )

        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append(
        [InlineKeyboardButton("⬅️ Back", callback_data="home")]
    )

    await query.edit_message_text(
        f"📺 {anime['title']}\n"
        f"📂 {anime['season']}\n\n"
        "Episode select karo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def process_episode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    index: int,
):
    query = update.callback_query
    await query.answer()

    anime = context.user_data.get("anime")

    if not anime:
        await query.edit_message_text(
            "⚠️ Session data nahi mila. /start karke dobara URL bhejo."
        )
        return

    episodes = anime["episodes"]

    if index < 0 or index >= len(episodes):
        await query.edit_message_text("⚠️ Invalid episode.")
        return

    ep = episodes[index]

    await query.edit_message_text(
        f"⏳ {ep['title']} ke download pages check kar raha hoon...\n\n"
        "Quality buttons nahi dikhaye jayenge."
    )

    gdflix_links = []

    try:
        # IMPORTANT:
        # download1.php ko sirf episode button click ke baad request kiya jata hai.
        for number, download_url in enumerate(ep["download_links"], start=1):
            logger.info(
                "Checking episode=%s download_link=%d",
                ep["title"],
                number,
            )

            response = fetch_page(download_url)

            logger.info(
                "Download page status=%s final_url=%s",
                response.status_code,
                response.url,
            )

            if is_cloudflare_challenge(response):
                await query.edit_message_text(
                    "⚠️ Download page par Cloudflare/CAPTCHA challenge mila.\n\n"
                    "Bot challenge ko bypass nahi karta, isliye yahin ruk gaya.\n\n"
                    f"Stopped URL:\n{download_url}"
                )
                return

            if response.status_code != 200:
                continue

            links = find_gdflix_links(response.text, response.url)

            for link in links:
                if link not in gdflix_links:
                    gdflix_links.append(link)

        if not gdflix_links:
            await query.edit_message_text(
                f"⚠️ {ep['title']} ke download pages check hue, "
                "lekin GDFlix link nahi mila."
            )
            return

        buttons = []
        for i, link in enumerate(gdflix_links, start=1):
            buttons.append(
                [InlineKeyboardButton(f"GDFlix Link {i}", url=link)]
            )

        buttons.append(
            [InlineKeyboardButton("⬅️ Episodes", callback_data="season:0")]
        )

        await query.edit_message_text(
            f"✅ {ep['title']} ka GDFlix link mil gaya.\n\n"
            "Neeche link open karo:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    except requests.RequestException as e:
        logger.exception("Download page request failed")
        await query.edit_message_text(
            f"❌ Download page request failed.\n"
            f"{type(e).__name__}: {e}"
        )
    except Exception as e:
        logger.exception("Unexpected episode error")
        await query.edit_message_text(
            f"❌ Error: {type(e).__name__}: {e}"
        )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""

    if data == "home":
        await show_season(update, context)
        return

    if data.startswith("season:"):
        await show_season(update, context)
        return

    if data.startswith("episode:"):
        try:
            index = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Invalid episode.", show_alert=True)
            return

        await process_episode(update, context, index)
        return

    await query.answer()


def main():
    logger.info("Starting Telegram Bot...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url)
    )
    application.add_handler(
        CallbackQueryHandler(callback)
    )

    logger.info("Bot is running.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
