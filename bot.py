# =========================
# FINAL YOUTUBE ANALYSER BOT
# Aiogram 3.7+
# =========================

import os, re, asyncio, sqlite3, hashlib
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart

import requests

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
YT_KEYS = os.getenv("YOUTUBE_API_KEYS").split(",")

# =========================
# BOT
# =========================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# =========================
# DB
# =========================
conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    credits INTEGER,
    last_reset TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS used_links(
    user_id INTEGER,
    video_id TEXT,
    PRIMARY KEY(user_id, video_id)
)
""")

conn.commit()

# =========================
# RAM CACHE
# =========================
CACHE_VIDEO = {}
CACHE_SEARCH = {}
CACHE_CHANNEL = {}

# =========================
# HELPERS
# =========================
def now_tashkent():
    return datetime.now(timezone.utc) + timedelta(hours=5)

def get_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

def yt_request(endpoint, params):
    for key in YT_KEYS:
        params["key"] = key
        r = requests.get(
            f"https://www.googleapis.com/youtube/v3/{endpoint}",
            params=params, timeout=10
        )
        if r.status_code == 200:
            return r.json()
    return None

def reset_credit_if_needed(user_id):
    cur.execute("SELECT credits,last_reset FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO users VALUES(?,?,?,?)",
            (user_id, "", 5, now_tashkent().isoformat())
        )
        conn.commit()
        return 5

    credits, last = row
    if datetime.fromisoformat(last) + timedelta(hours=24) <= now_tashkent():
        cur.execute(
            "UPDATE users SET credits=5,last_reset=? WHERE user_id=?",
            (now_tashkent().isoformat(), user_id)
        )
        conn.commit()
        return 5
    return credits

# =========================
# START
# =========================
@dp.message(CommandStart())
async def start(msg: Message):
    reset_credit_if_needed(msg.from_user.id)
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video link yuboring\n"
        "🎟 Kredit: 5/5 (har 24 soatda yangilanadi)"
    )

# =========================
# VIDEO HANDLE
# =========================
@dp.message(F.text.contains("youtu"))
async def handle_video(msg: Message):
    uid = msg.from_user.id
    reset_credit_if_needed(uid)

    vid = get_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Video topilmadi")
        return

    if uid != ADMIN_ID:
        cur.execute(
            "SELECT 1 FROM used_links WHERE user_id=? AND video_id=?",
            (uid, vid)
        )
        if not cur.fetchone():
            cur.execute(
                "UPDATE users SET credits=credits-1 WHERE user_id=?",
                (uid,)
            )
            cur.execute(
                "INSERT INTO used_links VALUES(?,?)",
                (uid, vid)
            )
            conn.commit()

    await msg.answer("⏳ Video analiz qilinmoqda...")

    data = yt_request(
        "videos",
        {"part": "snippet,statistics", "id": vid}
    )
    if not data or not data["items"]:
        await msg.answer("❌ Video topilmadi yoki API cheklangan")
        return

    v = data["items"][0]
    sn = v["snippet"]
    st = v["statistics"]

    published = datetime.fromisoformat(
        sn["publishedAt"].replace("Z", "+00:00")
    ) + timedelta(hours=5)

    like = int(st.get("likeCount", 0))
    view = int(st.get("viewCount", 0))
    comment = int(st.get("commentCount", 0))

    nakrutka = "🔴 Nakrutka ehtimoli yuqori" if view and like/view > 0.2 else "🟢 Normal"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("🧠 TOP KONKURENT NOMLAR", callback_data=f"top_titles:{vid}")
        ],
        [
            InlineKeyboardButton("🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton("📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")
        ]
    ])

    await msg.answer_photo(
        sn["thumbnails"]["high"]["url"],
        caption=
        f"🎬 <b>{sn['title']}</b>\n\n"
        f"🕒 Yuklangan: {published:%Y-%m-%d %H:%M} (Toshkent vaqti)\n"
        f"📺 Kanal: {sn['channelTitle']}\n\n"
        f"👁 {view}   ⚠️ Likelar soni🔴 {like}   💬 {comment}\n"
        f"{nakrutka}\n\n"
        f"🎟 Kredit: {reset_credit_if_needed(uid)}/5 (har 24 soatda yangilanadi)",
        reply_markup=kb
    )

# =========================
# TOP TITLES
# =========================
@dp.callback_query(F.data.startswith("top_titles"))
async def top_titles(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    await cb.message.answer("⏳ TOP nomlar olinmoqda...")

    v = yt_request("videos", {"part": "snippet", "id": vid})["items"][0]
    query = v["snippet"]["title"]

    res = yt_request(
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": (
                datetime.utcnow() - timedelta(days=30)
            ).isoformat("T") + "Z",
            "maxResults": 25
        }
    )

    titles = []
    for it in res["items"]:
        t = it["snippet"]["title"]
        if t not in titles:
            vid2 = it["id"]["videoId"]
            stat = yt_request("videos", {"part": "statistics", "id": vid2})
            views = stat["items"][0]["statistics"].get("viewCount", "0")
            titles.append(
                f"🔹 <a href='https://youtu.be/{vid2}'>{t}</a> — 👁 {views}"
            )
        if len(titles) == 10:
            break

    await cb.message.answer(
        "<b>🧠 TOP KONKURENT NOMLAR (30 kun)</b>\n\n" +
        "\n".join(titles)
    )

# =========================
# TAGS / DESC
# =========================
@dp.callback_query(F.data.startswith("tags"))
async def tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    v = yt_request("videos", {"part": "snippet", "id": vid})["items"][0]
    sn = v["snippet"]

    ch = yt_request(
        "channels",
        {
            "part": "brandingSettings",
            "id": sn["channelId"]
        }
    )["items"][0]

    await cb.message.answer(
        "<b>🏷 TAG / TAVSIF</b>\n\n"
        "<b>VIDEO TAGLARI:</b>\n"
        f"<pre>{', '.join(sn.get('tags', []))}</pre>\n\n"
        "<b>KANAL TAGLARI:</b>\n"
        f"<pre>{ch['brandingSettings']['channel'].get('keywords','')}</pre>\n\n"
        "<b>DESCRIPTION:</b>\n"
        f"<pre>{sn.get('description','')}</pre>"
    )

# =========================
# CHANNELS
# =========================
@dp.callback_query(F.data.startswith("channels"))
async def channels(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    v = yt_request("videos", {"part": "snippet", "id": vid})["items"][0]
    q = v["snippet"]["title"]

    res = yt_request(
        "search",
        {"part": "snippet", "q": q, "type": "video", "maxResults": 40}
    )

    chans = {}
    for it in res["items"]:
        cid = it["snippet"]["channelId"]
        if cid not in chans:
            chans[cid] = it["snippet"]["channelTitle"]
        if len(chans) == 10:
            break

    await cb.message.answer(
        "<b>📺 RAQOBATCHI KANALLAR (TOP)</b>\n\n" +
        "\n".join(
            f"🔗 <a href='https://youtube.com/channel/{cid}'>{name}</a>"
            for cid, name in chans.items()
        )
    )

# =========================
# RUN
# =========================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
