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


# ================= CONFIG ==============
CACHE_TTL = 6 * 3600   # 6 soat
CREDIT_DAILY = 5
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
    category TEXT,
    published TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    tags TEXT,
    description TEXT,
    updated_at INTEGER
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
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=20
    )
    r.raise_for_status()
    return r.json()


def get_category_name(cat_id):
    data = yt_api("videoCategories", {
        "part": "snippet",
        "id": cat_id,
        "regionCode": "US"
    })
    if data["items"]:
        return data["items"][0]["snippet"]["title"]
    return "Unknown"


def detect_like_fraud(views, likes, comments, hours):
    if views == 0:
        return "⚪ Ma’lumot yetarli emas"

    like_ratio = likes / views
    comment_ratio = comments / views

    if like_ratio > 0.25 and views > 1000:
        return "🔴 LIKE NAKRUTKA EHTIMOLI YUQORI"
    if comment_ratio < 0.001 and views > 5000:
        return "🟡 SHUBHALI FAOLLIGI"
    if hours < 2 and views > 10000:
        return "🟡 TEZ SUN’IY O‘SISH"

    return "🟢 NORMAL FAOLLIGI"
# =====================================


# ================= CREDIT ==============
def get_credit(uid):
    now = int(time.time())
    cur.execute("SELECT credit, last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        cur.execute("INSERT INTO users VALUES (?,?,?)", (uid, CREDIT_DAILY, now))
        conn.commit()
        return CREDIT_DAILY

    credit, last = row
    if now - last >= 86400:
        credit = CREDIT_DAILY
        cur.execute(
            "UPDATE users SET credit=?, last_reset=? WHERE user_id=?",
            (CREDIT_DAILY, now, uid)
        )
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
        [InlineKeyboardButton(
            text=f"💳 Kredit: {credit}/{CREDIT_DAILY} (24 soatda yangilanadi)",
            callback_data="noop"
        )]
    ])


@dp.message(Command("start"))
async def start(m: Message):
    credit = get_credit(m.from_user.id)
    await m.answer(
        "👋 YouTube ANALIZ BOT\n\n"
        "👉 YouTube linkni yuboring",
        reply_markup=main_kb(credit)
    )


@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    uid = m.from_user.id
    credit = get_credit(uid)

    vid = extract_video_id(m.text)
    if not vid:
        return

    # CACHE tekshirish
    cur.execute("SELECT * FROM videos WHERE video_id=?", (vid,))
    row = cur.fetchone()

    now = int(time.time())
    used_cache = False

    if row:
        updated_at = row[-1]
        if now - updated_at < CACHE_TTL:
            used_cache = True

    if not used_cache and credit <= 0:
        await m.answer("❌ Kredit tugagan", reply_markup=main_kb(credit))
        return

    if not row or not used_cache:
        data = yt_api("videos", {
            "part": "snippet,statistics",
            "id": vid
        })

        item = data["items"][0]
        sn = item["snippet"]
        st = item["statistics"]

        category = get_category_name(sn.get("categoryId", ""))

        views = int(st.get("viewCount", 0))
        likes = int(st.get("likeCount", 0))
        comments = int(st.get("commentCount", 0))

        cur.execute("""
        INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            vid,
            sn["title"],
            sn["channelTitle"],
            category,
            sn["publishedAt"],
            views,
            likes,
            comments,
            ", ".join(sn.get("tags", [])),
            sn.get("description", ""),
            now
        ))
        conn.commit()

        if not used_cache:
            use_credit(uid)
            credit -= 1

    cur.execute("SELECT * FROM videos WHERE video_id=?", (vid,))
    _, title, channel, category, published, views, likes, comments, tags, desc, _ = cur.fetchone()

    dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    hours = (datetime.utcnow() - dt).total_seconds() / 3600

    fraud = detect_like_fraud(views, likes, comments, hours)

    await m.answer(
        f"🎬 {title}\n"
        f"📂 Kategoriya: {category}\n"
        f"📺 Kanal: {channel}\n"
        f"⏰ Yuklangan: {dt.strftime('%Y-%m-%d %H:%M')} UTC\n\n"
        f"👁 {views}   👍 {likes}   💬 {comments}\n"
        f"🚨 {fraud}",
        reply_markup=main_kb(credit)
    )


@dp.callback_query(F.data == "noop")
async def noop(c: CallbackQuery):
    await c.answer()


async def main():
    print("🤖 BOT ISHLAYAPTI (DB + CACHE + CATEGORY + FRAUD)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
