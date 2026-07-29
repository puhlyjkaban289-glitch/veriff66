import json

# ================= CONFIG (EMBEDDED) =================
API_ID = 33176149
API_HASH = "f8fee085ca54498cf18129a84b82b2d8"
BOT_TOKEN = "8693154609:AAGnJb2a8RZz6KpDH8WD1A27jk_Sw9-KoxQ"

MAMBA_BOT = "mambarubot"
LOG_CHANNEL = -1003927369239
ADMIN_GROUP = -1003927369239

DRIVE_FOLDER_ID = "1_3wDOk7KtrHWnGj66eTJCcf-0tgvhq7z"
DRIVE_ARCHIVE_FOLDER_ID = "1rMJonXZZhpxrlBvw2Y2mvUiVHHcUXGz3"

GOOGLE_CREDS = {
  "type": "service_account",
  "project_id": "western-throne-480622-h0",
  "private_key_id": "723c68131d367ca408d688d59fed1bfeb3ead2d6",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCvOfRLagVF6YG/\nQlCuH5ttXtrxqGoEnzIDsTI6kyD6XIfrnjAKpFMmREAOpDlxkciohjjSKrKGlOz3\nq4NGqrnxMduGY/TV5ALEbCLeNY6MRpdGMIOgAy+uxUmQiZHpcw7zxrKjL37Ji1hU\nl6yPhIXpFeO0lDKqsKMfmej98+ehKSaTZYYQcbwJ8eqTedtYAM7dhAhdenMaFlMA\neM+L09fbuQTiAajnTxsleTO90wQfyBSe2nYQnokoZ/bvDVT+FbRDlkJH2xGmjQ4x\nQi4weiGTqAPXVxRAZnggTM3QmDW02m7BUgKl7qUPo8lIz57VArlFzCGWO4E4UK/u\nSHBPljVBAgMBAAECggEAA4MnuNdjazudSBXQjYF033UT0h1NQPoGjfc0R7MbWZZf\nS3ldetig8azjfHGldL+6fhmI5/pO71p6yqL+kd0GJrHwTbQJKEyKg0i8PRBVcu2P\nLqMWP9fRgdUqupvd08hEiu2TJwkKp2hAiztKNEsglqfDk3sHHheV4PpAJr8/39Gt\ngiI5BevoQB6Ukx/J52arJ60DYqLnP7jUiP8DJwJyY21CFsB/4sUQy1c19nGX8p7m\ngW5uzp6mGeTUAu3FWDs4iCtV83aiO+pXattK3kJN1TGug2rxXX6NHAqn5vSx7mfs\nPqeWi0GEArWAOcwZBkX/iCFlOUVRMVAss+ALTb3VoQKBgQDX0zBRcaN/4+7qft6f\nBbVNAKz+0eiOZUFhY2FzIgwFAya7R/It3PrSGNdMlRpk2RY7c8QwqhCF3c70SpoO\noTPPTm1TbzuebXawMFmOrApeEw4wH3HwFOXibm6rkgE6ZLuv1eG3A+ZxL+uyD5Qq\nU31jEkgu2lwNMOrgb7ou4ihKoQKBgQDP2Boizb9r24Ev8Y4q2WQITwRF6+d3XmUe\nwuHA2vW00ruu9B5Zf+jojJkTDiJPB+B3Tm60UtBZdGyurIHJ3fslgFO9WB24v2KC\n0iPjefPqEFTM7uB9AML2Xyh72n1m4IJMSw1Cf4JU8mT+s9NJOEkjxsCWz7fHXJcn\nV9+Zhc+GoQKBgGjMfMbfZmQAew/UwSb4r5uPe3FU3hbe5gtzJWuxmaKJcDI6ckeA\n6S5Br7HZKPLVUu1Vfmue+Nz34rlOzFXUQwMj8wQznACG6L4PDD2yHmql2BrX+gx5\nKVN1Cjo3cG85YMW2Fp82vpwxh8JzvB99YQJNa02M7GvfV/3ZYs/HM4dhAoGBAKNo\n3jOa2/Mq40kUe5gIzvMRXOS0comRN6OVyPRdsmx2eoU0/V+Uh0O+tuMaa7MDGGH0\n0mkH6zNJq+ExU+GomzqCyFPHoaaNIiCEox7H1ROjv2hYLztYi/A0JJor0AhAX3Eo\nWMZ9hbTP1sPCEk4w6KAuNWDc8zrU+yo9llkXsW/BAoGAZGLwvuj5PEhLPDcIZvwB\n6qdHieDk5p19tcLBUbtUObYkJ+/EH3FGaYfKP6EstogeY7r257smRhbzbzPFPqOi\n83VdKXBZwOnea4CI30+8+Vfzhpokp4jY2NpIGH67QKn7vWwmn6AYQyos7oDcucNm\nAJomW56rFKAxo0ZjXB4aqbE=\n-----END PRIVATE KEY-----\n",
  "client_email": "dolphin-anty-proxy@western-throne-480622-h0.iam.gserviceaccount.com",
  "client_id": "110322442431234326760",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/dolphin-anty-proxy%40western-throne-480622-h0.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

# Fix private key formatting
GOOGLE_CREDS["private_key"] = GOOGLE_CREDS["private_key"].replace("\\n", "\n")

def main():
    print("=== BOT STARTED ===")
    print("API_ID:", API_ID)
    print("Drive folder:", DRIVE_FOLDER_ID)

if __name__ == "__main__":
    main()
