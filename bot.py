import asyncio
import random
import json
import re
import os
from pathlib import Path
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.functions.messages import StartBotRequest
from telethon.errors import (
    FloodWaitError,
    AuthKeyUnregisteredError,
    UserDeactivatedError,
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ================= ENV =================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

MAMBA_BOT = os.getenv("MAMBA_BOT")
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL"))
ADMIN_GROUP = int(os.getenv("ADMIN_GROUP"))

DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
DRIVE_ARCHIVE_FOLDER_ID = os.getenv("DRIVE_ARCHIVE_FOLDER_ID")

# 🔥 ВАЖНО: JSON из Variables
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# ================= PATHS =================

DATA_DIR = Path("data")
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# ================= GOOGLE DRIVE =================

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive():
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)

    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )

    return build("drive", "v3", credentials=creds, cache_discovery=False)


drive = get_drive()


def drive_list():
    return drive.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
        fields="files(id,name)"
    ).execute().get("files", [])


def drive_download(file_id, path):
    request = drive.files().get_media(fileId=file_id)
    with open(path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def drive_move(file_id):
    drive.files().update(
        fileId=file_id,
        addParents=DRIVE_ARCHIVE_FOLDER_ID,
        removeParents=DRIVE_FOLDER_ID
    ).execute()


# ================= UTILS =================

def log(text):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {text}", flush=True)


async def delay():
    await asyncio.sleep(random.uniform(0.5, 1.5))


# ================= TELEGRAM BOT =================

bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)


async def is_admin(user_id):
    try:
        perms = await bot.get_permissions(ADMIN_GROUP, user_id)
        return perms.is_admin or perms.is_creator
    except:
        return False


# ================= CORE =================

async def process_session(path):

    async with TelegramClient(str(path), API_ID, API_HASH) as client:
        await delay()

        await client(StartBotRequest(
            bot=MAMBA_BOT,
            start_param="start"
        ))

        log(f"OK {path.name}")


# ================= MAIN WORK =================

async def worker_loop():

    while True:
        try:
            files = drive_list()

            if not files:
                await asyncio.sleep(5)
                continue

            for f in files:
                name = f["name"]

                if not name.endswith(".session"):
                    continue

                local = SESSIONS_DIR / name

                drive_download(f["id"], local)

                try:
                    await process_session(local)
                    drive_move(f["id"])
                except FloodWaitError as e:
                    log(f"FLOOD {e.seconds}")
                    await asyncio.sleep(e.seconds)

                except (AuthKeyUnregisteredError, UserDeactivatedError):
                    log(f"DEAD {name}")

                except Exception as e:
                    log(f"ERROR {e}")

                finally:
                    if local.exists():
                        local.unlink()

        except Exception as e:
            log(f"LOOP ERROR {e}")
            await asyncio.sleep(3)


# ================= COMMANDS =================

@bot.on(events.NewMessage(pattern="/start"))
async def start_cmd(event):
    if not await is_admin(event.sender_id):
        return
    await event.reply("бот работает")


# ================= START =================

async def main():
    log("BOT STARTED")

    await asyncio.gather(
        worker_loop(),
        bot.run_until_disconnected()
    )


if __name__ == "__main__":
    asyncio.run(main())
