import asyncio
import re
import sqlite3
import time
import os
import requests
from datetime import datetime, timedelta, timezone

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
ADMIN_IDS = os.getenv("ADMIN_IDS", "")

BOT_TOKEN = BOT_TOKEN.strip()
YOUTUBE_API_KEY = YOUTUBE_API_KEY.strip()
ADMIN_IDS = {int(x) for x in ADMIN_IDS.split(",") if x.strip().isdigit()}

# ================= CONFIG ==============
CREDIT_DAILY = 5

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()

# ================= HELPERS =============
YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"

def is_admin(uid): return uid in ADMIN_IDS

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# ================= INLINE KB ===========
def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP 10 KONKURENT VIDEO", callback_data=f"top:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")]
    ])

# ================= START ===============
@dp.message(Command("start"))
async def start(m: Message):
    await m.answer(
        f"Assalom aleykum, {m.from_user.first_name} 👋\n\n"
        f"📊 YouTube ANALIZ BOTI\n\n"
        f"💳 Kredit: {CREDIT_DAILY}/{CREDIT_DAILY}\n\n"
        f"👉 YouTube video linkini yuboring"
    )

# ================= ANALYZE =============
@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        await m.answer("❌ Iltimos, video link yuboring.")
        return

    data = yt_api("videos", {"part":"snippet,statistics","id":vid})
    it = data["items"][0]
    sn, st = it["snippet"], it["statistics"]

    await bot.send_photo(
        m.chat.id,
        sn["thumbnails"]["high"]["url"],
        caption=f"🎬 {sn['title']}\n📺 {sn['channelTitle']}\n👁 {st.get('viewCount',0)}"
    )

    await m.answer(
        f"🎬 {sn['title']}\n"
        f"📺 Kanal: {sn['channelTitle']}\n"
        f"👁 {st.get('viewCount',0)} 👍 {st.get('likeCount',0)} 💬 {st.get('commentCount',0)}",
        reply_markup=result_kb(vid)
    )

# ================= CALLBACKS ===========
@router.callback_query(F.data.startswith("top:"))
async def cb_top(c: CallbackQuery):
    vid = c.data.split(":")[1]
    await c.message.answer(f"🧠 TOP 10 KONKURENT VIDEO\n(video ID: {vid})")
    await c.answer()

@router.callback_query(F.data.startswith("channels:"))
async def cb_channels(c: CallbackQuery):
    await c.message.answer("📺 Raqobatchi kanallar (TEST)")
    await c.answer()

@router.callback_query(F.data.startswith("tags:"))
async def cb_tags(c: CallbackQuery):
    await c.message.answer("🏷 Tag / Tavsif (TEST)")
    await c.answer()

# ================= MAIN ================
async def main():
    dp.include_router(router)
    print("🤖 BOT ISHLAYAPTI — INLINE CALLBACKLAR TUZATILDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
