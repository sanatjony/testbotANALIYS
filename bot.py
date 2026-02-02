import os
import re
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import requests
from pytrends.request import TrendReq
import matplotlib.pyplot as plt

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


def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=10
    )
    r.raise_for_status()
    return r.json()


# ================== AI LOGIC ==================
def generate_titles(title: str):
    base = title.split("|")[0].strip()
    return [
        f"{base} 😱 INSANE Result!",
        f"{base} 🔥 You Won’t Believe This",
        f"{base} 💥 CRAZY Experiment",
        f"{base} ⚠️ Unexpected Outcome",
        f"{base} 🚛 SHOCKING Gameplay"
    ]


def generate_tags(title: str):
    title = title.lower()
    tags = set()

    if "mcqueen" in title or "cars" in title:
        tags |= {
            "pixar cars", "lightning mcqueen", "disney cars",
            "cars toys", "mcqueen gameplay"
        }

    if "truck" in title:
        tags |= {
            "flatbed truck", "truck challenge", "truck experiment",
            "truck gameplay", "transportation truck"
        }

    tags |= {
        "beamng drive", "beamng gameplay", "beamng mods",
        "viral gameplay", "satisfying gameplay", "simulation game"
    }

    return ", ".join(sorted(tags))


# ================== TREND (1 OY) ==================
def build_trend_chart(keyword: str):
    pytrends = TrendReq(hl="en-US", tz=0)
    pytrends.build_payload(
        [keyword],
        timeframe="today 1-m"
    )
    data = pytrends.interest_over_time()

    if data.empty:
        return None

    plt.figure(figsize=(6, 3))
    plt.plot(data.index, data[keyword])
    plt.title(f"Global trend (1 oy): {keyword}")
    plt.tight_layout()

    file_path = f"/tmp/trend_{keyword.replace(' ', '_')}.png"
    plt.savefig(file_path)
    plt.close()
    return file_path


# ================== HANDLERS ==================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 <b>TOP NOMLAR</b>\n"
        "🏷 <b>TOP TAGLAR</b>\n"
        "📈 <b>Global trend (1 oy)</b>\n\n"
        "chiqarib beraman."
    )


@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    video_id = extract_video_id(msg.text)
    if not video_id:
        await msg.answer("❌ Video ID topilmadi.")
        return

    try:
        video = yt_api(
            "videos",
            {
                "part": "snippet,statistics",
                "id": video_id
            }
        )["items"][0]
    except Exception:
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    snippet = video["snippet"]
    stats = video["statistics"]

    title = snippet["title"]
    channel = snippet["channelTitle"]

    text = (
        f"🎬 <b>{title}</b>\n"
        f"📺 Kanal: <b>{channel}</b>\n\n"
        f"👁 View: {stats.get('viewCount','-')}\n"
        f"👍 Like: {stats.get('likeCount','-')}\n"
        f"💬 Comment: {stats.get('commentCount','-')}\n\n"
        "👇 <b>Kerakli funksiyani tanlang:</b>"
    )

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
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📈 Global trend (1 oy)",
                    callback_data=f"trend:{video_id}"
                )
            ]
        ]
    )

    await msg.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb):
    video_id = cb.data.split(":")[1]
    video = yt_api(
        "videos",
        {"part": "snippet", "id": video_id}
    )["items"][0]

    titles = generate_titles(video["snippet"]["title"])
    text = "<b>🧠 TOP CLICKBAIT NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb):
    video_id = cb.data.split(":")[1]
    video = yt_api(
        "videos",
        {"part": "snippet", "id": video_id}
    )["items"][0]

    tags = generate_tags(video["snippet"]["title"])
    await cb.message.answer(
        "<b>🏷 TOP TAGLAR (copy-paste):</b>\n\n"
        f"<code>{tags}</code>"
    )


@dp.callback_query(F.data.startswith("trend:"))
async def cb_trend(cb):
    await cb.message.answer("📈 Global trend olinmoqda (1 oy), biroz kuting...")

    video_id = cb.data.split(":")[1]
    video = yt_api(
        "videos",
        {"part": "snippet", "id": video_id}
    )["items"][0]

    keyword = video["snippet"]["title"].split("|")[0].strip()

    path = await asyncio.to_thread(build_trend_chart, keyword)
    if not path:
        await cb.message.answer("❌ Trend ma’lumot topilmadi.")
        return

    await cb.message.answer_photo(
        photo=open(path, "rb"),
        caption=f"📈 <b>Global trend (1 oy)</b>\n🔑 Keyword: <b>{keyword}</b>"
    )


# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
