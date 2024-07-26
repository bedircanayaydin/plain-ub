from pyrogram import filters
from app import bot, BOT, Message
from ub_core.utils import aio

import re

CHANNEL_ID = int(-1001674072540)
APK_CHANNEL_ID = int(-1001724179522)


@bot.on_message(filters.chat(chats=-1001674072540) &
                ~filters.sticker & ~filters.via_bot & ~filters.forwarded)
async def upload_github_apk(c: BOT, message: Message):
    data = message.text or caption 
    if not data:
        return 
    pattern = r"https?://github\.com/([^/]+)/([^/]+)"
    match = re.search(data, pattern)
    if not match:
        return
    user, repo = match.group(1), match.group(2)

    if not (user and repo):
        return

    url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"
    response = await aio.get_json(url)
    if not response:
        return 
    else:
        release_data = response
        assets = release_data.get('assets', [])
        body = release_data.get('body', '')
        for asset in assets:
            if asset['name'].endswith('.apk'):
                apk_link, name = asset['browser_download_url'], asset['name']
                if apk_link:
                    try:
                        file_data = await aio.in_memory_dl(app_link)
                        if file_data:
                                await c.send_document(-1001724179522, document=file_data, file_name=name, caption=body+"\n\nFollow for more: @FossDroid_AndroidChat 📱✨")
                    except Exception as e:
                        print(f"An error occurred: {e}")
