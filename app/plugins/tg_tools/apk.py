import asyncio
import os
import shutil
import time
from urllib.parse import urlparse

from app import BOT, Message, bot
from pyrogram import filters
from pyrogram.types import InputMediaDocument
from ub_core.utils import Download, aio

CHANNEL_ID = -1001512388271
APK_CHANNEL_ID = -1001512388271

def get_urls(message):
    data = message.text or message.caption
    if not data:
        return
    urls = [x for x in data.split() if "github.com" in x]
    entities = message.entities or []
    entity_urls = [
        entity.url
        for entity in entities
        if (isinstance(entity.url, str) and "github.com" in entity.url)
    ]
    return urls + entity_urls

@bot.on_message(
    filters.chat(chats=CHANNEL_ID)
    & ~filters.sticker
    & ~filters.via_bot
    & ~filters.forwarded
)
async def upload_github_apk(bot: BOT, message: Message):
    urls = get_urls(message)
    if not urls:
        return
    for url in urls:
        await upload_apks(url)

async def upload_apks(url):
    parsed_url = urlparse(url)
    url = f"https://api.github.com/repos{parsed_url.path}/releases/latest"

    release_data = await aio.get_json(url)
    if not release_data:
        return

    assets = release_data.get("assets", [])
    body = release_data.get("body", "")

    to_dl_files = []
    dl_path = os.path.join("downloads", str(time.time()))

    for asset in assets or []:
        if asset["name"].endswith(".apk"):
            apk_link, name = asset["browser_download_url"], asset["name"]
            if apk_link:
                dl_obj = await Download.setup(
                    url=apk_link, path=dl_path, custom_file_name=name
                )
            to_dl_files.append(dl_obj.download())

    downloaded_files = await asyncio.gather(*to_dl_files)

    if not downloaded_files:
        print("No APK files found for this release.")
        return

    grouped_apks = [
        InputMediaDocument(media=apk.full_path)
        for apk in downloaded_files
    ]

    grouped_apks[-1].caption = body

    await bot.send_media_group(chat_id=APK_CHANNEL_ID, media=grouped_apks)

    shutil.rmtree(dl_path, ignore_errors=True)
    
