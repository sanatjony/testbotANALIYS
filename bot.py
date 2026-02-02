import os, re, sqlite3, asyncio, time, json
from datetime import datetime, timedelta, timezone
import requests

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEYS = [k.strip() for k in os.getenv("YOUTUBE_API_KEYS","").split(",") if k.strip()]

TZ_TASHKENT = timezone(timedelta(hours=5))

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

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
    dt = datetime.fromisoformat(iso.replace("Z","+00:00"))
    return dt.astimezone(TZ_TASHKENT).strftime("%d.%m.%Y %H:%M")

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

    data = {
        "id": video_id,
        "title": it["snippet"]["title"],
        "desc": it["snippet"].get("description",""),
        "thumb": it["snippet"]["thumbnails"]["high"]["url"],
        "published": tashkent_time(it["snippet"]["publishedAt"]),
        "views": int(it["statistics"].get("viewCount",0)),
        "likes": int(it["statistics"].get("likeCount",0)),
        "comments": int(it["statistics"].get("commentCount",0)),
        "channel": it["snippet"]["channelTitle"]
    }

    cache_set(key, data)
    return data

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

    text = (
        f"🎬 <b>{data['title']}</b>\n\n"
        f"🕒 Yuklangan: {data['published']} (Toshkent vaqti)\n"
        f"📺 Kanal: {data['channel']}\n\n"
        f"👁 {data['views']}   👍 {data['likes']}   💬 {data['comments']}\n"
        f"⚠️ Likelar soni {nak}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"comp:{vid}")]
    ])

    await msg.edit_text(text, reply_markup=kb)

# ================= CALLBACK: COMPETITORS =================
@dp.callback_query(F.data.startswith("comp:"))
async def cb_comp(c: CallbackQuery):
    vid = c.data.split(":")[1]
    data = get_video(vid)

    cache_key = f"competitors:{vid}"
    cached = cache_get(cache_key)
    if cached:
        await c.message.answer(cached)
        return

    js = yt("search", {
        "part": "snippet",
        "q": data["title"],
        "type": "video",
        "maxResults": 20
    })

    channel_ids = []
    for i in js["items"]:
        cid = i["snippet"]["channelId"]
        if cid not in channel_ids:
            channel_ids.append(cid)
        if len(channel_ids) == 10:
            break

    ch_js = yt("channels", {
        "part": "snippet",
        "id": ",".join(channel_ids)
    })

    lines = []
    for i, ch in enumerate(ch_js["items"], 1):
        name = ch["snippet"]["title"]
        cid = ch["id"]
        url = f"https://www.youtube.com/channel/{cid}"
        lines.append(f"{i}. {name}\n🔗 {url}")

    text = "<b>📺 RAQOBATCHI KANALLAR (TOP)</b>\n\n" + "\n\n".join(lines)

    cache_set(cache_key, text)
    await c.message.answer(text)

# ================= RUN =================
async def main():
    print("🤖 BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
