import os
import re
from bs4 import BeautifulSoup
import cloudscraper
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# Bot Token
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8647638574:AAFA688Xv_h85doU99zBWfBHmnb3N4MKqVw")
bot = telebot.TeleBot(BOT_TOKEN)

# Cloudscraper Browser Bypass
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

# Helper function: List ko fixed chunks (parts) mein todne ke liye
def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 **Namaste!** Mujhe kisi bhi Anime post ka URL bhejo, main uske Season aur Episodes ke Grid Buttons bana dunga.",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text.startswith(('http://', 'https://')))
def process_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "🔍 Page parse kiya ja raha hai, kripya intezar karein...")

    try:
        response = scraper.get(url, timeout=15)
        
        if response.status_code != 200:
            bot.edit_message_text(
                f"❌ Page load nahi ho saka (Status Code: {response.status_code}). Website block kar rahi hai ya URL galat hai.",
                message.chat.id,
                status_msg.message_id
            )
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # WordPress Post Content Container Target Karna
        content = soup.find('div', class_=re.compile(r'entry-content|post-content|post-body|inside-article'))
        if not content:
            content = soup

        seasons_data = {}
        current_section = "Episodes & Downloads"

        for element in content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'div', 'a']):
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                header_text = element.text.strip()
                if header_text and len(header_text) < 60:
                    current_section = header_text
                    continue

            if element.name == 'a' and element.get('href'):
                text = element.text.strip()
                href = element['href']

                if not text or not href.startswith('http') or 'javascript' in href:
                    continue
                if any(x in href.lower() for x in ['facebook.com', 'twitter.com', 'telegram.me', 't.me', 'whatsapp.com', 'category', 'tag', 'author']):
                    continue

                if re.search(r'ep|episode|download|480p|720p|1080p|watch|gdrive|mega|drive|link|zip|batch|\b\d{1,3}\b', text, re.IGNORECASE):
                    if current_section not in seasons_data:
                        seasons_data[current_section] = []
                    
                    if (text, href) not in seasons_data[current_section]:
                        seasons_data[current_section].append((text, href))

        total_found = sum(len(v) for v in seasons_data.values())
        
        if total_found == 0:
            bot.edit_message_text("⚠️ Is page par koi episodes ya valid download links nahi mile.", message.chat.id, status_msg.message_id)
            return

        # Status message delete karein
        try:
            bot.delete_message(message.chat.id, status_msg.message_id)
        except Exception:
            pass

        # Sections & Safe Chunking
        # Ek message mein maximum 20 buttons (10 rows of 2) bheje jayenge
        MAX_BUTTONS_PER_MSG = 20

        for section_title, ep_list in seasons_data.items():
            if not ep_list:
                continue

            # List ko chunks mein baantein
            chunks = list(chunk_list(ep_list, MAX_BUTTONS_PER_MSG))
            total_parts = len(chunks)

            for idx, chunk in enumerate(chunks, 1):
                markup = InlineKeyboardMarkup()
                row = []
                
                for ep_title, ep_url in chunk:
                    clean_title = ep_title.replace("\n", " ").strip()
                    if len(clean_title) > 22:
                        clean_title = clean_title[:19] + "..."
                    
                    button = InlineKeyboardButton(text=f"📁 {clean_title}", url=ep_url)
                    row.append(button)
                    
                    # 2 Buttons per row (Grid)
                    if len(row) == 2:
                        markup.row(*row)
                        row = []
                
                if row:
                    markup.row(*row)

                # Header Title Format (e.g., Part 1/2 agar multiple messages hon)
                part_text = f" (Part {idx}/{total_parts})" if total_parts > 1 else ""
                msg_caption = f"🎬 **{section_title}**{part_text}\nTotal Links in this batch: {len(chunk)}"

                bot.send_message(
                    message.chat.id, 
                    msg_caption, 
                    reply_markup=markup, 
                    parse_mode="Markdown"
                )

    except Exception as e:
        error_text = f"⚠️ Error aaya: {str(e)}"
        try:
            bot.edit_message_text(error_text, message.chat.id, status_msg.message_id)
        except Exception:
            bot.send_message(message.chat.id, error_text)

bot.infinity_polling()
