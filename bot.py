import os
import json
import base64

API_ID = 33176149
API_HASH = "f8fee085ca54498cf18129a84b82b2d8"
BOT_TOKEN = "8693154609:AAGnJb2a8RZz6KpDH8WD1A27jk_Sw9-KoxQ"

MAMBA_BOT = "mambarubot"
LOG_CHANNEL = -1003927369239
ADMIN_GROUP = -1003927369239

DRIVE_FOLDER_ID = "1_3wDOk7KtrHWnGj66eTJCcf-0tgvhq7z"
DRIVE_ARCHIVE_FOLDER_ID = "1rMJonXZZhpxrlBvw2Y2mvUiVHHcUXGz3"

# === BASE64 GOOGLE CREDS ===
b64 = os.getenv("GOOGLE_CREDS_B64")

if not b64:
    raise ValueError("GOOGLE_CREDS_B64 not set")

GOOGLE_CREDS = json.loads(base64.b64decode(b64).decode("utf-8"))
GOOGLE_CREDS["private_key"] = GOOGLE_CREDS["private_key"].replace("\\n", "\n")

def main():
    print("BOT STARTED (BASE64 SECURE)")
    print("Drive:", DRIVE_FOLDER_ID)

if __name__ == "__main__":
    main()
