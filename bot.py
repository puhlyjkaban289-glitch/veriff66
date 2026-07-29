import re
import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.functions.messages import StartBotRequest
from telethon.errors import (
    AuthKeyUnregisteredError, UserDeactivatedError,
    FloodWaitError, SessionPasswordNeededError,
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config import (
    API_ID, API_HASH, BOT_TOKEN,
    MAMBA_BOT, LOG_CHANNEL, ADMIN_GROUP,
    GOOGLE_CREDENTIALS_FILE,
    DRIVE_FOLDER_ID, DRIVE_ARCHIVE_FOLDER_ID,
)

# ---------- Пути ----------
DATA_DIR = Path("data")
SESSIONS_DIR = DATA_DIR / "sessions"
INDEX_FILE = DATA_DIR / "index.json"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

TEMP_DIR = Path(tempfile.gettempdir()) / "mamba_sessions"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

in_use: set[str] = set()
sessions_lock = asyncio.Lock()

_admin_cache: dict[int, tuple[bool, float]] = {}
_ADMIN_CACHE_TTL = 300

manual_states: dict[int, dict] = {}

MANUAL_WATCH_SECONDS = 90
MANUAL_POLL_INTERVAL = 3

# ---------- Google Drive ----------
SCOPES = ["https://www.googleapis.com/auth/drive"]

def get_drive_service():
    """Сначала JSON из env GOOGLE_CREDENTIALS_JSON, иначе файл."""
    import os
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    if raw:
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
        )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

drive = get_drive_service()


def drive_list_files(folder_id: str, name_contains: str | None = None) -> list[dict]:
    q = f"'{folder_id}' in parents and trashed = false and name contains '.session'"
    if name_contains:
        q += f" and name contains '{name_contains}'"
    results = []
    page_token = None
    while True:
        resp = drive.files().list(
            q=q,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def drive_download(file_id: str, dest: Path):
    request = drive.files().get_media(fileId=file_id)
    with open(dest, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def drive_rename(file_id: str, new_name: str):
    drive.files().update(
        fileId=file_id,
        body={"name": new_name},
        supportsAllDrives=True,
    ).execute()


def drive_move(file_id: str, new_folder_id: str, old_folder_id: str):
    drive.files().update(
        fileId=file_id,
        addParents=new_folder_id,
        removeParents=old_folder_id,
        supportsAllDrives=True,
        fields="id, parents",
    ).execute()


def load_index() -> dict:
    if not INDEX_FILE.exists():
        return {}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_index(index: dict):
    INDEX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def now_str() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


async def is_admin(user_id: int) -> bool:
    if not user_id:
        return False
    now = asyncio.get_event_loop().time()
    cached = _admin_cache.get(user_id)
    if cached and (now - cached[1]) < _ADMIN_CACHE_TTL:
        return cached[0]
    try:
        perms = await bot.get_permissions(ADMIN_GROUP, user_id)
        result = bool(perms.is_admin or perms.is_creator)
    except Exception as e:
        print(f"[ADMIN CHECK] {user_id}: {e}")
        result = False
    _admin_cache[user_id] = (result, now)
    return result


def extract_phone_from_filename(name: str) -> str:
    name = Path(name).stem
    name = re.sub(r'^\[?USED\]?_', '', name, flags=re.I)
    name = re.sub(r'_(VALID|NOVALID|DEAD|ERROR|FREE|USED)$', '', name, flags=re.I)
    digits = re.sub(r'\D', '', name)
    if len(digits) >= 10:
        return digits
    return name


def make_drive_name(phone: str, status: str) -> str:
    status = status.upper()
    if status == "FREE":
        return f"{phone}.session"
    return f"[USED]_{phone}_{status}.session"


async def send_log(client: TelegramClient, text: str):
    try:
        await client.send_message(LOG_CHANNEL, text, link_preview=False)
    except Exception as e:
        print(f"[LOG ERROR] {e}")


def make_log(status: str, phone: str, extra: str = "", user_id: int = 0) -> str:
    time_str = datetime.now().strftime("%H:%M:%S")
    hashtags = {
        "VALID": "#VALID #SUCCESS",
        "NOVALID": "#NOVALID #FAIL",
        "DEAD": "#DEAD #BADSESSION",
        "ERROR": "#ERROR #TIMEOUT",
        "START": "#START #REQUEST",
        "END": "#END #FINISHED",
        "EMPTY": "#EMPTY #NOACCOUNTS",
        "ARCHIVE": "#ARCHIVE",
        "SYNC": "#SYNC",
        "MANUAL": "#MANUAL",
    }
    tag = hashtags.get(status, "#LOG")
    lines = [f"**{status}** | `{phone}`", f"🕒 `{time_str}`"]
    if user_id:
        lines.append(f"👤 `{user_id}`")
    if extra:
        lines.append(f"ℹ️ {extra}")
    lines.append(f"\n{tag}")
    return "\n".join(lines)


async def sync_from_drive(force: bool = False) -> int:
    async with sessions_lock:
        files = drive_list_files(DRIVE_FOLDER_ID)
        index = load_index()
        seen_phones = set()
        free_count = 0

        for f in files:
            name = f["name"]
            if not name.lower().endswith(".session"):
                continue
            phone = extract_phone_from_filename(name)
            if not phone:
                continue
            seen_phones.add(phone)
            is_used = name.upper().startswith("[USED]_") or name.upper().startswith("USED_")
            if is_used:
                m = re.search(r'_(VALID|NOVALID|DEAD|ERROR|USED|FREE)$', Path(name).stem, re.I)
                status = m.group(1).upper() if m else "USED"
            else:
                status = "FREE"
                free_count += 1
            old = index.get(phone, {})
            index[phone] = {
                "phone": phone,
                "status": status,
                "filename": name,
                "file_id": f["id"],
                "updated": now_str() if force or old.get("file_id") != f["id"] else old.get("updated", now_str()),
            }
        to_del = [k for k in index if k not in seen_phones]
        for k in to_del:
            del index[k]
        save_index(index)
        return free_count


async def claim_session():
    async with sessions_lock:
        index = load_index()
        free_keys = [
            k for k, v in index.items()
            if v.get("status") == "FREE" and k not in in_use
        ]
        if not free_keys:
            return None, None, None, None
        key = sorted(free_keys)[0]
        in_use.add(key)
        entry = index[key]
        phone = entry.get("phone", key)
        file_id = entry.get("file_id")
        if not file_id:
            entry["status"] = "DEAD"
            entry["updated"] = now_str()
            save_index(index)
            in_use.discard(key)
            return None, None, None, None
        local_path = SESSIONS_DIR / f"{phone}.session"
        try:
            drive_download(file_id, local_path)
        except Exception as e:
            print(f"[DOWNLOAD] {phone}: {e}")
            entry["status"] = "DEAD"
            entry["updated"] = now_str()
            save_index(index)
            in_use.discard(key)
            return None, None, None, None
        new_name = make_drive_name(phone, "USED")
        try:
            drive_rename(file_id, new_name)
            entry["filename"] = new_name
        except Exception as e:
            print(f"[RENAME USED] {phone}: {e}")
        entry["status"] = "USED"
        entry["updated"] = now_str()
        save_index(index)
        return key, local_path, phone, file_id


async def release_session(key: str):
    async with sessions_lock:
        in_use.discard(key)


async def update_session_status(key: str, status: str):
    async with sessions_lock:
        index = load_index()
        if key not in index:
            return
        entry = index[key]
        entry["status"] = status
        entry["updated"] = now_str()
        phone = entry.get("phone", key)
        file_id = entry.get("file_id")
        save_index(index)
    if file_id:
        new_name = make_drive_name(phone, status)
        try:
            drive_rename(file_id, new_name)
            async with sessions_lock:
                index = load_index()
                if key in index:
                    index[key]["filename"] = new_name
                    save_index(index)
        except Exception as e:
            print(f"[RENAME {status}] {phone}: {e}")


async def check_one_account(session_path: Path, start_param: str) -> str:
    phone = session_path.stem
    print(f"[+] Проверяю {phone} ...")
    session_name = str(session_path.with_suffix(""))
    client = TelegramClient(
        session_name, API_ID, API_HASH,
        device_model="PC", system_version="Windows 10",
        app_version="4.0", lang_code="ru"
    )
    try:
        async with asyncio.timeout(14):
            await client.connect()
            if not await client.is_user_authorized():
                print(f"[-] {phone} — не авторизован")
                return "DEAD"
            await client(StartBotRequest(bot=MAMBA_BOT, peer=MAMBA_BOT, start_param=start_param))
            await asyncio.sleep(2.4)
            messages = await client.get_messages(MAMBA_BOT, limit=12)
            for msg in messages:
                text = (msg.message or "").lower()
                if "поздравляем" in text and "анкета подтверждена" in text:
                    print(f"[✓] {phone} — VALID")
                    return "VALID"
                if ("что-то пошло не так" in text or "something is wrong" in text or
                    "не может использоваться для подтверждения" in text or
                    "был использован ранее" in text):
                    print(f"[×] {phone} — NOVALID")
                    return "NOVALID"
            print(f"[?] {phone} — нет понятного ответа → NOVALID")
            return "NOVALID"
    except asyncio.TimeoutError:
        print(f"[T] {phone} — таймаут")
        return "ERROR"
    except (AuthKeyUnregisteredError, UserDeactivatedError):
        print(f"[D] {phone} — мёртвый")
        return "DEAD"
    except SessionPasswordNeededError:
        print(f"[2FA] {phone} — нужен пароль")
        return "DEAD"
    except FloodWaitError as e:
        print(f"[F] {phone} — FloodWait {e.seconds}с")
        return "ERROR"
    except Exception as e:
        print(f"[E] {phone} — {type(e).__name__}: {e}")
        return "ERROR"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        try:
            session_path.unlink(missing_ok=True)
            Path(str(session_path) + "-journal").unlink(missing_ok=True)
        except Exception:
            pass


def parse_mamba_result(messages) -> str | None:
    for msg in messages:
        text = (msg.message or "").lower()
        if "поздравляем" in text and "анкета подтверждена" in text:
            return "VALID"
        if ("что-то пошло не так" in text or "something is wrong" in text or
            "не может использоваться для подтверждения" in text or
            "был использован ранее" in text):
            return "NOVALID"
    return None


async def cleanup_manual_state(user_id: int):
    state = manual_states.pop(user_id, None)
    if not state:
        return
    task = state.get("watch_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    client = state.get("client")
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    local_path = state.get("local_path")
    if local_path:
        try:
            Path(local_path).unlink(missing_ok=True)
            Path(str(local_path) + "-journal").unlink(missing_ok=True)
        except Exception:
            pass
    key = state.get("key")
    if key:
        await release_session(key)


def extract_login_code(text: str) -> str | None:
    """Достаёт код входа из сообщения Telegram (777000)."""
    if not text:
        return None
    # типичные форматы: "Login code: 12345", "Код для входа: 12345", просто 5-6 цифр
    patterns = [
        r'(?:login code|код для входа|код входа|code)[^\d]{0,20}(\d{5,6})',
        r'(\d{5,6})\s*(?:is your|— ваш|ваш код)',
        r'\b(\d{5,6})\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


async def watch_mamba(user_id: int, event):
    """Следит за кодами от Telegram (777000) и за ответами Mamba."""
    state = manual_states.get(user_id)
    if not state:
        return
    client = state["client"]
    phone = state["phone"]
    key = state["key"]
    status_msg = state.get("status_msg")
    deadline = asyncio.get_event_loop().time() + MANUAL_WATCH_SECONDS
    seen_code_ids: set[int] = set()
    code_sent = False

    try:
        while asyncio.get_event_loop().time() < deadline:
            if user_id not in manual_states:
                return

            try:
                # --- 1. Ловим код от официального Telegram (777000) ---
                try:
                    tg_msgs = await client.get_messages(777000, limit=5)
                    for msg in tg_msgs:
                        if msg.id in seen_code_ids:
                            continue
                        seen_code_ids.add(msg.id)
                        code = extract_login_code(msg.message or "")
                        if code and not code_sent:
                            code_sent = True
                            await event.respond(
                                f"🔑 **Код для входа** (`{phone}`):\n\n"
                                f"`{code}`\n\n"
                                f"Введи его в Telegram."
                            )
                            print(f"[CODE] {phone}: {code}")
                except Exception as e:
                    print(f"[CODE CHECK] {phone}: {e}")

                # --- 2. Смотрим ответы Mamba ---
                messages = await client.get_messages(MAMBA_BOT, limit=15)
                result = parse_mamba_result(messages)

                if result == "VALID":
                    await update_session_status(key, "VALID")
                    text = (
                        f"✅ **Mamba верифицирована**\n\n"
                        f"Аккаунт: `{phone}`\n\n"
                        f"Mamba verif"
                    )
                    if status_msg:
                        try:
                            await status_msg.edit(text)
                        except Exception:
                            await event.respond(text)
                    else:
                        await event.respond(text)
                    await send_log(bot, make_log("VALID", phone, "Ручной режим", user_id))
                    await cleanup_manual_state(user_id)
                    return

                if result == "NOVALID":
                    await update_session_status(key, "NOVALID")
                    await release_session(key)
                    state["key"] = None
                    msg = f"❌ NOVALID — `{phone}`\nБеру следующий номер..."
                    if status_msg:
                        try:
                            await status_msg.edit(msg)
                        except Exception:
                            await event.respond(msg)
                    else:
                        await event.respond(msg)
                    await send_log(bot, make_log("NOVALID", phone, "Ручной режим", user_id))
                    await start_manual_round(event, user_id)
                    return

            except (AuthKeyUnregisteredError, UserDeactivatedError):
                await update_session_status(key, "DEAD")
                await release_session(key)
                state["key"] = None
                await event.respond(f"💀 DEAD — `{phone}`\nБеру следующий...")
                await start_manual_round(event, user_id)
                return
            except Exception as e:
                print(f"[WATCH] {phone}: {e}")

            await asyncio.sleep(MANUAL_POLL_INTERVAL)

        # время вышло
        await update_session_status(key, "NOVALID")
        await release_session(key)
        state["key"] = None
        await event.respond(
            f"⏳ Время ожидания вышло — `{phone}`\n"
            f"Помечаю NOVALID, беру следующий номер..."
        )
        await send_log(bot, make_log("NOVALID", phone, "Таймаут ожидания (ручной)", user_id))
        await start_manual_round(event, user_id)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[WATCH FATAL] {e}")
        await event.respond(f"❌ Ошибка наблюдения: `{e}`")
        await cleanup_manual_state(user_id)


async def start_manual_round(event, user_id: int):
    state = manual_states.get(user_id)
    if not state:
        return

    old_task = state.get("watch_task")
    if old_task and not old_task.done():
        old_task.cancel()
        try:
            await old_task
        except asyncio.CancelledError:
            pass

    old_client = state.get("client")
    if old_client:
        try:
            await old_client.disconnect()
        except Exception:
            pass
        state["client"] = None

    old_path = state.get("local_path")
    if old_path:
        try:
            Path(old_path).unlink(missing_ok=True)
            Path(str(old_path) + "-journal").unlink(missing_ok=True)
        except Exception:
            pass

    key, local_path, phone, file_id = await claim_session()
    if key is None:
        free = await sync_from_drive()
        if free == 0:
            await event.respond(
                "📭 Свободных аккаунтов больше нет.\n"
                "Загрузи .session в Google Drive и сделай /sync."
            )
            await cleanup_manual_state(user_id)
            await send_log(bot, make_log("EMPTY", "—", "Ручной режим: база пуста", user_id))
            return
        key, local_path, phone, file_id = await claim_session()
        if key is None:
            await event.respond("📭 Свободных аккаунтов нет.")
            await cleanup_manual_state(user_id)
            return

    state["key"] = key
    state["phone"] = phone
    state["file_id"] = file_id
    state["local_path"] = local_path
    state["tried"] = state.get("tried", 0) + 1

    session_name = str(Path(local_path).with_suffix(""))
    client = TelegramClient(
        session_name, API_ID, API_HASH,
        device_model="PC", system_version="Windows 10",
        app_version="4.0", lang_code="ru"
    )
    await client.connect()
    state["client"] = client

    if not await client.is_user_authorized():
        await update_session_status(key, "DEAD")
        await release_session(key)
        state["key"] = None
        try:
            await client.disconnect()
        except Exception:
            pass
        await event.respond(f"💀 `{phone}` — сессия не авторизована (DEAD). Беру следующий...")
        await start_manual_round(event, user_id)
        return

    status_msg = await event.respond(
        f"📱 **Номер:** `{phone}`\n"
        f"Попытка: {state['tried']}\n\n"
        f"👀 Жду код от Telegram и слежу за Mamba ({MANUAL_WATCH_SECONDS} сек)...\n"
        f"Нажми ссылку / войди с этого аккаунта — код пришлю сюда.\n\n"
        f"/next — сразу следующий номер\n"
        f"/cancel — отмена"
    )
    state["status_msg"] = status_msg
    await send_log(bot, make_log("MANUAL", phone, f"Выдан номер (попытка {state['tried']})", user_id))

    task = asyncio.create_task(watch_mamba(user_id, event))
    state["watch_task"] = task


async def update_status(status_msg, text: str):
    try:
        await status_msg.edit(text)
        return status_msg
    except Exception:
        try:
            return await status_msg.respond(text)
        except Exception:
            return status_msg


async def process_verification(event, start_param: str, bot_client: TelegramClient):
    user_id = event.sender_id
    status_msg = await event.reply("🔄 Запрос принят, начинаю перебор...")
    await send_log(bot_client, make_log("START", "—", f"start=`{start_param[:45]}...`", user_id))
    tried = 0
    max_tries = 40
    while tried < max_tries:
        key, local_path, phone, _ = await claim_session()
        if key is None:
            free = await sync_from_drive()
            if free == 0:
                status_msg = await update_status(
                    status_msg,
                    "📭 Свободных аккаунтов больше нет.\nНужно пополнение (загрузи .session в папку Google Drive)."
                )
                await send_log(bot_client, make_log("EMPTY", "—", "База закончилась", user_id))
                return
            key, local_path, phone, _ = await claim_session()
            if key is None:
                status_msg = await update_status(
                    status_msg,
                    "📭 Свободных аккаунтов больше нет.\nНужно пополнение."
                )
                await send_log(bot_client, make_log("EMPTY", "—", "База закончилась", user_id))
                return
        tried += 1
        status_msg = await update_status(status_msg, f"🔄 [{tried}] Пробую `{phone}`...")
        await update_session_status(key, "USED")
        result = await check_one_account(local_path, start_param)
        await release_session(key)
        if result == "VALID":
            await update_session_status(key, "VALID")
            status_msg = await update_status(
                status_msg,
                f"✅ **Mamba верифицирована**\n\nАккаунт: `{phone}`"
            )
            await send_log(bot_client, make_log("VALID", phone, "Успешная верификация", user_id))
            return
        elif result == "NOVALID":
            await update_session_status(key, "NOVALID")
            await send_log(bot_client, make_log("NOVALID", phone, "Аккаунт отклонён", user_id))
            continue
        elif result == "DEAD":
            await update_session_status(key, "DEAD")
            await send_log(bot_client, make_log("DEAD", phone, "Не авторизован / мёртвый", user_id))
            continue
        else:
            await update_session_status(key, "FREE")
            await send_log(bot_client, make_log("ERROR", phone, "Таймаут / ошибка (сессия возвращена)", user_id))
            continue
    status_msg = await update_status(
        status_msg,
        "⚠️ Не удалось подтвердить.\n\n"
        "Возможные причины:\n"
        "• Ссылка устарела\n"
        "• Все доступные аккаунты уже использованы\n"
        "• Временные сбои"
    )
    await send_log(bot_client, make_log("END", "—", "Не удалось подтвердить после перебора", user_id))


bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


@bot.on(events.NewMessage(pattern=r'^/archive$'))
async def archive_cmd(event):
    if not await is_admin(event.sender_id):
        return
    status = await event.reply("📦 Начинаю архивацию (Google Drive)...")
    try:
        files = drive_list_files(DRIVE_FOLDER_ID)
        to_archive = [
            f for f in files
            if f["name"].upper().startswith("[USED]_") or f["name"].upper().startswith("USED_")
        ]
        if not to_archive:
            await status.edit("Нечего архивировать — нет файлов с префиксом [USED]_.")
            return
        archive_num = datetime.now().strftime("%Y%m%d_%H%M%S")
        moved = 0
        errors = 0
        for i, f in enumerate(to_archive, 1):
            try:
                drive_move(f["id"], DRIVE_ARCHIVE_FOLDER_ID, DRIVE_FOLDER_ID)
                moved += 1
            except Exception as e:
                print(f"[ARCHIVE] {f['name']}: {e}")
                errors += 1
            if i % 5 == 0 or i == len(to_archive):
                try:
                    await status.edit(f"📦 Архивация...\n{moved}/{len(to_archive)}")
                except Exception:
                    pass
        index = load_index()
        for f in to_archive:
            phone = extract_phone_from_filename(f["name"])
            if phone in index:
                del index[phone]
        save_index(index)
        text = (
            f"✅ Архивация #{archive_num} завершена.\n"
            f"Перенесено в папку «архив»: {moved}\n"
            f"Ошибок: {errors}"
        )
        try:
            await status.edit(text)
        except Exception:
            await event.respond(text)
        await send_log(bot, make_log("ARCHIVE", "—", f"#{archive_num}, {moved} файлов"))
    except Exception as e:
        err = f"❌ Ошибка архивации:\n`{type(e).__name__}: {e}`"
        try:
            await status.edit(err)
        except Exception:
            await event.respond(err)


@bot.on(events.NewMessage(pattern=r'^/sync$'))
async def sync_cmd(event):
    if not await is_admin(event.sender_id):
        return
    status = await event.reply("🔄 Синхронизирую с Google Drive...")
    try:
        free = await sync_from_drive(force=True)
        index = load_index()
        await status.edit(
            f"✅ Синхронизация завершена.\n"
            f"📁 Всего в индексе: `{len(index)}`\n"
            f"🟢 Свободных (FREE): `{free}`"
        )
        await send_log(bot, make_log("SYNC", "—", f"free={free}, total={len(index)}"))
    except Exception as e:
        await status.edit(f"❌ Ошибка синхронизации:\n`{type(e).__name__}: {e}`")


@bot.on(events.NewMessage(pattern=r'^/stats$'))
async def stats_cmd(event):
    if not await is_admin(event.sender_id):
        return
    index = load_index()
    free = used = valid = novalid = dead = other = 0
    for entry in index.values():
        st = (entry.get("status") or "").upper()
        if st == "FREE":
            free += 1
        elif st == "USED":
            used += 1
        elif st == "VALID":
            valid += 1
        elif st == "NOVALID":
            novalid += 1
        elif st == "DEAD":
            dead += 1
        else:
            other += 1
    text = (
        f"📊 **Статистика базы (Google Drive)**\n\n"
        f"🟢 Свободно: `{free}`\n"
        f"🟡 В работе: `{used}`\n"
        f"✅ VALID: `{valid}`\n"
        f"❌ NOVALID: `{novalid}`\n"
        f"💀 DEAD: `{dead}`\n"
        f"❓ Прочее: `{other}`\n"
        f"\n📁 Всего в индексе: `{len(index)}`"
    )
    await event.reply(text)


@bot.on(events.NewMessage(pattern=r'^/debug$'))
async def debug_cmd(event):
    if not await is_admin(event.sender_id):
        return
    index = load_index()
    lines = [
        f"DRIVE_FOLDER_ID = `{DRIVE_FOLDER_ID}`",
        f"DRIVE_ARCHIVE_FOLDER_ID = `{DRIVE_ARCHIVE_FOLDER_ID}`",
        f"ADMIN_GROUP = `{ADMIN_GROUP}`",
        "",
        f"📋 Записей в индексе: `{len(index)}`",
        "",
    ]
    for key, entry in list(index.items())[:25]:
        lines.append(
            f"`{entry.get('phone', key)}` — **{entry.get('status')}** "
            f"({entry.get('filename', '?')})"
        )
    if len(index) > 25:
        lines.append(f"... и ещё {len(index) - 25}")
    await event.reply("\n".join(lines))


@bot.on(events.NewMessage(pattern=r'^/manual$'))
async def manual_cmd(event):
    if not event.is_private:
        return
    user_id = event.sender_id
    if user_id in manual_states:
        phone = manual_states[user_id].get("phone", "?")
        await event.reply(
            f"Уже идёт ручной режим (номер `{phone}`).\n"
            f"/next — следующий номер\n"
            f"/cancel — отмена"
        )
        return
    manual_states[user_id] = {
        "tried": 0,
        "key": None,
        "phone": None,
        "client": None,
        "local_path": None,
        "watch_task": None,
        "status_msg": None,
    }
    await event.reply("🖐 Ручной режим. Беру свободный аккаунт...")
    await start_manual_round(event, user_id)


@bot.on(events.NewMessage(pattern=r'^/next$'))
async def next_cmd(event):
    if not event.is_private:
        return
    user_id = event.sender_id
    state = manual_states.get(user_id)
    if not state:
        await event.reply("Ручной режим не запущен. Напиши /manual")
        return
    key = state.get("key")
    phone = state.get("phone", "?")
    task = state.get("watch_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if key:
        await update_session_status(key, "NOVALID")
        await release_session(key)
        state["key"] = None
        await send_log(bot, make_log("NOVALID", phone, "Ручной /next", user_id))
    await event.reply(f"⏭ Пропускаю `{phone}`, беру следующий...")
    await start_manual_round(event, user_id)


@bot.on(events.NewMessage(pattern=r'^/cancel$'))
async def cancel_cmd(event):
    user_id = event.sender_id
    if user_id not in manual_states:
        await event.reply("Нечего отменять.")
        return
    state = manual_states.get(user_id)
    key = state.get("key") if state else None
    phone = state.get("phone", "?") if state else "?"
    if key:
        await update_session_status(key, "FREE")
        await release_session(key)
    await cleanup_manual_state(user_id)
    await event.reply(f"❌ Ручной режим отменён (номер `{phone}` возвращён в FREE).")


@bot.on(events.NewMessage(pattern=r'(?i).*(tg://|start=|mambarubot)'))
async def handle_link(event):
    if not event.is_private:
        return
    if event.sender_id in manual_states:
        return
    text = event.raw_text.strip()
    start_param = None
    match = re.search(r'start=([a-zA-Z0-9_\-]+)', text)
    if match:
        start_param = match.group(1)
    elif re.fullmatch(r'[a-zA-Z0-9_\-]{10,}', text):
        start_param = text
    if not start_param:
        await event.reply("❌ Некорректная ссылка.")
        return
    asyncio.create_task(process_verification(event, start_param, bot))


@bot.on(events.NewMessage(pattern=r'^/start$'))
async def start_cmd(event):
    await event.reply(
        "Пришли ссылку для **автоматической** верификации Мамбы.\n\n"
        "**Ручной режим:**\n"
        "/manual — выдать свободный номер и следить за Mamba\n"
        "/next — пропустить текущий номер, взять следующий\n"
        "/cancel — отменить ручной режим\n\n"
        "Админ:\n"
        "/sync /stats /archive /debug"
    )


print("Бот запущен...")
print(f"Сессии (локальный кэш): {SESSIONS_DIR.resolve()}")
print(f"Индекс: {INDEX_FILE.resolve()}")

try:
    free = asyncio.get_event_loop().run_until_complete(sync_from_drive(force=True))
    print(f"[SYNC] Найдено FREE сессий на Drive: {free}")
except Exception as e:
    print(f"[SYNC ERROR] Не удалось синхронизировать Drive при старте: {e}")
    print("Проверь service_account.json и ID папок в config.py")

bot.run_until_disconnected()
