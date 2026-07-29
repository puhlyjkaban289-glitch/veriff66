import json
import os
import traceback

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ================= CONFIG =================
SPREADSHEET_ID = "ВСТАВЬ_СЮДА_ID_ТАБЛИЦЫ"
RANGE_NAME = "Sheet1!A:C"
# =========================================


def debug_print(title, value):
    print(f"\n=== {title} ===")
    print(value)


def test_google():
    try:
        print("\n🚀 START DEBUG\n")

        # ===== 1. Проверка файлов =====
        files = os.listdir()
        debug_print("FILES IN DIR", files)

        if "credentials.json" not in files:
            raise Exception("❌ credentials.json NOT FOUND")

        # ===== 2. Чтение файла =====
        with open("credentials.json", "r", encoding="utf-8") as f:
            raw = f.read()

        debug_print("RAW FILE START", raw[:200])

        creds_dict = json.loads(raw)

        # ===== 3. Проверка полей =====
        debug_print("CLIENT EMAIL", creds_dict.get("client_email"))
        debug_print("PROJECT ID", creds_dict.get("project_id"))

        private_key = creds_dict.get("private_key")
        if not private_key:
            raise Exception("❌ private_key NOT FOUND")

        debug_print("PRIVATE KEY START", private_key[:50])

        # ===== 4. Проверка формата ключа =====
        if "\\n" in private_key:
            print("\n⚠️ ВНИМАНИЕ: В ключе есть \\n (это ОК для env, но плохо если криво вставлено)")
        if "BEGIN PRIVATE KEY" not in private_key:
            raise Exception("❌ PRIVATE KEY FORMAT BROKEN")

        # ===== 5. Создание credentials =====
        print("\n🔐 Creating credentials...")
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )

        print("✅ Credentials created")

        # ===== 6. Создание сервиса =====
        print("\n🌐 Connecting to Google Sheets...")
        service = build("sheets", "v4", credentials=creds)

        print("✅ Service created")

        # ===== 7. Пробный запрос =====
        print("\n📊 Testing access to spreadsheet...")

        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME
        ).execute()

        debug_print("SHEETS RESPONSE", result)

        print("\n🎉 ВСЁ РАБОТАЕТ")

    except Exception as e:
        print("\n❌ ERROR OCCURRED\n")
        print(str(e))
        print("\n📜 TRACEBACK:")
        traceback.print_exc()


if __name__ == "__main__":
    test_google()
