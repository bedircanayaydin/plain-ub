from pyrogram import filters
from app import bot, BOT, Message

import re
import requests
CHANNEL_ID = int(-1001674072540)
APK_CHANNEL_ID = int(-1001724179522)


@bot.on_message(filters.chat(chats=CHANNEL_ID) &
                ~filters.sticker & ~filters.via_bot & ~filters.forwarded)
async def upload_github_apk(c: BOT, msg: Message):
    pattern = r"https?://github\.com/([^/]+)/([^/]+)"
    match = re.search(msg.text.markdown if msg.text else msg.caption.markdown)
    if not match:
        return
    user, repo = match.group(1), match.group(2)

    if not (user and repo):
        return

    url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"
    response = requests.get(url)
    if response.status_code == 200:
        release_data = response.json()
        assets = release_data.get('assets', [])
        body = release_data.get('body', '')
        for asset in assets:
            if asset['name'].endswith('.apk'):
                apk_link, name = asset['browser_download_url'], asset['name']
                if apk_link:
                    try:
                        response = requests.get(url, stream=True)
                        if response.status_code == 200:
                            file_data = BytesIO()
                            for chunk in response.iter_content(chunk_size=8192):
                                file_data.write(chunk)
                            file_data.seek(0)
                            if file_data:
                                await c.send_document(APK_CHANNEL_ID, document=file_data, file_name=name, caption=body+"\n\nFollow for more: @FossDroid_AndroidChat 📱✨")
                    except Exception as e:
                        print(f"An error occurred: {e}")