import asyncio
import re
import os
import time
import requests
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.filters import Command

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEYS")

BOT_TOKEN = BOT_TOKEN.strip()
YOUTUBE_API_KEY = YOUTUBE_API_KEY.strip()

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()

YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"

# ================= HELPERS =============
def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=20
    )
    r.raise_for_status()
    return r.json()

# ====== CATEGORY MAP (3 TIL) ==========
CATEGORY_MAP = {
    "Gaming": ("O‘yinlar", "Игры"),
    "News & Politics": ("Yangiliklar va siyosat", "Новости и политика"),
    "Entertainment": ("Ko‘ngilochar", "Развлечения"),
    "Education": ("Ta’lim", "Образование"),
    "Music": ("Musiqa", "Музыка"),
}

def map_category(en_name):
    uz, ru = CATEGORY_MAP.get(en_name, ("Noma’lum", "Неизвестно"))
    return uz, ru, en_name

# ====== NAKRUTKA CHECK ==========
def detect_activity(views, likes, comments, hours):
    if views == 0:
        return "⚪ Ma’lumot yetarli emas"

    like_ratio = likes / views
    comment_ratio = comments / views

    if likes > views:
        return "🔴 LIKE NAKRUTKA"

    if like_ratio >= 0.30:
        return "🔴 LIKE NAKRUTKA"

    if like_ratio >= 0.20 and comment_ratio < 0.002:
        return "🟠 SHUBHALI FAOLLIGI"

    if hours < 3 and views > 5000 and like_ratio > 0.15:
        return "🟠 TEZ O‘SISH"

    return "🟢 NORMAL FAOLLIGI"

# ================= INLINE KB ===========
def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🧠 TOP 10 KONKURENT VIDEO", callback_data=f"top:{vid}")],
        [InlineKeyboardButton("📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")],
        [InlineKeyboardButton("🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")]
    ])

# ================= START ===============
@dp.message(Command("start"))
async def start(m: Message):
    await m.answer(
        f"Assalom aleykum, {m.from_user.first_name} 👋\n\n"
        f"📊 YouTube ANALIZ BOTI\n\n"
        f"👉 YouTube video linkini yuboring"
    )

# ================= ANALYZE =============
@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        await m.answer("❌ Iltimos, video link yuboring.")
        return

    data = yt_api("videos", {"part": "snippet,statistics", "id": vid})
    it = data["items"][0]
    sn = it["snippet"]
    st = it["statistics"]

    # ===== DATE =====
    published_dt = datetime.fromisoformat(
        sn["publishedAt"].replace("Z", "+00:00")
    )
    published_str = published_dt.strftime("%Y-%m-%d %H:%M UTC")
    hours = (datetime.now(timezone.utc) - published_dt).total_seconds() / 3600

    # ===== CATEGORY =====
    cat_data = yt_api(
        "videoCategories",
        {"part": "snippet", "id": sn["categoryId"], "regionCode": "US"}
    )
    en_cat = cat_data["items"][0]["snippet"]["title"]
    uz_cat, ru_cat, en_cat = map_category(en_cat)

    # ===== ACTIVITY =====
    activity = detect_activity(
        int(st.get("viewCount", 0)),
        int(st.get("likeCount", 0)),
        int(st.get("commentCount", 0)),
        hours
    )

    caption = (
        f"🎬 <b>{sn['title']}</b>\n\n"
        f"📂 Kategoriya:\n"
        f"🇺🇿 {uz_cat}\n"
        f"🇷🇺 {ru_cat}\n"
        f"🇬🇧 {en_cat}\n\n"
        f"📺 Kanal: {sn['channelTitle']}\n"
        f"⏰ Yuklangan: {published_str}\n\n"
        f"👁 {st.get('viewCount',0)}   "
        f"👍 {st.get('likeCount',0)}   "
        f"💬 {st.get('commentCount',0)}\n\n"
        f"🚨 {activity}"
    )

    await bot.send_photo(
        chat_id=m.chat.id,
        photo=sn["thumbnails"]["high"]["url"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=result_kb(vid)
    )

# ================= CALLBACKS ===========
@router.callback_query(F.data.startswith("top:"))
async def cb_top(c: CallbackQuery):
    await c.message.answer("🧠 TOP 10 KONKURENT VIDEO (keyingi bosqich)")
    await c.answer()

@router.callback_query(F.data.startswith("channels:"))
async def cb_channels(c: CallbackQuery):
    await c.message.answer("📺 Raqobatchi kanallar (keyingi bosqich)")
    await c.answer()

@router.callback_query(F.data.startswith("tags:"))
async def cb_tags(c: CallbackQuery):
    await c.message.answer("🏷 Tag / Tavsif (keyingi bosqich)")
    await c.answer()

# ================= MAIN ================
async def main():
    dp.include_router(router)
    print("🤖 BOT ISHLAYAPTI — KATEGORIYA + SANA + NAKRUTKA QAYTDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
