import os
import re
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================= CACHE =================
CACHE = {}
CACHE_TTL = 1800  # 30 min

def now():
    return int(datetime.now(tz=timezone.utc).timestamp())

def cache_get(key):
    if key not in CACHE:
        return None
    data, ts = CACHE[key]
    if now() - ts > CACHE_TTL:
        del CACHE[key]
        return None
    return data

def cache_set(key, val):
    CACHE[key] = (val, now())

# ================= YOUTUBE =================
def extract_video_id(url: str):
    for p in [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"shorts/([a-zA-Z0-9_-]{11})",
    ]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt(endpoint, params):
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        return None
    return r.json()

def get_video(video_id):
    ck = f"video:{video_id}"
    cached = cache_get(ck)
    if cached:
        return cached

    data = yt("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })
    if not data or not data.get("items"):
        return None

    item = data["items"][0]
    cache_set(ck, item)
    return item

# ================= UI =================
def main_keyboard(video_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP KONKURENT NOMLAR",
                    callback_data=f"top_titles:{video_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏷 TAG / TAVSIF",
                    callback_data=f"tags_desc:{video_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📺 Raqobatchi kanallar",
                    callback_data=f"competitors:{video_id}"
                )
            ]
        ]
    )

# ================= START =================
@dp.message(F.text == "/start")
async def start(m: Message):
    await m.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video linkini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP konkurent nomlar (30 kun)\n"
        "🏷 TAG / TAVSIF\n"
        "📺 Raqobatchi kanallarni chiqaraman."
    )

# ================= VIDEO =================
@dp.message(F.text.contains("youtu"))
async def handle_video(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        await m.answer("❌ Video ID topilmadi.")
        return

    await m.answer("⏳ Video analiz qilinmoqda...")

    video = await asyncio.to_thread(get_video, vid)
    if not video:
        await m.answer("❌ Video topilmadi yoki API vaqtincha cheklangan.")
        return

    sn = video["snippet"]
    st = video["statistics"]

    text = (
        f"🎬 <b>{sn['title']}</b>\n\n"
        f"👁 {st.get('viewCount','0')}   "
        f"👍 {st.get('likeCount','0')}   "
        f"💬 {st.get('commentCount','0')}"
    )

    await m.answer(text, reply_markup=main_keyboard(vid))

# ================= TOP TITLES =================
@dp.callback_query(F.data.startswith("top_titles"))
async def top_titles(cb: CallbackQuery):
    await cb.answer("⏳ Konkurent nomlar olinmoqda...")

    vid = cb.data.split(":")[1]
    video = get_video(vid)
    if not video:
        await cb.message.answer("❌ Video topilmadi.")
        return

    base_q = video["snippet"]["title"].split("|")[0]

    after = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()

    search = yt("search", {
        "part": "snippet",
        "q": base_q,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": after,
        "maxResults": 15
    })

    if not search or not search.get("items"):
        await cb.message.answer("⚠️ O‘xshash konkurent nomlar topilmadi.")
        return

    used = set()
    results = []

    for it in search["items"]:
        title = it["snippet"]["title"]
        if title.lower() in used:
            continue
        used.add(title.lower())

        vid_id = it["id"]["videoId"]
        v = yt("videos", {
            "part": "statistics",
            "id": vid_id
        })
        if not v or not v.get("items"):
            continue

        views = int(v["items"][0]["statistics"].get("viewCount", 0))
        results.append((title, views))
        if len(results) >= 10:
            break

    txt = "🧠 <b>OXIRGI 30 KUN — TOP KONKURENT NOMLAR:</b>\n\n"
    for i, (t, v) in enumerate(results, 1):
        txt += f"{i}. {t}\n👁 {v:,}\n\n"

    await cb.message.answer(txt)

# ================= TAG / DESCRIPTION =================
@dp.callback_query(F.data.startswith("tags_desc"))
async def tags_desc(cb: CallbackQuery):
    await cb.answer("⏳ Taglar va tavsif olinmoqda...")

    vid = cb.data.split(":")[1]
    video = get_video(vid)
    if not video:
        await cb.message.answer("❌ Video topilmadi.")
        return

    title = video["snippet"]["title"].lower()
    desc = video["snippet"].get("description", "")

    video_tags = set(re.findall(r"\b[a-zA-Z]{4,}\b", title))
    channel_tags = set(video_tags)

    txt = (
        "🏷 <b>Video taglari:</b>\n"
        f"<code>{', '.join(sorted(video_tags))}</code>\n\n"
        "📌 <b>Kanal taglari:</b>\n"
        f"<code>{', '.join(sorted(channel_tags))}</code>\n\n"
        "📝 <b>Video description:</b>\n"
        f"<code>{desc[:3500]}</code>"
    )

    await cb.message.answer(txt)

# ================= COMPETITORS =================
@dp.callback_query(F.data.startswith("competitors"))
async def competitors(cb: CallbackQuery):
    await cb.answer("⏳ Raqobatchi kanallar analiz qilinmoqda...")

    vid = cb.data.split(":")[1]
    video = get_video(vid)
    if not video:
        await cb.message.answer("❌ Video topilmadi.")
        return

    q = video["snippet"]["title"].split("|")[0]

    search = yt("search", {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": 20
    })

    channels = defaultdict(int)
    for it in search.get("items", []):
        channels[it["snippet"]["channelTitle"]] += 1

    txt = "📺 <b>RAQOBATCHI KANALLAR (TOP):</b>\n\n"
    for i, (ch, c) in enumerate(
        sorted(channels.items(), key=lambda x: x[1], reverse=True)[:10], 1
    ):
        txt += f"{i}. {ch} — {c} video\n"

    await cb.message.answer(txt)

# ================= RUN =================
async def main():
    print("🤖 BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
