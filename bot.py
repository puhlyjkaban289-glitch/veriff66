import asyncio
import random
import json
import re
from pathlib import Path
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.functions.messages import StartBotRequest
from telethon.errors import (
    FloodWaitError,
    AuthKeyUnregisteredError,
    UserDeactivatedError,
)

from config import API_ID, API_HASH, MAMBA_BOT

# ================= НАСТРОЙКИ =================

PARALLEL = 5              # оптимально 3–7
DELAY_MIN = 0.5
DELAY_MAX = 1.5
SESSION_COOLDOWN = 3
TIMEOUT = 20

SESSIONS_DIR = Path("data/sessions")

# ============================================

SEM = asyncio.Semaphore(PARALLEL)
last_used = {}

# ================= УТИЛИТЫ ==================

def now():
    return datetime.now().strftime("%H:%M:%S")


def log(text):
    print(f"[{now()}] {text}")


async def human_delay():
    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def get_sessions():
    return list(SESSIONS_DIR.glob("*.session"))


# ================= АНТИБАН ==================

async def safe_request(fn):
    try:
        await human_delay()
        return await fn()

    except FloodWaitError as e:
        if e.seconds > 60:
            log(f"⏭ SKIP flood {e.seconds}s")
            return "SKIP"

        log(f"⏳ flood {e.seconds}s")
        await asyncio.sleep(e.seconds + random.uniform(1, 5))

    except (AuthKeyUnregisteredError, UserDeactivatedError):
        return "DEAD"

    except Exception as e:
        log(f"⚠ ERROR {e}")
        await asyncio.sleep(random.uniform(1, 3))


# ================= ОСНОВА ==================

async def process_session(session_path: Path):

    session_name = session_path.stem

    now_time = asyncio.get_running_loop().time()

    # cooldown
    if session_name in last_used:
        if now_time - last_used[session_name] < SESSION_COOLDOWN:
            return

    last_used[session_name] = now_time

    async with SEM:
        try:
            async with TelegramClient(
                str(session_path),
                API_ID,
                API_HASH
            ) as client:

                async def action():
                    return await client(StartBotRequest(
                        bot=MAMBA_BOT,
                        start_param="start"
                    ))

                result = await asyncio.wait_for(
                    safe_request(action),
                    timeout=TIMEOUT
                )

                if result == "DEAD":
                    log(f"💀 DEAD {session_name}")
                    return "DEAD"

                log(f"✅ OK {session_name}")
                return "OK"

        except asyncio.TimeoutError:
            log(f"⌛ TIMEOUT {session_name}")

        except Exception as e:
            log(f"❌ FAIL {session_name}: {e}")


# ================= ВОРКЕР ==================

queue = asyncio.Queue()


async def worker():

    while True:
        session = await queue.get()

        try:
            await process_session(session)

        finally:
            await asyncio.sleep(random.uniform(1, 3))
            await queue.put(session)


# ================= ЗАПУСК ==================

async def main():

    sessions = get_sessions()

    if not sessions:
        log("❌ Нет сессий")
        return

    log(f"🚀 Загружено сессий: {len(sessions)}")

    for s in sessions:
        await queue.put(s)

    workers = [
        asyncio.create_task(worker())
        for _ in range(PARALLEL)
    ]

    await asyncio.gather(*workers)


if __name__ == "__main__":
    asyncio.run(main())
