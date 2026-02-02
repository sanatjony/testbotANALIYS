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
CACHE_TTL = 1800  # 30 daqiqa

# ================= FILTERS =================
KIDS_WORDS = {
    "kids", "kid", "children", "toy", "toys", "cartoon", "baby", "nursery"
}
BANNED_WORDS = {
    "free", "download", "hack", "cheat", "crack", "mod apk"
}
TRIGGER_WORDS = [
    "vs", "challenge", "crash test", "experiment", "gameplay",
    "realistic", "physics", "simulation", "extreme"
]

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

def clean_words(words):
    out = []
    for w in words:
        lw = w.lower()
        if lw in KIDS_WORDS or lw in BANNED_WORDS:
            continue
        if len(w) < 4:
            continue
        out.append(w)
    return out

def extract_phrases(title):
    words = re.findall(r"[A-Za-z]{4,}", title)
    words = clean_words(words)
    phrases = []
    for i in range(len(words) - 1):
        phrases.append(f"{words[i]} {words[i+1]}")
    return phrases

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

def yt_search(keyword: str, limit=40):
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
        "🧪 *YouTube Analyser — TEST BOT*\n\n"
        "📌 YouTube video link yuboring.\n"
        "🔘 Inline tugmalar orqali tahlil qilinadi:\n"
        "• Trend\n• Raqobat\n• Top Tags\n• AI Title",
        parse_mode="Markdown"
    )

# ================= MAIN =================
@dp.message()
async def handle_video(message: types.Message):
    url = (message.text or "").strip()
    vid = get_video_id(url)

    if not vid:
        await message.answer("❌ YouTube link noto‘g‘ri.")
        return

    video = yt_video(vid)
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
                InlineKeyboardButton("📈 Trend", callback_data=f"trend:{keyword}"),
                InlineKeyboardButton("🔍 Raqobat", callback_data=f"search:{keyword}")
            ],
            [
                InlineKeyboardButton("🏷 Top Tags", callback_data=f"tags:{keyword}"),
                InlineKeyboardButton("✍️ Title AI", callback_data=f"titleai:{vid}")
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
        f"🔑 Mavzu: *{keyword}*"
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
            await call.message.answer("⚠️ Juda tor mavzu, global trend topilmadi.")
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

# ================= TOP TAGS =================
@dp.callback_query(F.data.startswith("tags:"))
async def tags_cb(call: types.CallbackQuery):
    keyword = call.data.split("tags:", 1)[1]
    items = yt_search(keyword, limit=40)

    words = []
    for i in items:
        title = i["snippet"]["title"]
        found = re.findall(r"[A-Za-z]{4,}", title)
        words.extend(clean_words(found))

    counter = Counter(words)
    tags = [w for w, _ in counter.most_common(15)]

    if not tags:
        await call.message.answer("⚠️ Mos taglar topilmadi.")
        await call.answer()
        return

    text = (
        "🏷 *Top trend & safe taglar*\n\n"
        "```\n" + ", ".join(tags) + "\n```\n\n"
        "✅ NoKids\n"
        "✅ Qoidalarga mos\n"
        "📈 Trendga yaqin"
    )

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= AI TITLE =================
@dp.callback_query(F.data.startswith("titleai:"))
async def title_ai_cb(call: types.CallbackQuery):
    vid = call.data.split("titleai:", 1)[1]
    video = yt_video(vid)

    base_title = video["snippet"]["title"]
    items = yt_search(base_title, limit=40)

    phrases = []
    for i in items:
        phrases.extend(extract_phrases(i["snippet"]["title"]))

    counter = Counter(phrases)
    core = [p for p, _ in counter.most_common(5)]

    titles = []
    for c in core:
        for t in TRIGGER_WORDS:
            new_title = f"{c} {t.title()} | {base_title.split('|')[0]}"
            if 55 <= len(new_title) <= 75:
                titles.append(new_title)
            if len(titles) >= 5:
                break
        if len(titles) >= 5:
            break

    text = "✍️ *AI tavsiya qilgan optimal video nomlari*\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n\n"

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST bot ishga tushdi (FULL)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
