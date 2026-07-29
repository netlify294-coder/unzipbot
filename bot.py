"""
Unzip Bot — Telegram bot jo aapki zip file lekar usse ek channel me
extract karke saari files bhej deta hai.

IMPORTANT (2GB support ke liye):
Telegram ka default Bot API sirf 20MB download aur 50MB upload allow karta hai.
2GB tak ki files handle karne ke liye aapko apna LOCAL Bot API server chalana
padega (telegram-bot-api). README.md me pura setup diya hai — pehle wo padhein.

Flow:
1. User bot ko zip file bhejta hai (private chat me)
2. Bot download karta hai
3. zipfile se extract karta hai temp folder me
4. Har extracted file ko target CHANNEL_ID par upload karta hai
5. Temp files delete karke cleanup karta hai
"""

import os
import shutil
import zipfile
import asyncio
import logging
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# ---------------------- CONFIG ----------------------
# In sab values environment variables se ya seedha yaha fill karein.

API_ID = int(os.environ.get("API_ID", "0"))          # my.telegram.org se
API_HASH = os.environ.get("API_HASH", "")             # my.telegram.org se
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")           # @BotFather se

# Local Bot API server ka address (2GB support ke liye zaroori)
# Agar local server nahi chala rahe to LOCAL_SERVER = False rakhein
# (tab 20MB/50MB ki default limit lagegi).
LOCAL_SERVER = os.environ.get("LOCAL_SERVER", "true").lower() == "true"
LOCAL_API_URL = os.environ.get("LOCAL_API_URL", "http://localhost:8081")

# Target channel jaha extracted files bhejni hain
# Channel ka numeric ID (e.g. -1001234567890) ya @username
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

DOWNLOAD_DIR = Path("downloads")
EXTRACT_DIR = Path("extracted")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unzip-bot")

# ---------------------- CLIENT ----------------------

client_kwargs = dict(
    name="unzip_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

if LOCAL_SERVER:
    # Pyrogram ko local Bot API server ki taraf point karna
    client_kwargs["base_url"] = f"{LOCAL_API_URL}/bot"

app = Client(**client_kwargs)


# ---------------------- HELPERS ----------------------

def human_size(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


async def safe_send(coro_func, *args, **kwargs):
    """FloodWait handle karne ke liye retry wrapper."""
    while True:
        try:
            return await coro_func(*args, **kwargs)
        except FloodWait as e:
            logger.info(f"FloodWait: {e.value}s sleeping...")
            await asyncio.sleep(e.value)


def guess_send_method(app: Client, file_path: Path):
    """File extension ke hisaab se sahi send method choose karta hai."""
    ext = file_path.suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        return app.send_photo
    if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm"):
        return app.send_video
    if ext in (".mp3", ".m4a", ".wav", ".flac", ".ogg"):
        return app.send_audio
    return app.send_document


# ---------------------- HANDLERS ----------------------

@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    await message.reply_text(
        "👋 Namaste! Mujhe koi bhi **.zip** file bhejein — "
        "main use extract karke ek channel me upload kar dunga.\n\n"
        "⚠️ Zip size 2GB tak allowed hai (agar local Bot API server configured hai)."
    )


@app.on_message(filters.document)
async def zip_handler(client: Client, message: Message):
    doc = message.document
    file_name = doc.file_name or "file.zip"

    if not file_name.lower().endswith(".zip"):
        await message.reply_text("❌ Sirf .zip files supported hain abhi.")
        return

    if not CHANNEL_ID:
        await message.reply_text("⚠️ Bot me CHANNEL_ID configure nahi hai. Admin ko batayein.")
        return

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    EXTRACT_DIR.mkdir(exist_ok=True)

    status = await message.reply_text(f"⬇️ Downloading `{file_name}` ({human_size(doc.file_size)})...")

    zip_path = DOWNLOAD_DIR / file_name
    extract_path = EXTRACT_DIR / Path(file_name).stem

    try:
        # ------------- Step 1: Download -------------
        await message.download(
            file_name=str(zip_path),
            progress=lambda current, total: None,  # chahe to progress bar bana sakte hain
        )
        await status.edit_text("📦 Download complete. Extracting...")

        # ------------- Step 2: Extract -------------
        extract_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_path)

        all_files = [p for p in extract_path.rglob("*") if p.is_file()]

        if not all_files:
            await status.edit_text("⚠️ Zip khali nikli, koi file nahi mili.")
            return

        await status.edit_text(f"📤 {len(all_files)} files mili. Channel par upload ho raha hai...")

        # ------------- Step 3: Upload to channel -------------
        uploaded = 0
        for f in all_files:
            send_method = guess_send_method(app, f)
            caption = f.name

            if send_method == app.send_photo:
                arg_name = "photo"
            elif send_method == app.send_video:
                arg_name = "video"
            elif send_method == app.send_audio:
                arg_name = "audio"
            else:
                arg_name = "document"

            try:
                await safe_send(
                    send_method,
                    chat_id=CHANNEL_ID,
                    caption=caption,
                    **{arg_name: str(f)},
                )
                uploaded += 1
            except Exception as e:
                logger.exception(f"Failed to upload {f}: {e}")
                await message.reply_text(f"⚠️ `{f.name}` upload nahi ho payi: {e}")

        await status.edit_text(
            f"✅ Done! {uploaded}/{len(all_files)} files channel par bhej di gayi."
        )

    except zipfile.BadZipFile:
        await status.edit_text("❌ Ye ek valid zip file nahi hai.")
    except Exception as e:
        logger.exception("Error processing zip")
        await status.edit_text(f"❌ Error aaya: {e}")
    finally:
        # ------------- Step 4: Cleanup -------------
        if zip_path.exists():
            zip_path.unlink()
        if extract_path.exists():
            shutil.rmtree(extract_path, ignore_errors=True)


if __name__ == "__main__":
    logger.info("Starting unzip bot...")
    app.run()
