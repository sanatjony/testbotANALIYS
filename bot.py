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

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================== SIMPLE RAM CACHE ==================
CACHE = {}
CACHE_TTL = 60 * 30  # 30 minut

def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    data, ts = item
    if time_now() - ts > CACHE_TTL:
        del CACHE[key]
        return None
    return data

def cache_set(key, value):
    CACHE[key] = (value, time_now())

def time_now():
    return int(datetime.now(tz=timezone.utc).timestamp())

# ================== YOUTUBE HELPERS ==================
def extract_video_id(url: str):
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"shorts/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt_api(endpoint, params):
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        return None
    return r.json()

# ================== ANALYSIS ==================
def get_video(video_id):
    cached = cache_get(f"video:{video_id}")
    if cached:
        return cached

    data = yt_api("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })
    if not data or not data.get("items"):
        return None

    item = data["items"][0]
    cache_set(f"video:{video_id}", item)
    return item

def nakrutka_check(views, likes):
    if views == 0:
        return False
    ratio = (likes / views) * 100
    return ratio > 50  # juda agressiv

def build_keyboard(video_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP NOMLAR",
                    callback_data=f"top_titles:{video_id}"
                ),
                InlineKeyboardButton(
                    text="🏷 TOP TAGLAR",
                    callback_data=f"top_tags:{video_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📺 Raqobatchi kanallar",
                    callback_data=f"competitors:{video_id}"
                )
            ]
        ]
    )

# ================== START ==================
@dp.message(F.text == "/start")
async def start(m: Message):
    await m.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n"
        "Men sizga:\n"
        "🧠 TOP nomlar\n"
        "🏷 TOP taglar\n"
        "📺 Raqobatchi kanallarni chiqaraman."
    )

# ================== VIDEO HANDLE ==================
@dp.message(F.text.contains("youtu"))
async def handle_video(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        await m.answer("❌ Video ID topilmadi.")
        return

    await m.answer("⏳ Video analiz qilinmoqda...")

    item = await asyncio.to_thread(get_video, vid)
    if not item:
        await m.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    sn = item["snippet"]
    st = item["statistics"]

    views = int(st.get("viewCount", 0))
    likes = int(st.get("likeCount", 0))
    comments = int(st.get("commentCount", 0))

    nak = nakrutka_check(views, likes)

    text = (
        f"🎬 <b>{sn['title']}</b>\n\n"
        f"📅 Yuklangan: {sn['publishedAt'][:10]}\n\n"
        f"📊 <b>Video statistikasi</b>\n"
        f"👁 View: {views}\n"
        f"👍 Like: {likes}\n"
        f"💬 Comment: {comments}\n\n"
        f"💰 Monetizatsiya: "
        f"{'🔴 Nakrutka ehtimoli yuqori' if nak else '🟢 Normal'}"
    )

    await m.answer(
        text,
        reply_markup=build_keyboard(vid)
    )

# ================== TOP TITLES ==================
@dp.callback_query(F.data.startswith("top_titles"))
async def top_titles(cb: CallbackQuery):
    await cb.answer("⏳ TOP nomlar olinmoqda...", show_alert=False)

    vid = cb.data.split(":")[1]
    video = get_video(vid)
    if not video:
        await cb.message.answer("❌ Maʼlumot topilmadi.")
        return

    base = video["snippet"]["title"]
    core = base.split("|")[0].strip()

    titles = [
        f"{core} 😱 INSANE Result!",
        f"{core} 🔥 You Won’t Believe This!",
        f"{core} 💥 CRAZY Experiment",
        f"{core} 🤯 Unexpected Outcome",
        f"{core} 🚗 Most Satisfying Video",
    ]

    txt = "🧠 <b>ANALIZ ASOSIDA TOP NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        txt += f"{i}. {t}\n"

    await cb.message.answer(txt)

# ================== TOP TAGS ==================
@dp.callback_query(F.data.startswith("top_tags"))
async def top_tags(cb: CallbackQuery):
    await cb.answer("⏳ TOP taglar olinmoqda...", show_alert=False)

    vid = cb.data.split(":")[1]
    video = get_video(vid)
    if not video:
        await cb.message.answer("❌ Maʼlumot topilmadi.")
        return

    title = video["snippet"]["title"].lower()

    tags = set()
    if "mcqueen" in title:
        tags |= {
            "lightning mcqueen",
            "disney pixar cars",
            "pixar cars toys",
            "mcqueen unboxing",
            "cars toy review",
        }
    if "beamng" in title:
        tags |= {
            "beamng drive",
            "beamng crash",
            "beamng gameplay",
            "truck crash simulation",
        }

    tags |= {
        "viral gameplay",
        "satisfying video",
        "toy review",
        "cars gameplay",
    }

    txt = "🏷 <b>TOP TAGLAR (copy-paste):</b>\n\n<code>"
    txt += ", ".join(sorted(tags))
    txt += "</code>"

    await cb.message.answer(txt)

# ================== COMPETITORS ==================
@dp.callback_query(F.data.startswith("competitors"))
async def competitors(cb: CallbackQuery):
    await cb.answer("⏳ Raqobatchi kanallar analiz qilinmoqda...", show_alert=False)

    vid = cb.data.split(":")[1]
    video = get_video(vid)
    if not video:
        await cb.message.answer("❌ Maʼlumot topilmadi.")
        return

    q = video["snippet"]["title"].split("|")[0]

    data = yt_api("search", {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": 10
    })

    if not data:
        await cb.message.answer("❌ Raqobatchilar topilmadi.")
        return

    channels = defaultdict(int)
    for it in data["items"]:
        ch = it["snippet"]["channelTitle"]
        channels[ch] += 1

    txt = "📺 <b>RAQOBATCHI KANALLAR (TOP):</b>\n\n"
    for i, (ch, c) in enumerate(
        sorted(channels.items(), key=lambda x: x[1], reverse=True)[:10], 1
    ):
        txt += f"{i}. {ch} — {c} video\n"

    await cb.message.answer(txt)

# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
