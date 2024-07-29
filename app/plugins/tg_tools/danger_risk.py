import asyncio
import logging
import os
import re
import shutil
import time

from pyrogram import filters
from pyrogram.types import InputMediaDocument
from ub_core.utils import Download, aio

from app import Message, bot

logging.basicConfig(level=logging.INFO)

CHANNEL_ID = -1001674072540
APK_CHANNEL_ID = -1001724179522

def get_urls(message):
    data = message.text or message.caption
    if not data:
        logging.info("No data found.")
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
async def upload_github_apk(_, message: Message):
    urls = get_urls(message)
    if not urls:
        logging.info("No URLs found.")
        return
    for url in urls:
        await upload_apks(url)

async def upload_apks(url):
    pattern = r"https?://github\.com/([^/]+)/([^/]+)"
    match = re.search(pattern, url)
    if not match:
        logging.info("Invalid URL.")
        return
    user, repo = match.group(1), match.group(2)

    if not (user and repo):
        logging.info("Invalid URL.")
        return

    url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"

    release_data = await aio.get_json(url)
    if not release_data:
        logging.info("No release data found.")
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
        logging.info("No APK files found for this release.")
        return

    grouped_apks = [
        InputMediaDocument(media=apk.full_path)
        for apk in downloaded_files
    ]

    if not grouped_apks:
        logging.info("No APK files found for this release.")
        return

    grouped_apks[-1].caption = (
            body +
            "\n\n"+
            "👥 Join\n📣 @FossDroidAndroid \n"+
            "💬 @FossDroid_AndroidChat \n"+
            "🆙 @Fossdroidupdate_Repo\n"+
            "@FossDroid_Android_apkrepo"
    )

    await bot.send_media_group(chat_id=APK_CHANNEL_ID, media=grouped_apks)

    shutil.rmtree(dl_path, ignore_errors=True)
