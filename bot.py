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
    status_msg = bot.reply_to(message, "🔍 Hindi Anime Zone page parse kiya ja raha hai...")

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
            content = soup  # Fallback agar div class na mile

        seasons_data = {}
        current_section = "Episodes & Downloads"

        # Content ke andar ke headings aur links analyze karna
        for element in content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'div', 'a']):
            # Agar Heading ya Section Bold text milta hai (Season/Quality Info)
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                header_text = element.text.strip()
                if header_text and len(header_text) < 60:
                    current_section = header_text
                    continue

            # Agar link element hai
            if element.name == 'a' and element.get('href'):
                text = element.text.strip()
                href = element['href']

                # Filter out unnecessary links (social media, home page, comments)
                if not text or not href.startswith('http') or 'javascript' in href:
                    continue
                if any(x in href.lower() for x in ['facebook.com', 'twitter.com', 'telegram.me', 't.me', 'whatsapp.com', 'category', 'tag', 'author']):
                    continue

                # Episode, Download, Quality ya Drive link matching
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

        # Buttons Bhejna (Season-wise / Section-wise)
        for section_title, ep_list in seasons_data.items():
            if not ep_list:
                continue

            markup = InlineKeyboardMarkup()
            row = []
            
            for ep_title, ep_url in ep_list:
                clean_title = ep_title.replace("\n", " ").strip()
                if len(clean_title) > 25:
                    clean_title = clean_title[:22] + "..."
                
                button = InlineKeyboardButton(text=f"📁 {clean_title}", url=ep_url)
                row.append(button)
                
                # 2 Buttons per row (Grid Layout)
                if len(row) == 2:
                    markup.row(*row)
                    row = []
            
            if row:
                markup.row(*row)

            bot.send_message(
                message.chat.id, 
                f"🎬 **{section_title}**\nTotal Links: {len(ep_list)}", 
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
