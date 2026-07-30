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

# NOTE: Pyrogram MTProto se seedha Telegram ke servers se connect hota hai
# (official HTTP Bot API server ke through nahi), isliye 20MB/50MB wali
# limit yaha lagti hi nahi — 2GB tak ki files bina kisi local server ke
# already handle ho jati hain.

# Target channel jaha extracted files bhejni hain
# Channel ka numeric ID (e.g. -1001234567890) ya @username
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

DOWNLOAD_DIR = Path("downloads")
EXTRACT_DIR = Path("extracted")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unzip-bot")

# ---------------------- CLIENT ----------------------

app = Client(
    name="unzip_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    # Ek file ko multiple parallel connections se download/upload karta hai
    # — bade files (500MB-2GB) ke liye speed kaafi zyada badh jaati hai.
    # VPS resources achhe hain (4+ core, 8GB+ RAM) to 8-12 tak try kar sakte ho.
    max_concurrent_transmissions=8,
)


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

    # ------------- Disk space check (extract + zip dono ke liye ~3x jagah chahiye) -------------
    needed = (doc.file_size or 0) * 3
    free_space = shutil.disk_usage(DOWNLOAD_DIR).free
    if needed and free_space < needed:
        await message.reply_text(
            f"❌ Disk me jagah kam hai. Chahiye ~{human_size(needed)}, "
            f"available: {human_size(free_space)}. VPS disk clean karein "
            f"ya storage badhayein."
        )
        return

    status = await message.reply_text(f"⬇️ Downloading `{file_name}` ({human_size(doc.file_size)})...")

    zip_path = DOWNLOAD_DIR / file_name
    extract_path = EXTRACT_DIR / Path(file_name).stem

    try:
        # ------------- Step 1: Download -------------
        try:
            downloaded_path = await message.download(
                file_name=str(zip_path),
                progress=lambda current, total: None,  # chahe to progress bar bana sakte hain
            )
        except Exception as dl_error:
            logger.exception("Download failed with exception")
            await status.edit_text(f"❌ Download ke dauraan error aaya: {dl_error}")
            return

        if not downloaded_path or not Path(downloaded_path).exists():
            await status.edit_text("❌ Download fail ho gaya — file save nahi hui. Dobara try karein.")
            return

        actual_size = Path(downloaded_path).stat().st_size
        expected_size = doc.file_size or 0

        if expected_size and actual_size != expected_size:
            await status.edit_text(
                f"❌ Download incomplete lagta hai "
                f"({human_size(actual_size)} mila, {human_size(expected_size)} expected). "
                f"Network issue ho sakta hai — dobara bhejein."
            )
            return

        if not zipfile.is_zipfile(downloaded_path):
            # Debug ke liye pehle kuch bytes dekh lete hain
            with open(downloaded_path, "rb") as fcheck:
                header = fcheck.read(8)
            await status.edit_text(
                f"❌ Ye ek valid zip file nahi hai.\n"
                f"Downloaded size: {human_size(actual_size)}\n"
                f"File header (hex): `{header.hex()}`\n\n"
                f"Check karein ki file sach me .zip hai (rar/7z/tar renamed to "
                f".zip to nahi hai), aur agar bahut badi file thi to dobara "
                f"bhej ke try karein — kabhi kabhi bada upload beech me kat "
                f"jata hai."
            )
            return

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
                # Kai baar video/photo/audio ka metadata Telegram ko pasand
                # nahi aata (jaise purani WhatsApp .mp4 files me moov atom
                # missing) — is case me plain document ke roop me try karte hain.
                if arg_name != "document":
                    logger.warning(f"{arg_name} send failed for {f.name}, retrying as document: {e}")
                    try:
                        await safe_send(
                            app.send_document,
                            chat_id=CHANNEL_ID,
                            document=str(f),
                            caption=caption,
                        )
                        uploaded += 1
                        continue
                    except Exception as e2:
                        logger.exception(f"Document fallback bhi fail hua for {f}: {e2}")
                        await message.reply_text(f"⚠️ `{f.name}` upload nahi ho payi: {e2}")
                        continue
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
