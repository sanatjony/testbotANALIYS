import os, re, sqlite3, asyncio, time, json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, InputMediaPhoto
)
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEYS = os.getenv("YOUTUBE_API_KEYS", "").split(",")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================== DB ==================
db = sqlite3.connect("cache.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS video_cache (
    video_id TEXT PRIMARY KEY,
    data TEXT,
    ts INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS search_cache (
    key TEXT PRIMARY KEY,
    data TEXT,
    ts INTEGER
)
""")

db.commit()

# ================== RAM CACHE ==================
RAM_VIDEO: Dict[str, Dict] = {}
RAM_SEARCH: Dict[str, Dict] = {}

CACHE_TTL = 60 * 60  # 1 soat

# ================== HELPERS ==================
def btn(text, cb):
    return InlineKeyboardButton(text=text, callback_data=cb)

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def now_ts():
    return int(time.time())

def extract_video_id(url: str) -> str | None:
    m = re.search(r"(v=|be/)([\w\-]{11})", url)
    return m.group(2) if m else None

def yt_request(endpoint: str, params: dict):
    last_err = None
    for key in API_KEYS:
        try:
            params["key"] = key
            r = requests.get(
                f"https://www.googleapis.com/youtube/v3/{endpoint}",
                params=params,
                timeout=10
            )
            if r.status_code == 200:
                return r.json()
            last_err = r.text
        except Exception as e:
            last_err = str(e)
    raise Exception(f"YouTube API error: {last_err}")

# ================== CACHE ==================
def cache_get(table: str, key: str):
    cur.execute(f"SELECT data, ts FROM {table} WHERE key=?",(key,))
    row = cur.fetchone()
    if not row:
        return None
    data, ts = row
    if now_ts() - ts > CACHE_TTL:
        return None
    return json.loads(data)

def cache_set(table: str, key: str, data: dict):
    cur.execute(
        f"REPLACE INTO {table} VALUES (?,?,?)",
        (key, json.dumps(data), now_ts())
    )
    db.commit()

# ================== ANALYTICS ==================
def nakrutka_flag(likes: int, views: int) -> str:
    if views == 0:
        return ""
    ratio = likes / views
    if ratio > 0.5:
        return "🔴 Nakrutka ehtimoli yuqori"
    return "🟢 Normal"

# ================== VIDEO ==================
def get_video(video_id: str) -> dict:
    if video_id in RAM_VIDEO:
        return RAM_VIDEO[video_id]

    cur.execute("SELECT data, ts FROM video_cache WHERE video_id=?", (video_id,))
    row = cur.fetchone()
    if row and now_ts() - row[1] < CACHE_TTL:
        data = json.loads(row[0])
        RAM_VIDEO[video_id] = data
        return data

    js = yt_request("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })

    if not js["items"]:
        raise Exception("Video topilmadi")

    it = js["items"][0]
    data = {
        "id": video_id,
        "title": it["snippet"]["title"],
        "desc": it["snippet"].get("description",""),
        "thumb": it["snippet"]["thumbnails"]["high"]["url"],
        "published": it["snippet"]["publishedAt"],
        "views": int(it["statistics"].get("viewCount",0)),
        "likes": int(it["statistics"].get("likeCount",0)),
        "comments": int(it["statistics"].get("commentCount",0)),
        "channel": it["snippet"]["channelTitle"]
    }

    RAM_VIDEO[video_id] = data
    cur.execute(
        "REPLACE INTO video_cache VALUES (?,?,?)",
        (video_id, json.dumps(data), now_ts())
    )
    db.commit()
    return data

# ================== SEARCH ==================
def search_videos(q: str, days: int, max_res=10):
    key = f"{q}:{days}"
    if key in RAM_SEARCH:
        return RAM_SEARCH[key]

    cached = cache_get("search_cache", key)
    if cached:
        RAM_SEARCH[key] = cached
        return cached

    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    js = yt_request("search", {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": max_res,
        "publishedAfter": published_after,
        "order": "viewCount"
    })

    vids = []
    for it in js.get("items", []):
        vids.append({
            "title": it["snippet"]["title"],
            "vid": it["id"]["videoId"]
        })

    cache_set("search_cache", key, vids)
    RAM_SEARCH[key] = vids
    return vids

# ================== HANDLERS ==================
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "👋 <b>Salom!</b>\n"
        "YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR\n"
        "🏷 TAG / TAVSIF\n"
        "📊 KONKURENT ANALIZ\n"
        "ni chiqarib beraman."
    )

@dp.message(F.text)
async def handle_video(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        return

    msg = await m.answer("⏳ Video analiz qilinmoqda...")

    try:
        data = await asyncio.to_thread(get_video, vid)
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")
        return

    nak = nakrutka_flag(data["likes"], data["views"])

    text = (
        f"🎬 <b>{data['title']}</b>\n\n"
        f"🕒 Yuklangan: {data['published'][:10]} (Toshkent vaqti)\n"
        f"📺 Kanal: {data['channel']}\n\n"
        f"👁 {data['views']}   👍 {data['likes']}   💬 {data['comments']}\n"
        f"{nak}"
    )

    keyboard = kb([
        [btn("🧠 TOP NOMLAR", f"title:{vid}")],
        [btn("🏷 TAG / TAVSIF", f"tags:{vid}")],
        [btn("📺 Raqobatchi kanallar", f"comp:{vid}")]
    ])

    await msg.delete()
    await m.answer_photo(
        photo=data["thumb"],
        caption=text,
        reply_markup=keyboard
    )

# ================== CALLBACKS ==================
@dp.callback_query(F.data.startswith("title:"))
async def cb_titles(c: CallbackQuery):
    vid = c.data.split(":")[1]
    data = get_video(vid)
    q = data["title"]

    await c.message.answer("⏳ TOP nomlar olinmoqda...")

    res = await asyncio.to_thread(search_videos, q, 30, 10)

    lines = []
    used = set()
    for r in res:
        t = r["title"]
        if t.lower() in used:
            continue
        used.add(t.lower())
        lines.append(f"• {t}")
        if len(lines) == 10:
            break

    if not lines:
        await c.message.answer("⚠️ Yetarli nom topilmadi.")
        return

    await c.message.answer(
        "<b>🧠 TOP KONKURENT NOMLAR (30 kun):</b>\n\n" + "\n".join(lines)
    )

@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    data = get_video(vid)

    tags = re.findall(r"\w+", data["title"].lower())
    tags = list(dict.fromkeys(tags))[:20]

    text = (
        "<b>🏷 Video taglari:</b>\n"
        + ", ".join(tags)
        + "\n\n<b>🏷 Kanal taglari:</b>\n"
        + ", ".join(tags[:10])
        + "\n\n<b>📝 Description:</b>\n"
        + data["desc"][:500]
    )

    await c.message.answer(text)

@dp.callback_query(F.data.startswith("comp:"))
async def cb_comp(c: CallbackQuery):
    vid = c.data.split(":")[1]
    data = get_video(vid)

    await c.message.answer("⏳ Raqobatchi kanallar analiz qilinmoqda...")

    res = await asyncio.to_thread(search_videos, data["title"], 60, 15)

    chans = {}
    for r in res:
        chans.setdefault(r["vid"], 0)
        chans[r["vid"]] += 1

    out = []
    for i, k in enumerate(list(chans.keys())[:10], 1):
        out.append(f"{i}. {k}")

    await c.message.answer(
        "<b>📺 RAQOBATCHI KANALLAR (TOP):</b>\n" + "\n".join(out)
    )

# ================== RUN ==================
async def main():
    print("🤖 BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
