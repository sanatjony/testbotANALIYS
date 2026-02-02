import os, re, sqlite3, asyncio, time, json
from datetime import datetime, timedelta, timezone

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEYS = os.getenv("YOUTUBE_API_KEYS", "").split(",")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

TZ_TASHKENT = timezone(timedelta(hours=5))

# ================= CATEGORY MAP =================
CATEGORY_MAP = {
    "20": ("Gaming", "Игры", "O‘yinlar"),
    "24": ("Entertainment", "Развлечения", "Ko‘ngilochar"),
    "22": ("People & Blogs", "Люди и блоги", "Bloglar"),
    "10": ("Music", "Музыка", "Musiqa"),
}

# ================= DB + RAM =================
db = sqlite3.connect("cache.db", check_same_thread=False)
cur = db.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    data TEXT,
    ts INTEGER
)
""")
db.commit()

RAM = {}
CACHE_TTL = 3600

def cache_get(key):
    if key in RAM:
        return RAM[key]
    cur.execute("SELECT data, ts FROM cache WHERE key=?", (key,))
    r = cur.fetchone()
    if not r or time.time() - r[1] > CACHE_TTL:
        return None
    data = json.loads(r[0])
    RAM[key] = data
    return data

def cache_set(key, data):
    RAM[key] = data
    cur.execute(
        "REPLACE INTO cache VALUES (?,?,?)",
        (key, json.dumps(data), int(time.time()))
    )
    db.commit()

# ================= YT HELPERS =================
def yt(endpoint, params):
    for k in API_KEYS:
        try:
            params["key"] = k
            r = requests.get(
                f"https://www.googleapis.com/youtube/v3/{endpoint}",
                params=params,
                timeout=10
            )
            if r.status_code == 200:
                return r.json()
        except:
            pass
    raise Exception("YouTube API error")

def extract_video_id(url):
    m = re.search(r"(v=|be/)([\w\-]{11})", url)
    return m.group(2) if m else None

def tashkent_time(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(TZ_TASHKENT).strftime("%d.%m.%Y %H:%M")

# ================= NAKRUTKA =================
def like_nakrutka(views, likes):
    if views == 0:
        return "⚪ Maʼlumot yetarli emas"
    r = likes / views
    if r > 0.3:
        return "🔴 Nakrutka ehtimoli yuqori"
    if r > 0.15:
        return "🟡 Shubhali"
    return "🟢 Normal"

# ================= VIDEO =================
def get_video(video_id):
    key = f"video:{video_id}"
    cached = cache_get(key)
    if cached:
        return cached

    js = yt("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })
    it = js["items"][0]

    cat_id = it["snippet"].get("categoryId")
    cat = CATEGORY_MAP.get(cat_id, ("—", "—", "—"))

    data = {
        "id": video_id,
        "title": it["snippet"]["title"],
        "desc": it["snippet"].get("description", ""),
        "thumb": it["snippet"]["thumbnails"]["high"]["url"],
        "published": tashkent_time(it["snippet"]["publishedAt"]),
        "views": int(it["statistics"].get("viewCount", 0)),
        "likes": int(it["statistics"].get("likeCount", 0)),
        "comments": int(it["statistics"].get("commentCount", 0)),
        "channel": it["snippet"]["channelTitle"],
        "category": cat
    }

    cache_set(key, data)
    return data

# ================= SEARCH =================
def search_top_videos(query, days=30, limit=25):
    key = f"search:{query}:{days}"
    cached = cache_get(key)
    if cached:
        return cached

    after = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

    js = yt("search", {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",
        "maxResults": limit,
        "publishedAfter": after
    })

    ids = [i["id"]["videoId"] for i in js["items"]]
    if not ids:
        return []

    stats = yt("videos", {
        "part": "statistics,snippet",
        "id": ",".join(ids)
    })

    out = []
    for v in stats["items"]:
        out.append({
            "title": v["snippet"]["title"],
            "views": int(v["statistics"].get("viewCount", 0))
        })

    cache_set(key, out)
    return out

# ================= BOT =================
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("🎬 YouTube video linkini yuboring")

@dp.message(F.text)
async def handle(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        return

    msg = await m.answer("⏳ Analiz qilinmoqda...")
    data = await asyncio.to_thread(get_video, vid)

    nak = like_nakrutka(data["views"], data["likes"])
    cat = data["category"]

    text = (
        f"🎬 <b>{data['title']}</b>\n\n"
        f"🕒 Yuklangan: {data['published']} (Toshkent vaqti)\n"
        f"📺 Kanal: {data['channel']}\n"
        f"📂 Kategoriya:\n"
        f"🇬🇧 {cat[0]} / 🇷🇺 {cat[1]} / 🇺🇿 {cat[2]}\n\n"
        f"👁 {data['views']}   👍 {data['likes']}   💬 {data['comments']}\n"
        f"⚠️ Likelar soni {nak}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP KONKURENT NOMLAR", callback_data=f"title:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"chan:{vid}")]
    ])

    await msg.edit_text(text, reply_markup=kb)

# ================= CALLBACKS =================
@dp.callback_query(F.data.startswith("title:"))
async def cb_titles(c: CallbackQuery):
    vid = c.data.split(":")[1]
    data = get_video(vid)

    res = await asyncio.to_thread(search_top_videos, data["title"], 30, 25)

    lines = [
        f"{i+1}. {r['title']}\n👁 {r['views']:,}"
        for i, r in enumerate(res)
    ]

    await c.message.answer(
        "<b>🧠 TOP KONKURENT NOMLAR (30 kun)</b>\n\n" + "\n\n".join(lines)
    )

@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    d = get_video(vid)

    words = list(dict.fromkeys(re.findall(r"\w+", d["title"].lower())))

    await c.message.answer(
        "<b>🏷 Video taglari</b>\n<pre>" + ", ".join(words[:25]) + "</pre>\n\n"
        "<b>🏷 Kanal taglari</b>\n<pre>" + ", ".join(words[:15]) + "</pre>\n\n"
        "<b>📝 Description</b>\n<pre>" + d["desc"][:800] + "</pre>"
    )

@dp.callback_query(F.data.startswith("chan:"))
async def cb_channels(c: CallbackQuery):
    vid = c.data.split(":")[1]
    d = get_video(vid)

    js = yt("search", {
        "part": "snippet",
        "q": d["title"],
        "type": "video",
        "maxResults": 15
    })

    channel_ids = list({i["snippet"]["channelId"] for i in js["items"]})

    ch_js = yt("channels", {
        "part": "snippet",
        "id": ",".join(channel_ids)
    })

    names = [i["snippet"]["title"] for i in ch_js["items"]]

    out = [f"{i+1}. {name}" for i, name in enumerate(names[:10])]

    await c.message.answer(
        "<b>📺 RAQOBATCHI KANALLAR (TOP)</b>\n\n" + "\n".join(out)
    )

# ================= RUN =================
async def main():
    print("🤖 BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
