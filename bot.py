import os
import re
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

import requests

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEYS")

ADMIN_IDS = {787803140}  # <-- O'ZINGNING TG ID

CREDIT_LIMIT = 5
DB_PATH = "data.db"

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# ================== DB ==================
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    credits INTEGER,
    reset_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS links (
    user_id INTEGER,
    video_id TEXT,
    UNIQUE(user_id, video_id)
)
""")

conn.commit()

# ================== RAM CACHE ==================
VIDEO_CACHE = {}
SEARCH_CACHE = {}

# ================== BOT ==================
bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ================== HELPERS ==================
def extract_video_id(url: str):
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def get_user(user_id, username):
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    now = datetime.now(timezone.utc)

    if not row:
        reset = now + timedelta(days=1)
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?)",
            (user_id, username, CREDIT_LIMIT, reset.isoformat())
        )
        conn.commit()
        return CREDIT_LIMIT, reset

    credits, reset_at = row[2], datetime.fromisoformat(row[3])

    if now >= reset_at:
        reset = now + timedelta(days=1)
        credits = CREDIT_LIMIT
        cur.execute(
            "UPDATE users SET credits=?, reset_at=? WHERE user_id=?",
            (credits, reset.isoformat(), user_id)
        )
        conn.commit()
        return credits, reset

    return credits, reset_at

def update_credit(user_id, credits):
    cur.execute(
        "UPDATE users SET credits=? WHERE user_id=?",
        (credits, user_id)
    )
    conn.commit()

def yt_request(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"{YOUTUBE_API}/{endpoint}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

# ================== START ==================
@dp.message(CommandStart())
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP nomlar\n"
        "🏷 Tag / Tavsif\n"
        "📺 Raqobatchi kanallar\n"
        "🚨 Nakrutka tekshiruv\n"
        "🎟 Kredit nazorati\n\n"
        "chiqarib beraman."
    )

# ================== VIDEO HANDLE ==================
@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    user_id = msg.from_user.id
    username = msg.from_user.username or ""

    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Video topilmadi.")
        return

    credits, reset_at = get_user(user_id, username)

    if user_id not in ADMIN_IDS:
        cur.execute(
            "SELECT 1 FROM links WHERE user_id=? AND video_id=?",
            (user_id, vid)
        )
        if not cur.fetchone():
            if credits <= 0:
                await msg.answer("❌ Kredit tugadi.")
                return
            credits -= 1
            update_credit(user_id, credits)
            cur.execute(
                "INSERT OR IGNORE INTO links VALUES (?,?)",
                (user_id, vid)
            )
            conn.commit()

    if vid in VIDEO_CACHE:
        data = VIDEO_CACHE[vid]
    else:
        data = yt_request(
            "videos",
            {
                "part": "snippet,statistics",
                "id": vid
            }
        )
        if not data["items"]:
            await msg.answer("❌ Video topilmadi yoki API cheklangan.")
            return
        VIDEO_CACHE[vid] = data

    item = data["items"][0]
    s = item["snippet"]
    st = item["statistics"]

    title = s["title"]
    channel = s["channelTitle"]

    published = datetime.fromisoformat(
        s["publishedAt"].replace("Z", "+00:00")
    ).astimezone(timezone(timedelta(hours=5)))

    views = int(st.get("viewCount", 0))
    likes = int(st.get("likeCount", 0))
    comments = int(st.get("commentCount", 0))

    nakrutka = "🔴 ehtimoli yuqori" if likes > views else "🟢 normal"

    text = (
        f"🎬 <b>{title}</b>\n\n"
        f"🕒 Yuklangan: {published:%Y-%m-%d %H:%M} (Toshkent vaqti)\n"
        f"📺 Kanal: <b>{channel}</b>\n\n"
        f"👁 {views}   👍 {likes}   💬 {comments}\n"
        f"⚠️ Likelar soni: {nakrutka}\n"
        f"🎟 Kredit: {credits}/{CREDIT_LIMIT} (har 24 soatda yangilanadi)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🧠 TOP KONKURENT NOMLAR", callback_data=f"titles:{vid}")],
        [InlineKeyboardButton("🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")],
        [InlineKeyboardButton("📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")]
    ])

    await msg.answer(text, reply_markup=kb)

# ================== CALLBACKS ==================
@dp.callback_query(F.data.startswith("titles:"))
async def cb_titles(call: CallbackQuery):
    await call.answer("Analiz qilinmoqda...")
    await call.message.answer("🧠 TOP KONKURENT NOMLAR (30 kun)...\n(tez orada)")

@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(call: CallbackQuery):
    await call.answer()
    await call.message.answer(
        "🏷 <b>TAG / TAVSIF</b>\n\n"
        "<b>Video taglari:</b>\n"
        "```\nexample, tags, here\n```\n\n"
        "<b>Kanal taglari:</b>\n"
        "```\nchannel, tags\n```\n\n"
        "<b>Description:</b>\n"
        "```\nVideo description...\n```"
    )

@dp.callback_query(F.data.startswith("channels:"))
async def cb_channels(call: CallbackQuery):
    await call.answer()
    await call.message.answer(
        "📺 <b>RAQOBATCHI KANALLAR (TOP)</b>\n\n"
        "1. BNG OYOT\n"
        "2. OBA BeamNG\n"
        "3. BeamNG Family"
    )

# ================== MAIN ==================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
