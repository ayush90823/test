import os
import re
import time
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8647638574:AAFA688Xv_h85doU99zBWfBHmnb3N4MKqVw")
bot = telebot.TeleBot(BOT_TOKEN)

def extract_gdflix_with_stealth(target_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--window-size=1920,1080',
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()

        try:
            # 2 Baar Try Karega agar pehli baar Timeout/522 aaye
            for attempt in range(2):
                response = page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                content_lower = page.content().lower()

                # Agar Cloudflare Error 522/5xx aaye toh wait karke reload karega
                if "522" in content_lower or "5xx-error-landing" in content_lower or "connection timed out" in content_lower:
                    if attempt == 0:
                        time.sleep(5)
                        page.reload()
                        continue
                    else:
                        browser.close()
                        return None, "⚠️ Website Server Down hai ya GitHub Actions IP response timeout ho raha hai (Error 522)."

                # Captcha Handling Logic
                if "turnstile" in content_lower or "verify you're human" in content_lower:
                    try:
                        for f in page.frames:
                            if "challenges.cloudflare.com" in f.url:
                                f.click('body', timeout=5000)
                                time.sleep(5)
                                break
                    except Exception:
                        pass

                    try:
                        continue_btn = page.locator('button:has-text("Continue"), input[value="Continue"]')
                        if continue_btn.is_visible():
                            continue_btn.click()
                            time.sleep(5)
                    except Exception:
                        pass

                final_html = page.content()
                browser.close()
                return final_html, None

            browser.close()
            return None, "❌ Target page load nahi ho saka."

        except Exception as e:
            browser.close()
            return None, str(e)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 **Namaste!** URL bhejo, main Playwright se GDFlix link extract karunga.")

@bot.message_handler(func=lambda message: message.text.startswith(('http://', 'https://')))
def process_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "⚙️ Webpage process ho raha hai...")

    html, error = extract_gdflix_with_stealth(url)

    if error:
        bot.edit_message_text(f"❌ {error}", message.chat.id, status_msg.message_id)
        return

    soup = BeautifulSoup(html, 'html.parser')
    gdflix_links = []

    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.text.strip() or "Download Link"

        # Cloudflare Error / System Links Filter
        if "cloudflare.com" in href or "5xx-error" in href or "javascript" in href:
            continue

        if any(x in href.lower() or x in text.lower() for x in ['gdflix', 'gdrive', 'drive', 'download', 'fast', 'mega', 'link']):
            gdflix_links.append((text, href))

    bot.delete_message(message.chat.id, status_msg.message_id)

    if gdflix_links:
        markup = InlineKeyboardMarkup()
        for g_text, g_url in gdflix_links[:15]:
            clean_txt = g_text.replace("\n", " ")[:25]
            markup.add(InlineKeyboardButton(text=f"⚡ {clean_txt}", url=g_url))

        bot.send_message(
            message.chat.id,
            "🎉 **GDFlix / Download Links Successfully Extracted:**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="🔗 Open Page Directly", url=url))
        bot.send_message(
            message.chat.id,
            "⚠️ Direct links extract nahi ho paaye. Page ko browser mein kholein:",
            reply_markup=markup
        )

bot.infinity_polling()
