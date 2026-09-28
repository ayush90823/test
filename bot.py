import os
import re
import time
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8647638574:AAFA688Xv_h85doU99zBWfBHmnb3N4MKqVw")
bot = telebot.TeleBot(BOT_TOKEN)

def extract_gdflix_page(target_url):
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
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            content_lower = page.content().lower()

            # Cloudflare Turnstile Bypass Logic
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
                    continue_btn = page.locator('button:has-text("Continue"), input[value="Continue"], a:has-text("Continue")')
                    if continue_btn.is_visible():
                        continue_btn.click()
                        time.sleep(5)
                except Exception:
                    pass

            final_html = page.content()
            browser.close()
            return final_html, None

        except Exception as e:
            browser.close()
            return None, str(e)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 **Namaste!** Target link bhejo, main Server buttons & GDFlix links extract karke dunga.")

@bot.message_handler(func=lambda message: message.text.startswith(('http://', 'https://')))
def process_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "⚙️ Page parse ho raha hai & links extract ho rahe hain...")

    html, error = extract_gdflix_page(url)

    if error:
        bot.edit_message_text(f"❌ Error: {error}", message.chat.id, status_msg.message_id)
        return

    soup = BeautifulSoup(html, 'html.parser')
    extracted_links = []

    # Target class: 'server-btn' or 'server-list'
    server_buttons = soup.find_all('a', class_=re.compile(r'server-btn|server-link'))

    if server_buttons:
        for btn in server_buttons:
            href = btn.get('href')
            if not href or not href.startswith('http'):
                continue

            # Server Name (GDFlix / Gdshare)
            label = btn.get('data-label', '').strip()
            server_name_elem = btn.find('span', class_='server-name')
            
            if server_name_elem:
                server_name = server_name_elem.contents[0].strip() if server_name_elem.contents else label
            else:
                server_name = label or "Server"

            # Quality & Size Extraction (e.g., 480p x264 • 103.13 MB)
            meta_elem = btn.find('span', class_='server-meta')
            meta_info = ""
            if meta_elem:
                raw_meta = " ".join(meta_elem.text.split())
                parts = raw_meta.split('•')
                if len(parts) >= 2:
                    meta_info = f" ({parts[0].strip()} - {parts[1].strip()})"

            button_title = f"{server_name}{meta_info}"
            extracted_links.append((button_title, href))

    # Fallback agar 'server-btn' class na mile toh general links search karein
    if not extracted_links:
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.text.strip() or "Download Link"
            if any(x in href.lower() or x in text.lower() for x in ['gdflix', 'gdshare', 'gdrive', 'drive']):
                extracted_links.append((text, href))

    bot.delete_message(message.chat.id, status_msg.message_id)

    if extracted_links:
        markup = InlineKeyboardMarkup()
        for b_title, b_url in extracted_links:
            clean_title = b_title[:35] if len(b_title) > 35 else b_title
            markup.add(InlineKeyboardButton(text=f"⚡ {clean_title}", url=b_url))

        bot.send_message(
            message.chat.id,
            f"🎉 **Download Servers Extracted ({len(extracted_links)} Found):**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="🔗 Open Page Directly", url=url))
        bot.send_message(
            message.chat.id,
            "⚠️ Webpage par `server-btn` links match nahi ho sake. Page ko browser mein kholein:",
            reply_markup=markup
        )

bot.infinity_polling()
