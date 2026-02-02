import os
import re
import asyncio
import requests
from datetime import datetime
from collections import Counter

import pytz
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV xato")

TZ = pytz.timezone("Asia/Tashkent")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= CONSTANTS =================
TRIGGER_WORDS = [
    "vs", "challenge", "crash test", "experiment",
    "gameplay", "realistic", "physics", "simulation"
]

# ================= HELPERS =================
def get_video_id(url: str):
    m = re.search(r"(v=|youtu\.be/|/live/)([^&?/]+)", url)
    return m.group(2) if m else None

def yt_video(video_id: str):
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,statistics&id={video_id}&key={YOUTUBE_API_KEY}"
    )
    r = requests.get(url, timeout=10).json()
    return r["items"][0] if r.get("items") else None

def yt_search(query: str, limit=40):
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&type=video&q={query}"
        f"&maxResults={limit}&key={YOUTUBE_API_KEY}"
    )
    return requests.get(url, timeout=10).json().get("items", [])

def extract_phrases(title: str):
    words = re.findall(r"[A-Za-z]{4,}", title)
    phrases = []
    for size in (2, 3):
        for i in range(len(words) - size + 1):
            phrases.append(" ".join(words[i:i+size]))
    return phrases

# ================= START =================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🧪 *YouTube Analyser — TEST*\n\n"
        "📌 YouTube video link yuboring\n"
        "✍️ AI title analiz qilinadi",
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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Title AI",
                    callback_data=f"titleai:{vid}"
                )
            ]
        ]
    )

    text = (
        f"🎬 *Mavjud video nomi:*\n{title}\n\n"
        f"📺 Kanal: {channel}\n"
        f"🕒 {published.strftime('%d.%m.%Y %H:%M')} (UTC+5)\n\n"
        f"📊 View: {views}\n"
        f"👍 Like: {likes}\n"
        f"💬 Comment: {comments}\n\n"
        f"{flag}"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

# ================= AI TITLE =================
@dp.callback_query(F.data.startswith("titleai:"))
async def title_ai_cb(call: types.CallbackQuery):
    vid = call.data.split("titleai:", 1)[1]
    video = yt_video(vid)

    base_title = video["snippet"]["title"]
    items = yt_search(base_title)

    phrases = []
    for i in items:
        phrases.extend(extract_phrases(i["snippet"]["title"]))

    if not phrases:
        phrases = extract_phrases(base_title)

    counter = Counter(phrases)
    core = [p for p, _ in counter.most_common(5)]

    titles = []
    for c in core:
        for t in TRIGGER_WORDS:
            new_title = f"{c} {t.title()} | {base_title.split('|')[0]}"
            if 45 <= len(new_title) <= 90:
                titles.append(new_title)
            if len(titles) >= 5:
                break
        if len(titles) >= 5:
            break

    if not titles:
        titles = [base_title]

    text = "✍️ *AI tavsiya qilgan optimal video nomlari*\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n\n"

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST bot ishga tushdi (FIXED)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
