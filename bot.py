import asyncio
import re
import sqlite3
import time
import os
import requests
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEYS")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV yo‘q")

BOT_TOKEN = BOT_TOKEN.strip()
YOUTUBE_API_KEY = YOUTUBE_API_KEY.strip()
# =====================================


# ================= DATABASE ============
DB = "bot.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credit INTEGER,
    last_reset INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    title TEXT,
    tags TEXT,
    description TEXT
)
""")

conn.commit()
# =====================================


# ================= HELPERS =============
YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()
# =====================================


# ================= CREDIT ==============
def get_credit(uid):
    now = int(time.time())
    cur.execute("SELECT credit, last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        cur.execute("INSERT INTO users VALUES (?,?,?)", (uid, 5, now))
        conn.commit()
        return 5

    credit, last = row
    if now - last >= 86400:
        credit = 5
        cur.execute("UPDATE users SET credit=5, last_reset=? WHERE user_id=?", (now, uid))
        conn.commit()

    return credit

def use_credit(uid):
    cur.execute("UPDATE users SET credit = credit - 1 WHERE user_id=?", (uid,))
    conn.commit()
# =====================================


bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def main_kb(credit):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Kredit: {credit}/5", callback_data="noop")]
    ])

def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP KONKURENT NOMLAR", callback_data=f"top:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")]
    ])


@dp.message(Command("start"))
async def start(m: Message):
    credit = get_credit(m.from_user.id)
    await m.answer(
        "👋 YouTube analiz bot\n\n"
        "👉 YouTube linkni yuboring",
        reply_markup=main_kb(credit)
    )


@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    uid = m.from_user.id
    credit = get_credit(uid)

    if credit <= 0:
        await m.answer("❌ Kredit tugagan", reply_markup=main_kb(credit))
        return

    vid = extract_video_id(m.text)
    if not vid:
        return

    data = yt_api("videos", {
        "part": "snippet",
        "id": vid
    })

    sn = data["items"][0]["snippet"]
    title = sn["title"]
    tags = ", ".join(sn.get("tags", []))
    desc = sn.get("description", "")

    cur.execute(
        "INSERT OR REPLACE INTO videos VALUES (?,?,?,?)",
        (vid, title, tags, desc)
    )
    use_credit(uid)
    credit -= 1

    await m.answer(
        f"🎬 {title}\n\n"
        f"👇 Natijalarni tanlang",
        reply_markup=result_kb(vid)
    )


@dp.callback_query(F.data.startswith("top:"))
async def top_videos(c: CallbackQuery):
    vid = c.data.split(":")[1]

    data = yt_api("search", {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "publishedAfter": (datetime.utcnow() - timedelta(days=30)).isoformat("T") + "Z",
        "maxResults": 10,
        "q": vid
    })

    text = "🧠 TOP 10 KONKURENT VIDEO (30 kun):\n\n"
    for i, it in enumerate(data["items"], 1):
        v_id = it["id"]["videoId"]
        title = it["snippet"]["title"]
        text += f"{i}. {title}\nhttps://youtu.be/{v_id}\n\n"

    await c.message.answer(text)
    await c.answer()


@dp.callback_query(F.data.startswith("channels:"))
async def channels(c: CallbackQuery):
    vid = c.data.split(":")[1]

    data = yt_api("search", {
        "part": "snippet",
        "type": "channel",
        "maxResults": 5,
        "q": vid
    })

    text = "📺 RAQOBATCHI KANALLAR:\n\n"
    for i, it in enumerate(data["items"], 1):
        cid = it["id"]["channelId"]
        name = it["snippet"]["channelTitle"]
        text += f"{i}. {name}\nhttps://www.youtube.com/channel/{cid}\n\n"

    await c.message.answer(text)
    await c.answer()


@dp.callback_query(F.data.startswith("tags:"))
async def tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    cur.execute("SELECT tags, description FROM videos WHERE video_id=?", (vid,))
    tags, desc = cur.fetchone()

    await c.message.answer(
        f"🏷 VIDEO TAGLAR:\n```\n{tags}\n```\n\n"
        f"📝 DESCRIPTION:\n```\n{desc[:3500]}\n```",
        parse_mode="Markdown"
    )
    await c.answer()


@dp.callback_query(F.data == "noop")
async def noop(c: CallbackQuery):
    await c.answer()


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
