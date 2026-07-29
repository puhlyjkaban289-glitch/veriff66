import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import io
import config

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)

# ================= TELEGRAM =================
bot = TelegramClient('bot', config.API_ID, config.API_HASH).start(bot_token=config.BOT_TOKEN)

# ================= GOOGLE DRIVE =================
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive():
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

# ================= DOWNLOAD SESSION =================
def download_session(service, file_id, filename):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(filename, 'wb')
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()
        logging.info(f"Download {int(status.progress() * 100)}%")

    return filename

# ================= GET FILES =================
def get_sessions(service):
    query = f"'{config.DRIVE_FOLDER_ID}' in parents and name contains '.session'"
    results = service.files().list(q=query).execute()
    files = results.get('files', [])

    logging.info(f"Найдено файлов: {len(files)}")

    return files

# ================= MAIN =================
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("🚀 Бот работает")

@bot.on(events.NewMessage(pattern='/get'))
async def get_account(event):
    await event.reply("🔍 Ищу .session...")

    try:
        service = get_drive()
        files = get_sessions(service)

        if not files:
            await event.reply("❌ Нет свободных .session")
            return

        file = files[0]
        file_id = file['id']
        filename = file['name']

        logging.info(f"Берём файл: {filename}")

        path = download_session(service, file_id, filename)

        await event.reply(f"✅ Скачан: {filename}")

        # ================= TELETHON LOGIN =================
        try:
            client = TelegramClient(path, config.API_ID, config.API_HASH)
            await client.connect()

            if await client.is_user_authorized():
                me = await client.get_me()
                await event.reply(f"👤 Аккаунт: {me.first_name}")
            else:
                await event.reply("⚠️ Сессия не авторизована")

            await client.disconnect()

        except Exception as e:
            await event.reply(f"❌ Ошибка Telethon: {e}")

        # ================= MOVE TO ARCHIVE =================
        service.files().update(
            fileId=file_id,
            addParents=config.DRIVE_ARCHIVE_FOLDER_ID,
            removeParents=config.DRIVE_FOLDER_ID
        ).execute()

        await event.reply("📦 Перемещено в архив")

    except Exception as e:
        await event.reply(f"🔥 Ошибка: {e}")

# ================= RUN =================
bot.run_until_disconnected()
