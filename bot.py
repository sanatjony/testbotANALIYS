import os
import re
import json
import time
import asyncio
import sqlite3
import requests
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# ================= CACHE =================
RAM_CACHE = {}   # video_id -> data
CACHE_TTL = 60 * 60 * 24  # 24 soat

# ================= DB =================
conn = sqlite3.connect("cache.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS cache (
    video_id TEXT PRIMARY KEY,
    data TEXT,
    created_at INTEGER
)
""")
conn.commit()

# ================= HELPERS =================
def extract_video_id(url):
    for p in [r"v=([A-Za-z0-9_-]{11})", r"youtu\.be/([A-Za-z0-9_-]{11})"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"{YOUTUBE_API}/{endpoint}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def cache_get(video_id):
    now = int(time.time())

    # RAM
    if video_id in RAM_CACHE:
        data, ts = RAM_CACHE[video_id]
        if now - ts < CACHE_TTL:
            return data

    # DB
    cur.execute("SELECT data, created_at FROM cache WHERE video_id=?", (video_id,))
    row = cur.fetchone()
    if row and now - row[1] < CACHE_TTL:
        data = json.loads(row[0])
        RAM_CACHE[video_id] = (data, row[1])
        return data

    return None


def cache_set(video_id, data):
    ts = int(time.time())
    RAM_CACHE[video_id] = (data, ts)
    cur.execute(
        "REPLACE INTO cache(video_id, data, created_at) VALUES(?,?,?)",
        (video_id, json.dumps(data), ts)
    )
    conn.commit()

# ================= CORE ANALYSIS =================
def analyze_video(video_id):
    # video info
    v = yt("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })["items"]

    if not v:
        return None

    video = v[0]
    title = video["snippet"]["title"]
    keyword = title.split("|")[0].split("-")[0][:60]

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()

    search = yt("search", {
        "part": "snippet",
        "type": "video",
        "q": keyword,
        "order": "viewCount",
        "maxResults": 15,
        "publishedAfter": published_after
    })["items"]

    competitors = []
    channels = {}
    used = set()

    for it in search:
        vid = it["id"]["videoId"]
        t = it["snippet"]["title"]

        if t.lower() in used:
            continue
        used.add(t.lower())

        stats = yt("videos", {
            "part": "statistics",
            "id": vid
        })["items"]

        if not stats:
            continue

        views = int(stats[0]["statistics"].get("viewCount", 0))
        competitors.append({"title": t, "views": views})

        ch = it["snippet"]["channelTitle"]
        channels[ch] = channels.get(ch, 0) + 1

        if len(competitors) >= 10:
            break

    competitors.sort(key=lambda x: x["views"], reverse=True)

    return {
        "video_title": title,
        "views": video["statistics"].get("viewCount"),
        "likes": video["statistics"].get("likeCount"),
        "comments": video["statistics"].get("commentCount"),
        "keyword": keyword,
        "competitors": competitors,
        "channels": sorted(channels.items(), key=lambda x: x[1], reverse=True)[:5]
    }

# ================= HANDLERS =================
@dp.message(CommandStart())
async def start(msg: Message):
    await msg.answer(
        "👋 Salom!\n\n"
        "YouTube video linkini yuboring.\n\n"
        "⚡ Juda tez ishlaydi\n"
        "📉 Limitni tejaydi\n"
        "🧠 Cache bilan"
    )


@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        return await msg.answer("❌ Link noto‘g‘ri.")

    cached = cache_get(vid)
    if cached:
        data = cached
    else:
        wait = await msg.answer("⏳ Video analiz qilinmoqda...")
        try:
            data = await asyncio.to_thread(analyze_video, vid)
        except Exception:
            return await wait.edit_text("❌ API vaqtincha cheklangan.")

        if not data:
            return await wait.edit_text("❌ Video topilmadi.")

        cache_set(vid, data)
        await wait.delete()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"titles:{vid}"),
            InlineKeyboardButton(text="🏷 TOP TAGLAR", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton(text="📺 Raqobatchi kanallar", callback_data=f"channels:{vid}")
        ]
    ])

    await msg.answer(
        f"🎬 {data['video_title']}\n\n"
        f"👁 {data['views']} | 👍 {data['likes']} | 💬 {data['comments']}",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("titles:"))
async def cb_titles(cb):
    vid = cb.data.split(":")[1]
    data = cache_get(vid)

    text = "🧠 TOP KONKURENT NOMLAR (30 kun):\n\n"
    for i, c in enumerate(data["competitors"], 1):
        text += f"{i}. {c['title']}\n👁 {c['views']:,}\n\n"

    await cb.message.answer(text)


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb):
    vid = cb.data.split(":")[1]
    data = cache_get(vid)

    tags = [
        data["keyword"],
        "viral",
        "challenge",
        "gameplay",
        "trending",
        "youtube shorts"
    ]

    await cb.message.answer("🏷 TOP TAGLAR:\n\n" + ", ".join(dict.fromkeys(tags)))


@dp.callback_query(F.data.startswith("channels:"))
async def cb_channels(cb):
    vid = cb.data.split(":")[1]
    data = cache_get(vid)

    text = "📺 RAQOBATCHI KANALLAR:\n\n"
    for i, (c, n) in enumerate(data["channels"], 1):
        text += f"{i}. {c} — {n} video\n"

    await cb.message.answer(text)

# ================= RUN =================
async def main():
    print("🤖 BOT ishga tushdi (CACHE ON)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
