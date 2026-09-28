import os
import re
import time
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8647638574:AAFA688Xv_h85doU99zBWfBHmnb3N4MKqVw")
bot = telebot.TeleBot(BOT_TOKEN)

def solve_and_extract(url):
    with sync_playwright() as p:
        # Launch Headless Chromium on GitHub Actions
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # Cloudflare Turnstile Auto-Clicker Logic
            for _ in range(3):  # 3 baar try karega agar captcha delay kare
                content = page.content()
                if "challenges.cloudflare.com" in content or "turnstile" in content.lower():
                    try:
                        # Turnstile iframe target karke click karna
                        frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
                        checkbox = frame.locator('input[type="checkbox"], .mark, body')
                        if checkbox.is_visible():
                            checkbox.click()
                            time.sleep(5)  # Captcha pass hone ka wait
                    except Exception:
                        pass
                else:
                    break

            # Page content fetch karna
            final_html = page.content()
            browser.close()
            return final_html, None

        except Exception as e:
            browser.close()
            return None, str(e)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 **Namaste!** Main GitHub Actions server par Playwright se Auto-Captcha Bypass karke GDFlix Links extract karunga. URL bhejo!",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text.startswith(('http://', 'https://')))
def process_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "⚙️ Playwright Browser launch ho raha hai & Captcha auto-pass ho raha hai...")

    html, error = solve_and_extract(url)

    if error:
        bot.edit_message_text(f"❌ Error aaya: {error}", message.chat.id, status_msg.message_id)
        return

    soup = BeautifulSoup(html, 'html.parser')
    gdflix_links = []

    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.text.strip() or "GDFlix Link"

        if 'gdflix' in href.lower() or 'gdrive' in href.lower() or 'drive' in href.lower():
            gdflix_links.append((text, href))

    if gdflix_links:
        markup = InlineKeyboardMarkup()
        for g_text, g_url in gdflix_links:
            markup.add(InlineKeyboardButton(text=f"⚡ {g_text[:30]}", url=g_url))

        bot.delete_message(message.chat.id, status_msg.message_id)
        bot.send_message(
            message.chat.id,
            "🎉 **GDFlix / Download Links Extracted:**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text("⚠️ Direct GDFlix link nahi mil saka. Page structure change ho sakta hai.", message.chat.id, status_msg.message_id)

bot.infinity_polling()
