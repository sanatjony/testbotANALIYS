import os
import re
import asyncio
import requests
from collections import Counter

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV xato")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= CONFIG =================
BANNED = {"hack", "crack", "cheat", "free download", "mod apk"}

TRIGGERS = [
    "vs", "challenge", "experiment", "gameplay",
    "insane", "crazy", "unexpected", "extreme"
]

# ================= HELPERS =================
def get_video_id(url: str):
    m = re.search(r"(v=|youtu\.be/|/live/)([^&?/]+)", url)
    return m.group(2) if m else None

def yt_video(video_id: str):
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet&id={video_id}&key={YOUTUBE_API_KEY}"
    )
    return requests.get(url, timeout=10).json()["items"][0]

def yt_search(query: str, limit=40):
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&type=video&q={query}"
        f"&maxResults={limit}&key={YOUTUBE_API_KEY}"
    )
    return requests.get(url, timeout=10).json().get("items", [])

def extract_phrases(text: str):
    words = re.findall(r"[A-Za-z0-9]{3,}", text.lower())
    phrases = []

    for size in (1, 2, 3, 4):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i+size])
            if not any(b in phrase for b in BANNED):
                phrases.append(phrase)

    return phrases

# ================= START =================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🧪 *YouTube Analyser — TEST*\n\n"
        "YouTube video link yuboring\n"
        "✍️ AI Title | 🏷 AI Tags",
        parse_mode="Markdown"
    )

# ================= MAIN =================
@dp.message()
async def handle_video(message: types.Message):
    vid = get_video_id(message.text or "")
    if not vid:
        await message.answer("❌ YouTube link noto‘g‘ri.")
        return

    video = yt_video(vid)
    title = video["snippet"]["title"]
    channel = video["snippet"]["channelTitle"]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✍️ AI Title", callback_data=f"titleai:{vid}"),
                InlineKeyboardButton(text="🏷 AI Tags", callback_data=f"tagai:{vid}")
            ]
        ]
    )

    await message.answer(
        f"🎬 *Mavjud video nomi:*\n{title}\n\n"
        f"📺 Kanal: {channel}\n\n"
        "👇 Kerakli AI funksiyani tanlang",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================= AI TITLE =================
@dp.callback_query(F.data.startswith("titleai:"))
async def title_ai_cb(call: types.CallbackQuery):
    vid = call.data.split(":")[1]
    video = yt_video(vid)

    base_title = video["snippet"]["title"]
    items = yt_search(base_title)

    phrases = []
    for i in items:
        phrases.extend(extract_phrases(i["snippet"]["title"]))

    if not phrases:
        phrases = extract_phrases(base_title)

    core = [p for p, _ in Counter(phrases).most_common(5)]

    titles = []
    for c in core:
        for t in TRIGGERS:
            new = f"{c.title()} {t.title()} | {base_title.split('|')[0]}"
            if 45 <= len(new) <= 90:
                titles.append(new)
            if len(titles) >= 5:
                break

    text = "✍️ *AI tavsiya qilgan clickbait titellar*\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n\n"

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= AI TAGS =================
@dp.callback_query(F.data.startswith("tagai:"))
async def tag_ai_cb(call: types.CallbackQuery):
    vid = call.data.split(":")[1]
    video = yt_video(vid)

    base_title = video["snippet"]["title"]
    items = yt_search(base_title)

    tags = []

    # 1️⃣ Search title'lardan
    for i in items:
        tags.extend(extract_phrases(i["snippet"]["title"]))

    # 2️⃣ Asl title fallback
    if not tags:
        tags.extend(extract_phrases(base_title))

    # 3️⃣ Trigger bilan kengaytirish
    expanded = []
    for t in tags[:10]:
        for trig in TRIGGERS:
            expanded.append(f"{t} {trig}")

    all_tags = tags + expanded
    final_tags = [t for t, _ in Counter(all_tags).most_common(20)]

    text = (
        "🏷 *AI tavsiya qilgan top taglar*\n\n"
        "```\n" + ", ".join(final_tags) + "\n```\n\n"
        "📈 CTR + Search uchun mos"
    )

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST bot ishga tushdi (AI TAG FIXED)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
