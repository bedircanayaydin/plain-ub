from pyrogram import filters
from app import bot, BOT, Message

import re
import aiohttp
import logging
from io import BytesIO

CHANNEL_ID = int(-1001674072540)
APK_CHANNEL_ID = int(-1001724179522)

logging.basicConfig(level=logging.INFO)

@bot.on_message(filters.chat(CHANNEL_ID) &
                ~filters.sticker & ~filters.via_bot & ~filters.forwarded)
async def upload_github_apk(c: BOT, msg: Message):
    pattern = r"https?://github\.com/([^/]+)/([^/]+)"
    text = msg.text.markdown if msg.text else (msg.caption.markdown if msg.caption else "")
    if not text:
        return
    match = re.search(pattern, text)
    if not match:
        return
    user, repo = match.group(1), match.group(2)

    if not (user and repo):
        return

    url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                release_data = await response.json()
                assets = release_data.get('assets', [])
                body = release_data.get('body', '')
                for asset in assets:
                    if asset['name'].endswith('.apk'):
                        apk_link, name = asset['browser_download_url'], asset['name']
                        if apk_link:
                            try:
                                async with session.get(apk_link) as apk_response:
                                    if apk_response.status == 200:
                                        file_data = BytesIO(await apk_response.read())
                                        file_data.seek(0)
                                        if file_data:
                                            await c.send_document(APK_CHANNEL_ID, document=file_data, file_name=name, caption=body+"\n\nFollow for more: @FossDroid_AndroidChat 📱✨")
                            except Exception as e:
                                logging.error(f"An error occurred: {e}")
