import os
import re
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# GitHub Secrets se token lega, agar nahi mila toh fallback default token use karega
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8647638574:AAFA688Xv_h85doU99zBWfBHmnb3N4MKqVw")
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 **Namaste!** Mujhe kisi bhi page ka URL bhejo, main uske episodes ke Season-wise Grid Buttons bana dunga.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text.startswith(('http://', 'https://')))
def process_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "🔍 Page extract kiya ja raha hai, kripya intezar karein...")

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            bot.edit_message_text("❌ Page load nahi ho saka. Invalid URL ya website block hai.", message.chat.id, status_msg.message_id)
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        all_links = soup.find_all('a', href=True)
        
        seasons_data = {}
        current_season = "Season 1"
        
        for link in all_links:
            text = link.text.strip()
            href = link['href']
            
            if not text or not href.startswith('http'):
                continue
                
            if "season" in text.lower() or "s0" in text.lower():
                current_season = text
                continue

            if re.search(r'ep|episode|\b\d{1,3}\b|download|480p|720p|1080p', text, re.IGNORECASE):
                if current_season not in seasons_data:
                    seasons_data[current_season] = []
                
                if (text, href) not in seasons_data[current_season]:
                    seasons_data[current_season].append((text, href))

        bot.delete_message(message.chat.id, status_msg.message_id)

        if not seasons_data:
            bot.send_message(message.chat.id, "⚠️ Page par koi episodes ya valid links nahi mile.")
            return

        for season_name, ep_list in seasons_data.items():
            if not ep_list:
                continue

            markup = InlineKeyboardMarkup()
            row = []
            
            for ep_title, ep_url in ep_list:
                clean_title = ep_title[:20] if len(ep_title) > 20 else ep_title
                button = InlineKeyboardButton(text=f"📁 {clean_title}", url=ep_url)
                row.append(button)
                
                if len(row) == 2:
                    markup.row(*row)
                    row = []
            
            if row:
                markup.row(*row)

            bot.send_message(
                message.chat.id, 
                f"🎬 **{season_name}**\nTotal Links: {len(ep_list)}", 
                reply_markup=markup, 
                parse_mode="Markdown"
            )

    except Exception as e:
        bot.edit_message_text(f"⚠️ Error aaya: {str(e)}", message.chat.id, status_msg.message_id)

bot.infinity_polling()
