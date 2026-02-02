import os
import re
import asyncio
import requests
from collections import Counter

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
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

# ================== UTILS ==================
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


def yt_api(endpoint: str, params: dict):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=8
    )
    r.raise_for_status()
    return r.json()

# ================== AI TITLE ==================
def generate_titles(title: str):
    base = title.split("|")[0].strip()
    return [
        f"What Happens When {base} Goes Wrong?",
        f"I Tried This With {base} – The Result Shocked Me",
        f"This Experiment With {base} Was a Mistake",
        f"{base} vs Reality – Nobody Expected This",
        f"Would You Click This? {base} Test"
    ]

# ================== COMPETITORS ==================
def competitor_channels(keyword: str):
    data = yt_api(
        "search",
        {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": 25
        }
    )
    channels = [i["snippet"]["channelTitle"] for i in data["items"]]
    return Counter(channels).most_common(5)

# ================== AI TAGS ==================
def generate_tags(title: str, competitors):
    t = title.lower()
    tags = set()

    if "beamng" in t:
        tags |= {
            "beamng drive", "beamng gameplay",
            "beamng crash", "beamng mods"
        }
    if "truck" in t or "flatbed" in t:
        tags |= {
            "flatbed truck", "truck experiment",
            "truck challenge", "truck vs car"
        }
    if "mcqueen" in t:
        tags |= {
            "pixar cars", "lightning mcqueen",
            "disney cars"
        }

    for c in competitors:
        for w in c.lower().split():
            if len(w) > 3:
                tags.add(w)

    tags |= {
        "viral gameplay",
        "satisfying crash",
        "simulation game",
        "youtube gaming"
    }

    return ", ".join(sorted(tags))

# ================== HANDLERS ==================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video linkini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR\n"
        "🏷 TOP TAGLAR\n"
        "🎯 Raqobatchi kanallar\n\n"
        "analiz qilib beraman."
    )

@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    video_id = extract_video_id(msg.text)
    if not video_id:
        await msg.answer("❌ Video link noto‘g‘ri.")
        return

    try:
        data = yt_api(
            "videos",
            {"part": "snippet,statistics", "id": video_id}
        )["items"][0]
    except Exception:
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    s = data["snippet"]
    st = data["statistics"]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP NOMLAR",
                    callback_data=f"title:{video_id}"
                ),
                InlineKeyboardButton(
                    text="🏷 TOP TAGLAR",
                    callback_data=f"tags:{video_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Raqobatchi analiz",
                    callback_data=f"comp:{video_id}"
                )
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{s['title']}</b>\n"
        f"📺 Kanal: {s['channelTitle']}\n\n"
        f"👁 View: {st.get('viewCount','-')}\n"
        f"👍 Like: {st.get('likeCount','-')}\n"
        f"💬 Comment: {st.get('commentCount','-')}\n\n"
        "👇 Funksiyani tanlang:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    titles = generate_titles(data["snippet"]["title"])

    text = "🧠 <b>TOP CLICKBAIT NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()

@dp.callback_query(F.data.startswith("comp:"))
async def cb_comp(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]

    keyword = data["snippet"]["title"].split("|")[0]
    comps = competitor_channels(keyword)

    text = "🎯 <b>Raqobatchi kanallar (TOP):</b>\n\n"
    for i, (ch, cnt) in enumerate(comps, 1):
        text += f"{i}. <b>{ch}</b>\n   🎬 O‘xshash videolar: {cnt}\n"

    await cb.message.answer(text)
    await cb.answer()

@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]

    keyword = data["snippet"]["title"].split("|")[0]
    comps = competitor_channels(keyword)
    comp_names = [c[0] for c in comps]

    tags = generate_tags(data["snippet"]["title"], comp_names)

    await cb.message.answer(
        "<b>🏷 TOP TAGLAR (copy-paste):</b>\n\n"
        f"<code>{tags}</code>"
    )
    await cb.answer()

# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
