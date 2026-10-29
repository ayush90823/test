"""
Telegram Video -> Stream / Embed link bot

Flow:
  1. User bot ko video bhejta hai (ya forward karta hai)
  2. Bot video ko private storage channel (BIN_CHANNEL) me copy karta hai
  3. Bot ek signed stream link + embed link + iframe code deta hai
  4. Web server Telegram se video chunk-by-chunk stream karta hai (Range support,
     isliye seeking kaam karti hai)
"""
import asyncio
import hashlib
import hmac
import html
import os
import re

from aiohttp import web
from dotenv import load_dotenv
from pyrogram import Client, filters, idle

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
BIN_CHANNEL = int(os.environ["BIN_CHANNEL"])  # e.g. -1001234567890
# Fixed player page (GitHub Pages), e.g. https://user.github.io/repo/
PLAYER_URL = os.environ["PLAYER_URL"].rstrip("/") + "/"
SECRET = os.environ["SECRET_KEY"].encode()
PORT = int(os.environ.get("PORT", "8080"))
ALLOWED_USERS = {
    int(x) for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()
}  # khali = sab allowed

CHUNK = 1024 * 1024  # Pyrogram stream_media 1 MB chunks deta hai

bot = Client("stream_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
_meta_cache: dict[int, tuple[int, str, str]] = {}


def make_hash(msg_id: int) -> str:
    return hmac.new(SECRET, str(msg_id).encode(), hashlib.sha256).hexdigest()[:16]


def links(msg_id: int) -> dict:
    h = make_hash(msg_id)
    # Ye link kabhi nahi badalta: player page tunnel ka latest URL khud dhoondh leta hai
    embed = f"{PLAYER_URL}?id={msg_id}&hash={h}"
    iframe = (
        f'<iframe src="{embed}" width="640" height="360" '
        f'frameborder="0" allowfullscreen></iframe>'
    )
    return {"embed": embed, "iframe": iframe}


# ----------------------------- Telegram bot ---------------------------------
@bot.on_message(filters.command("start") & filters.private)
async def start(_, m):
    await m.reply_text(
        "Mujhe koi video bhejo (ya forward karo), main uska player link "
        "aur iframe code bana dunga."
    )


@bot.on_message(filters.private & (filters.video | filters.document | filters.animation))
async def handle_media(_, m):
    if ALLOWED_USERS and m.from_user.id not in ALLOWED_USERS:
        return await m.reply_text("Aapko is bot ko use karne ki permission nahi hai.")

    media = m.video or m.animation or m.document
    mime = getattr(media, "mime_type", "") or ""
    if not mime.startswith("video/"):
        return await m.reply_text("Sirf video files support hoti hain.")

    status = await m.reply_text("Processing...")
    copied = await m.copy(BIN_CHANNEL)
    l = links(copied.id)
    await status.edit_text(
        f"✅ Link ready\n\n"
        f"🌐 Player link:\n{l['embed']}\n\n"
        f"📋 Iframe code:\n<code>{html.escape(l['iframe'])}</code>",
        disable_web_page_preview=True,
    )


# ----------------------------- Web server -----------------------------------
async def get_meta(msg_id: int):
    if msg_id in _meta_cache:
        return _meta_cache[msg_id]
    msg = await bot.get_messages(BIN_CHANNEL, msg_id)
    media = msg.video or msg.animation or msg.document if msg and not msg.empty else None
    if not media:
        return None
    meta = (media.file_size, media.mime_type or "video/mp4", getattr(media, "file_name", "") or "video.mp4")
    _meta_cache[msg_id] = meta
    return meta


def check_hash(request, msg_id: int) -> bool:
    return hmac.compare_digest(request.query.get("hash", ""), make_hash(msg_id))


async def stream_handler(request: web.Request):
    msg_id = int(request.match_info["mid"])
    if not check_hash(request, msg_id):
        return web.Response(status=403, text="Invalid hash")
    meta = await get_meta(msg_id)
    if not meta:
        return web.Response(status=404, text="Not found")
    size, mime, name = meta

    start, end = 0, size - 1
    range_header = request.headers.get("Range")
    if range_header:
        mt = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if mt:
            s, e = mt.groups()
            if s:
                start = int(s)
                if e:
                    end = min(int(e), size - 1)
            elif e:
                start = max(size - int(e), 0)
        if start > end or start >= size:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{size}"})

    headers = {
        "Content-Type": mime,
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Disposition": f'inline; filename="{name}"',
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=3600",
    }
    status = 200
    if range_header:
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    resp = web.StreamResponse(status=status, headers=headers)
    await resp.prepare(request)

    msg = await bot.get_messages(BIN_CHANNEL, msg_id)
    first_chunk = start // CHUNK
    skip = start - first_chunk * CHUNK
    remaining = end - start + 1
    try:
        async for chunk in bot.stream_media(msg, offset=first_chunk):
            if skip:
                chunk = chunk[skip:]
                skip = 0
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            await resp.write(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                break
    except (ConnectionResetError, asyncio.CancelledError):
        pass  # player ne connection band kar diya (seek/close)
    return resp


async def embed_handler(request: web.Request):
    msg_id = int(request.match_info["mid"])
    if not check_hash(request, msg_id):
        return web.Response(status=403, text="Invalid hash")
    src = f"/stream/{msg_id}?hash={make_hash(msg_id)}"
    page = f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video</title>
<style>html,body{{margin:0;height:100%;background:#000}}
video{{width:100%;height:100%;outline:none}}</style></head>
<body><video controls autoplay playsinline preload="metadata" src="{src}"></video></body></html>"""
    return web.Response(text=page, content_type="text/html")


async def index(_):
    return web.Response(text="Stream server is running.")


async def main():
    await bot.start()
    # Pyrogram ko channel resolve karne ke liye ek baar access chahiye
    await bot.get_chat(BIN_CHANNEL)

    app = web.Application()
    app.add_routes(
        [
            web.get("/", index),
            web.get("/stream/{mid:\\d+}", stream_handler),
            web.get("/embed/{mid:\\d+}", embed_handler),
        ]
    )
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"Server running on port {PORT}")
    await idle()
    await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
