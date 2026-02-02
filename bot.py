import os
import re
import time
import sqlite3
import asyncio
import requests
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart

# =======================
# CONFIG
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YT_API_KEY = os.getenv("YOUTUBE_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

TZ_TASHKENT = timezone(timedelta(hours=5))

# =======================
# BOT INIT (aiogram 3.x)
# =======================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# =======================
# RAM CACHE
# =======================
RAM_CACHE = {}
CACHE_TTL = 1800  # 30 min

def cache_get(key):
    data = RAM_CACHE.get(key)
    if not data:
        return None
    if time.time() - data["time"] > CACHE_TTL:
        del RAM_CACHE[key]
        return None
    return data["value"]

def cache_set(key, value):
    RAM_CACHE[key] = {"time": time.time(), "value": value}

# =======================
# SQLITE DB
# =======================
conn = sqlite3.connect("data.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT,
    ts INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS requests (
    username TEXT,
    video_url TEXT,
    ts INTEGER
)
""")

conn.commit()

def db_get(key):
    cur.execute("SELECT value, ts FROM cache WHERE key=?", (key,))
    row = cur.fetchone()
    if not row:
        return None
    if time.time() - row[1] > CACHE_TTL:
        return None
    return eval(row[0])

def db_set(key, value):
    cur.execute(
        "REPLACE INTO cache VALUES (?, ?, ?)",
        (key, repr(value), int(time.time()))
    )
    conn.commit()

# =======================
# YOUTUBE HELPERS
# =======================
def extract_video_id(url: str):
    patterns = [
        r"v=([^&]+)",
        r"youtu\.be/([^?]+)",
        r"youtube\.com/shorts/([^?]+)"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt_api(endpoint, params):
    params["key"] = YT_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=8
    )
    r.raise_for_status()
    return r.json()

# =======================
# VIDEO DATA
# =======================
def get_video(video_id):
    cache_key = f"video:{video_id}"

    # RAM
    data = cache_get(cache_key)
    if data:
        return data

    # DB
    data = db_get(cache_key)
    if data:
        cache_set(cache_key, data)
        return data

    # API
    res = yt_api("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })

    if not res["items"]:
        return None

    v = res["items"][0]
    snippet = v["snippet"]
    stats = v["statistics"]

    published = datetime.fromisoformat(
        snippet["publishedAt"].replace("Z", "+00:00")
    ).astimezone(TZ_TASHKENT)

    data = {
        "title": snippet["title"],
        "channel": snippet["channelTitle"],
        "published": published.strftime("%d.%m.%Y %H:%M (Toshkent)"),
        "category": snippet.get("categoryId"),
        "tags": snippet.get("tags", []),
        "description": snippet.get("description", ""),
        "thumb": snippet["thumbnails"]["high"]["url"],
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0))
    }

    cache_set(cache_key, data)
    db_set(cache_key, data)
    return data

# =======================
# NAKRUTKA CHECK
# =======================
def check_nakrutka(views, likes):
    if views == 0:
        return "⚪ Maʼlumot yetarli emas"
    ratio = likes / views
    if ratio > 0.25:
        return "🔴 Nakrutka ehtimoli yuqori"
    elif ratio > 0.1:
        return "🟡 Shubhali"
    return "🟢 Normal"

# =======================
# START
# =======================
@dp.message(CommandStart())
async def start(msg: types.Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP nomlar\n"
        "🏷 TAG/TAVSIF\n"
        "🖥 Raqobatchi kanallar\n"
        "📊 Analiz\n"
        "chiqarib beraman."
    )

# =======================
# HANDLE VIDEO LINK
# =======================
@dp.message()
async def handle(msg: types.Message):
    vid = extract_video_id(msg.text or "")
    if not vid:
        return

    await msg.answer("⏳ Video analiz qilinmoqda...")

    data = await asyncio.to_thread(get_video, vid)
    if not data:
        await msg.answer("❌ Video topilmadi yoki API vaqtincha cheklangan.")
        return

    # SAVE REQUEST
    if msg.from_user:
        cur.execute(
            "INSERT INTO requests VALUES (?, ?, ?)",
            (msg.from_user.username, msg.text, int(time.time()))
        )
        conn.commit()

    nak = check_nakrutka(data["views"], data["likes"])

    text = (
        f"<b>{data['title']}</b>\n\n"
        f"🕒 Yuklangan: {data['published']}\n"
        f"📺 Kanal: {data['channel']}\n\n"
        f"📊 <b>Video statistikasi</b>\n"
        f"👁 View: {data['views']}\n"
        f"👍 Like: {data['likes']}\n"
        f"💬 Comment: {data['comments']}\n\n"
        f"⚠️ {nak}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"title:{vid}"),
            InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton(text="🖥 Raqobatchi kanallar", callback_data=f"comp:{vid}")
        ]
    ])

    await msg.answer_photo(
        photo=data["thumb"],
        caption=text,
        reply_markup=kb
    )

# =======================
# TAG / DESCRIPTION
# =======================
@dp.callback_query(lambda c: c.data.startswith("tags:"))
async def tags_cb(c: types.CallbackQuery):
    vid = c.data.split(":")[1]
    data = cache_get(f"video:{vid}") or db_get(f"video:{vid}")

    text = (
        "<b>🏷 Video taglari:</b>\n<code>"
        + ", ".join(data["tags"][:40]) +
        "</code>\n\n"
        "<b>📝 Description:</b>\n<code>"
        + data["description"][:3500] +
        "</code>"
    )
    await c.message.answer(text)

# =======================
# TOP TITLES (SIMPLIFIED SAFE)
# =======================
@dp.callback_query(lambda c: c.data.startswith("title:"))
async def title_cb(c: types.CallbackQuery):
    vid = c.data.split(":")[1]
    data = cache_get(f"video:{vid}") or db_get(f"video:{vid}")

    base = data["title"].split("|")[0].strip()

    titles = [
        f"{base} 😱 INSANE Result!",
        f"{base} 🔥 You Won’t Believe This!",
        f"{base} 💥 CRAZY Moment",
        f"{base} 😮 Unexpected Outcome",
        f"{base} 🚗 Most Satisfying Video"
    ]

    text = "<b>🧠 TOP CLICKBAIT NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await c.message.answer(text)

# =======================
# COMPETITORS (SEARCH)
# =======================
@dp.callback_query(lambda c: c.data.startswith("comp:"))
async def comp_cb(c: types.CallbackQuery):
    vid = c.data.split(":")[1]
    data = cache_get(f"video:{vid}") or db_get(f"video:{vid}")

    q = data["title"].split("|")[0]

    res = yt_api("search", {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": 10,
        "order": "viewCount"
    })

    channels = {}
    for it in res["items"]:
        ch = it["snippet"]["channelTitle"]
        channels[ch] = channels.get(ch, 0) + 1

    text = "<b>🖥 RAQOBATCHI KANALLAR (TOP):</b>\n\n"
    for i, (ch, cnt) in enumerate(sorted(channels.items(), key=lambda x: -x[1])[:10], 1):
        text += f"{i}. {ch} — {cnt} video\n"

    await c.message.answer(text)

# =======================
# ADMIN EXPORT
# =======================
async def admin_export():
    if ADMIN_ID == 0:
        return
    cur.execute("SELECT * FROM requests")
    rows = cur.fetchall()
    if not rows:
        return

    content = ""
    for r in rows:
        content += f"{r[0]} | {r[1]} | {datetime.fromtimestamp(r[2])}\n"

    with open("export.txt", "w", encoding="utf-8") as f:
        f.write(content)

    await bot.send_document(ADMIN_ID, types.FSInputFile("export.txt"))

# =======================
# RUN
# =======================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
