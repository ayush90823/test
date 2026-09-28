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
        # Headless Chromium with Anti-Bot Detection Flags
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-size=1920,1080',
            ]
        )
        
        # Real Browser User Context
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            locale="en-US"
        )
        
        page = context.new_page()

        # Hide webdriver flag (Jugaad 1)
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            # Turnstile Captcha Check & Auto-Click (Jugaad 2)
            content = page.content().lower()
            if "turnstile" in content or "verify you're human" in content or "challenges.cloudflare.com" in content:
                
                # Iframe target karke click karna
                try:
                    for _ in range(3):
                        frames = page.frames
                        for f in frames:
                            if "challenges.cloudflare.com" in f.url:
                                # Captcha checkbox ya body par click
                                f.click('body', timeout=5000)
                                time.sleep(5)
                                break
                except Exception:
                    pass

                # Captcha pass hone ke baad 'Continue' button par click
                try:
                    continue_btn = page.locator('button:has-text("Continue"), input[value="Continue"], a:has-text("Continue")')
                    if continue_btn.is_visible():
                        continue_btn.click()
                        time.sleep(5)
                except Exception:
                    pass

            # Final HTML extract karna
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
        "👋 **Namaste!** URL bhejo, main Stealth Playwright se Captcha bypass karke direct GDFlix link nikal kar dunga.",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text.startswith(('http://', 'https://')))
def process_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "⚙️ Stealth Browser launch ho raha hai & Captcha auto-tick ho raha hai...")

    html, error = extract_gdflix_with_stealth(url)

    if error:
        bot.edit_message_text(f"❌ Error aaya: {error}", message.chat.id, status_msg.message_id)
        return

    soup = BeautifulSoup(html, 'html.parser')
    gdflix_links = []

    # Scraping GDFlix / Download Links
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.text.strip() or "Download Link"

        if not href.startswith('http') or 'javascript' in href:
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
        # Fallback Direct Page Link
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="🔗 Open Page Directly", url=url))
        bot.send_message(
            message.chat.id,
            "⚠️ Captcha bypass hone ke baad bhi page par direct `GDFlix` key match nahi hui. Page yahan se kholein:",
            reply_markup=markup
        )

bot.infinity_polling()
