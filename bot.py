import os
import re
import asyncio
import requests
from datetime import datetime
from io import BytesIO
from collections import Counter

import pytz
import matplotlib.pyplot as plt
from pytrends.request import TrendReq

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV xato")

TZ = pytz.timezone("Asia/Tashkent")

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= CACHE =================
TREND_CACHE = {}
CACHE_TTL = 1800  # 30 min

# ================= HELPERS =================
def get_video_id(url: str):
    m = re.search(r"(v=|youtu\.be/|/live/)([^&?/]+)", url)
    return m.group(2) if m else None

def extract_keyword(title: str):
    words = title.split()
    return " ".join(words[:3]) if len(words) >= 3 else title

def keyword_variants(keyword: str):
    words = keyword.split()
    variants = [keyword]
    if len(words) >= 2:
        variants.append(" ".join(words[:2]))
    for w in words:
        if len(w) > 4:
            variants.append(w)
            break
    variants.append(words[0])
    return list(dict.fromkeys(variants))

# ================= YOUTUBE API =================
def yt_video(video_id: str):
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,statistics"
        f"&id={video_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    r = requests.get(url, timeout=10).json()
    return r["items"][0] if r.get("items") else None

def yt_search(keyword: str, limit=25):
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
        "👋 *YouTube Analyser TEST*\n\n"
        "📌 YouTube video link yuboring.\n"
        "📊 Analiz + Trend + AI tavsiyalar.",
        parse_mode="Markdown"
    )

# ================= MAIN =================
@dp.message()
async def handle_video(message: types.Message):
    url = (message.text or "").strip()
    video_id = get_video_id(url)

    if not video_id:
        await message.answer("❌ YouTube link noto‘g‘ri.")
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
    flag = "🟢 Normal"
    if ratio > 30:
        flag = "🔴 Nakrutka ehtimoli"
    elif ratio > 15:
        flag = "🟡 Shubhali"

    keyword = extract_keyword(title)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Raqobat (YouTube Search)",
                    callback_data=f"search:{keyword}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📈 Trend (Google • Grafik)",
                    callback_data=f"trend:{keyword}"
                ),
                InlineKeyboardButton(
                    text="🤖 AI trend nomlari",
                    callback_data=f"ai:{keyword}"
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

# ================= SEARCH =================
@dp.callback_query(F.data.startswith("search:"))
async def search_cb(call: types.CallbackQuery):
    keyword = call.data.split("search:", 1)[1]
    items = yt_search(keyword)

    channels = {i["snippet"]["channelTitle"] for i in items}
    level = "🟢 Past"
    if len(channels) > 10:
        level = "🔴 Yuqori"
    elif len(channels) > 5:
        level = "🟡 O‘rtacha"

    await call.message.answer(
        f"🔍 *YouTube Search Analiz*\n\n"
        f"🔑 Keyword: *{keyword}*\n"
        f"📹 Top videolar: {len(items)}\n"
        f"📺 Turli kanallar: {len(channels)}\n\n"
        f"📊 Raqobat: {level}",
        parse_mode="Markdown"
    )
    await call.answer()

# ================= TREND =================
@dp.callback_query(F.data.startswith("trend:"))
async def trend_cb(call: types.CallbackQuery):
    raw = call.data.split("trend:", 1)[1]
    now = datetime.now().timestamp()

    if raw in TREND_CACHE:
        ts, cached = TREND_CACHE[raw]
        if now - ts < CACHE_TTL:
            await call.message.answer_photo(
                cached["photo"],
                caption=cached["caption"],
                parse_mode="Markdown"
            )
            await call.answer()
            return

    await call.message.answer("📈 Global trend olinmoqda...")

    try:
        pytrends = TrendReq(hl="en-US", tz=360)
        used_kw = None
        data = None

        for kw in keyword_variants(raw):
            pytrends.build_payload([kw], timeframe="today 3-m")
            tmp = pytrends.interest_over_time()
            if not tmp.empty and tmp[kw].sum() > 0:
                used_kw = kw
                data = tmp
                break

        if data is None:
            await call.message.answer("⚠️ Juda tor keyword, global trend yo‘q.")
            await call.answer()
            return

        plt.figure()
        data[used_kw].plot()
        plt.title(f"Global trend: {used_kw}")
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)

        diff = data[used_kw].iloc[-1] - data[used_kw].iloc[0]
        trend = "⚪ Barqaror"
        if diff > 15:
            trend = "🟢 Kuchli o‘sish"
        elif diff > 5:
            trend = "🟡 O‘sish"
        elif diff < -5:
            trend = "🔴 Pasayish"

        caption = (
            f"📈 *Global trend*\n\n"
            f"🔑 Keyword: *{used_kw}*\n"
            f"⏱ Oxirgi 3 oy\n\n"
            f"📊 Natija: {trend}"
        )

        photo = types.BufferedInputFile(buf.read(), filename="trend.png")
        TREND_CACHE[raw] = (now, {"photo": photo, "caption": caption})

        await call.message.answer_photo(photo, caption=caption, parse_mode="Markdown")

    except Exception:
        await call.message.answer("⚠️ Trend vaqtincha mavjud emas.")

    await call.answer()

# ================= AI KEYWORD =================
@dp.callback_query(F.data.startswith("ai:"))
async def ai_cb(call: types.CallbackQuery):
    keyword = call.data.split("ai:", 1)[1]
    items = yt_search(keyword, limit=30)

    phrases = []

    for i in items:
        title = i["snippet"]["title"]
        words = re.findall(r"[A-Za-z]{4,}", title)
        for j in range(len(words) - 1):
            phrases.append(f"{words[j]} {words[j+1]}")

    counter = Counter(phrases)
    top = [k for k, _ in counter.most_common(3)]

    if not top:
        await call.message.answer("⚠️ AI tavsiya topa olmadi.")
        await call.answer()
        return

    text = "🤖 *AI tavsiya qilgan trend nomlari*\n\n"
    for i, t in enumerate(top, 1):
        text += f"{i}. 🔥 *{t}*\n"

    text += "\n📌 *Tavsiya:* title va description’da ishlating."

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
