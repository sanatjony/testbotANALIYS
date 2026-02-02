import asyncio
import re
import hashlib
import sqlite3
import time
import os
import requests
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEYS")  # BITTA KEY
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV variables yo‘q (BOT_TOKEN / YOUTUBE_API_KEYS)")

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
    channel TEXT,
    published TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
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


def reset_credit_if_needed(uid):
    cur.execute("SELECT credit, last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    now = int(time.time())
    if row:
        credit, last = row
        if now - last >= 86400:
            cur.execute(
                "UPDATE users SET credit=5, last_reset=? WHERE user_id=?",
                (now, uid)
            )
            conn.commit()


def get_or_create_user(uid):
    cur.execute("SELECT credit FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO users VALUES (?,?,?)",
            (uid, 5, int(time.time()))
        )
        conn.commit()
        return 5
    reset_credit_if_needed(uid)
    cur.execute("SELECT credit FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()[0]


def update_credit(uid, val):
    cur.execute("UPDATE users SET credit = credit + ? WHERE user_id=?", (val, uid))
    conn.commit()


def yt_api(url, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()
# =====================================


# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
# =====================================


def main_keyboard(credit):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Kredit: {credit}/5 (24 soatda yangilanadi)", callback_data="noop")]
    ])


def result_keyboard(video_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP KONKURENT NOMLAR", callback_data=f"top:{video_id}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{video_id}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{video_id}")]
    ])


@dp.message(Command("start"))
async def start(m: Message):
    credit = get_or_create_user(m.from_user.id)
    await m.answer(
        "👋 Xush kelibsiz!\n\n"
        "👉 YouTube linkni yuboring.\n"
        "Bot avtomatik analiz qiladi.",
        reply_markup=main_keyboard(credit)
    )


# ============== ANALIZ =============
@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    uid = m.from_user.id
    credit = get_or_create_user(uid)
    if credit <= 0:
        await m.answer("❌ Kredit tugagan", reply_markup=main_keyboard(credit))
        return

    url = re.search(YOUTUBE_REGEX, m.text).group(1)
    vid = extract_video_id(url)
    if not vid:
        return

    cur.execute("SELECT title FROM videos WHERE video_id=?", (vid,))
    cached = cur.fetchone()

    if not cached:
        data = yt_api(
            "https://www.googleapis.com/youtube/v3/videos",
            {
                "part": "snippet,statistics",
                "id": vid
            }
        )

        if not data["items"]:
            await m.answer("❌ Video topilmadi")
            return

        item = data["items"][0]
        sn = item["snippet"]
        st = item["statistics"]

        title = sn["title"]
        channel = sn["channelTitle"]
        published = sn["publishedAt"]
        views = int(st.get("viewCount", 0))
        likes = int(st.get("likeCount", 0))
        comments = int(st.get("commentCount", 0))
        tags = ", ".join(sn.get("tags", []))
        desc = sn.get("description", "")

        cur.execute(
            "INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?, ?,?)",
            (vid, title, channel, published, views, likes, comments, tags, desc)
        )
        update_credit(uid, -1)
        credit -= 1
        conn.commit()
    else:
        cur.execute("SELECT * FROM videos WHERE video_id=?", (vid,))
        _, title, channel, published, views, likes, comments, tags, desc = cur.fetchone()

    dt = datetime.fromisoformat(published.replace("Z", "+00:00")) + timedelta(hours=5)

    await m.answer(
        f"🎬 {title}\n"
        f"⏰ Yuklangan: {dt.strftime('%Y-%m-%d %H:%M')} (Toshkent)\n"
        f"📺 Kanal: {channel}\n\n"
        f"👁 {views}   👍 {likes}   💬 {comments}",
        reply_markup=result_keyboard(vid)
    )


@dp.callback_query(F.data.startswith("top:"))
async def top_videos(c: CallbackQuery):
    vid = c.data.split(":")[1]
    data = yt_api(
        "https://www.googleapis.com/youtube/v3/search",
        {
            "part": "snippet",
            "q": vid,
            "type": "video",
            "maxResults": 5
        }
    )

    text = "🧠 TOP KONKURENT NOMLAR (30 kun):\n\n"
    for i, it in enumerate(data["items"], 1):
        text += f"{i}. {it['snippet']['title']}\n"

    await c.message.answer(text)
    await c.answer()


@dp.callback_query(F.data.startswith("tags:"))
async def tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    cur.execute("SELECT tags, description FROM videos WHERE video_id=?", (vid,))
    tags, desc = cur.fetchone()

    await c.message.answer(
        f"🏷 VIDEO TAGLAR:\n{tags}\n\n"
        f"DESCRIPTION:\n{desc[:3000]}"
    )
    await c.answer()


@dp.callback_query(F.data.startswith("channels:"))
async def channels(c: CallbackQuery):
    vid = c.data.split(":")[1]
    data = yt_api(
        "https://www.googleapis.com/youtube/v3/search",
        {
            "part": "snippet",
            "q": vid,
            "type": "channel",
            "maxResults": 5
        }
    )

    text = "📺 RAQOBATCHI KANALLAR:\n\n"
    for i, it in enumerate(data["items"], 1):
        text += f"{i}. {it['snippet']['channelTitle']}\n"

    await c.message.answer(text)
    await c.answer()


@dp.callback_query(F.data == "noop")
async def noop(c: CallbackQuery):
    await c.answer()


# ================= RUN =================
async def main():
    print("🤖 FINAL BOT ISHLAYAPTI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
