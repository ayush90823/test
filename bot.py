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
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        captcha_status = "Captcha Not Found"
        screenshot_bytes = None

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # Check if Captcha frame exists
            content_check = page.content().lower()
            if "challenges.cloudflare.com" in content_check or "turnstile" in content_check:
                captcha_status = "⚠️ Captcha Detect Hua"
                try:
                    frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
                    checkbox = frame.locator('input[type="checkbox"], .mark, body')
                    if checkbox.is_visible():
                        checkbox.click()
                        time.sleep(6)  # Wait for bypass
                except Exception as e:
                    captcha_status = f"❌ Captcha Click Failed: {str(e)}"

            # Final verification after click
            final_check = page.content().lower()
            if "challenges.cloudflare.com" not in final_check and "turnstile" not in final_check:
                captcha_status = "✅ Captcha Solved / Bypass Successful!"
            elif captcha_status != "Captcha Not Found":
                captcha_status = "❌ Captcha Solve Nahi Hua (Stuck)"

            # Take screenshot of the result
            screenshot_bytes = page.screenshot(full_page=False)
            final_html = page.content()

            browser.close()
            return final_html, captcha_status, screenshot_bytes, None

        except Exception as e:
            browser.close()
            return None, "Error", None, str(e)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 **Namaste!** URL bhejo, main Playwright se page scan karke status + links dunga.",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text.startswith(('http://', 'https://')))
def process_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "⚙️ Browser launch ho raha hai & Captcha check kiya ja raha hai...")

    html, captcha_status, screenshot, error = solve_and_extract(url)

    if error:
        bot.edit_message_text(f"❌ Error aaya: {error}", message.chat.id, status_msg.message_id)
        return

    soup = BeautifulSoup(html, 'html.parser')
    all_links = []

    # Safe extraction of all download buttons/links
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.text.strip() or "Download Link"

        if not href.startswith('http') or 'javascript' in href:
            continue

        # Match any download, gdflix, drive, fast, mega or direct link
        if re.search(r'gdflix|drive|gdrive|download|fast|mega|go|link|file', href + " " + text, re.IGNORECASE):
            all_links.append((text, href))

    bot.delete_message(message.chat.id, status_msg.message_id)

    # Status summary
    report = f"📌 **Captcha Status:** {captcha_status}\n🔗 **Links Found:** {len(all_links)}"

    if all_links:
        markup = InlineKeyboardMarkup()
        for g_text, g_url in all_links[:15]: # Max 15 buttons
            clean_btn_text = g_text.replace("\n", " ")[:25]
            markup.add(InlineKeyboardButton(text=f"⚡ {clean_btn_text}", url=g_url))

        bot.send_message(
            message.chat.id,
            f"🎉 **Extraction Result:**\n\n{report}",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        # Links na milne par Photo/Screenshot bhejega verification ke liye
        if screenshot:
            bot.send_photo(
                message.chat.id,
                photo=screenshot,
                caption=f"⚠️ Links nahi mile! Page ka screenshot dekhein:\n\n{report}\n\n*Agar screenshot mein captcha dikh raha hai toh bypass fail hua hai, agar page khul gaya hai toh text pattern change hai.*",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(message.chat.id, f"⚠️ Links nahi mile.\n\n{report}")

bot.infinity_polling()
