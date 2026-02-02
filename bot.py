import os
import re
import asyncio
import requests
from datetime import datetime
from io import BytesIO

import pytz
import pandas as pd
import matplotlib.pyplot as plt

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytrends.request import TrendReq

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV sozlanmagan")

TZ = pytz.timezone("Asia/Tashkent")

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= HELPERS =================
def get_video_id(url: str):
    m = re.search(r"(v=|youtu\.be/|/live/)([^&?/]+)", url)
    return m.group(2) if m else None

def extract_keyword(title: str):
    words = title.split()
    return " ".join(words[:3]) if len(words) >= 3 else title

# ================= YOUTUBE =================
def yt_video(video_id: str):
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,statistics,contentDetails"
        f"&id={video_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    r = requests.get(url, timeout=10).json()
    return r["items"][0] if r.get("items") else None

def yt_search(keyword: str, limit=10):
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&type=video"
        f"&q={keyword}"
        f"&maxResults={limit}"
        f"&key={YOUTUBE_API_KEY}"
    )
    return requests.get(url, timeout=10).json().get("items", [])

# ================= START =================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🧪 *YouTube Analyser TEST BOT*\n\n"
        "📌 YouTube video havolasini yuboring.\n"
        "🔘 Qo‘shimcha analizlar inline tugmalar orqali.\n"
        "🌍 Google Trends: GLOBAL + grafik",
        parse_mode="Markdown"
    )

# ================= MAIN ANALYSIS =================
@dp.message()
async def handle_video(message: types.Message):
    url = (message.text or "").strip()
    video_id = get_video_id(url)

    if not video_id:
        await message.answer("❌ YouTube video link noto‘g‘ri.")
        return

    video = yt_video(video_id)
    if not video:
        await message.answer("❌ Video topilmadi.")
        return

    sn = video["snippet"]
    st = video["statistics"]

    title = sn["title"]
    channel = sn["channelTitle"]
    published = datetime.fromisoformat(
        sn["publishedAt"].replace("Z", "+00:00")
    ).astimezone(TZ)

    views = int(st.get("viewCount", 0))
    likes = int(st.get("likeCount", 0))
    comments = int(st.get("commentCount", 0))

    ratio = (likes / views * 100) if views else 0
    if ratio > 30:
        flag = "🔴 Nakrutka ehtimoli"
    elif ratio > 15:
        flag = "🟡 Shubhali"
    else:
        flag = "🟢 Normal"

    keyword = extract_keyword(title)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Raqobat (YouTube Search)",
                    callback_data=f"search:{keyword}"
                ),
                InlineKeyboardButton(
                    text="📈 Trend (Google • Grafik)",
                    callback_data=f"trend:{keyword}"
                )
            ]
        ]
    )

    text = (
        f"🎬 *{title}*\n"
        f"📺 Kanal: {channel}\n\n"
        f"🕒 {published.strftime('%d.%m.%Y %H:%M')} (UTC+5)\n\n"
        f"📊 *Statistika*\n"
        f"👁 View: {views}\n"
        f"👍 Like: {likes}\n"
        f"💬 Comment: {comments}\n\n"
        f"{flag}\n\n"
        f"🔑 Keyword: *{keyword}*"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

# ================= SEARCH ANALYSIS =================
@dp.callback_query(F.data.startswith("search:"))
async def search_cb(call: types.CallbackQuery):
    keyword = call.data.split("search:", 1)[1]

    items = yt_search(keyword)
    if not items:
        await call.message.answer("❌ Search bo‘yicha natija topilmadi.")
        await call.answer()
        return

    channels = {i["snippet"]["channelTitle"] for i in items}

    text = (
        f"🔍 *YouTube Search Analiz*\n\n"
        f"🔑 Keyword: *{keyword}*\n"
        f"📹 Top videolar: {len(items)}\n"
        f"📺 Turli kanallar: {len(channels)}\n\n"
        f"📊 *Xulosa:* "
    )

    if len(channels) > 7:
        text += "🔴 Raqobat yuqori"
    elif len(channels) > 4:
        text += "🟡 Raqobat o‘rtacha"
    else:
        text += "🟢 Raqobat past"

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= GOOGLE TRENDS + GRAPH =================
@dp.callback_query(F.data.startswith("trend:"))
async def trend_cb(call: types.CallbackQuery):
    keyword = call.data.split("trend:", 1)[1]

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], timeframe="today 3-m")
    data = pytrends.interest_over_time()

    if data.empty:
        await call.message.answer("❌ Google Trends ma’lumot topilmadi.")
        await call.answer()
        return

    # Grafik chizish
    plt.figure()
    data[keyword].plot()
    plt.title(f"Google Trends (Global): {keyword}")
    plt.xlabel("Sana")
    plt.ylabel("Qiziqish darajasi")
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)

    start = data[keyword].iloc[0]
    end = data[keyword].iloc[-1]
    diff = end - start

    if diff > 10:
        trend_text = "🟢 Kuchli o‘sish"
    elif diff > 0:
        trend_text = "🟡 Sekin o‘sish"
    elif diff == 0:
        trend_text = "⚪ Barqaror"
    else:
        trend_text = "🔴 Pasayish"

    caption = (
        f"📈 *Google Trends (Global)*\n\n"
        f"🔑 Keyword: *{keyword}*\n"
        f"⏱ Davr: Oxirgi 3 oy\n\n"
        f"📊 Natija: {trend_text}"
    )

    await call.message.answer_photo(
        types.BufferedInputFile(buf.read(), filename="trend.png"),
        caption=caption,
        parse_mode="Markdown"
    )
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST YouTube Analyser (Global Trend + Grafik) ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
