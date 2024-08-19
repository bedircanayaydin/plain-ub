import asyncio
import os
import re
import shutil
import time
from pyrogram import filters
from pyrogram.types import InputMediaDocument
from googletrans import Translator
from ub_core.utils import Download, aio
from app import Message, bot

CHANNEL_ID = [-1001552586568, -1001674072540]
APK_CHANNEL_ID = {
    -1001552586568: {
        "upload_id": -1001836098073,
        "info": (
            "👥 Join\n📣 @XposedRepository \n"
            "💬 @XposedRepositoryChat \n"
            "@Xposedapkrepo"
        ),
    },
    -1001674072540: {
        "upload_id": -1001724179522,
        "info": (
            "👥 Join\n📣 @FossDroidAndroid \n"
            "💬 @FossDroid_AndroidChat \n"
            "@FossDroid_Android_apkrepo"
        ),
    },
}

async def retry_upload_github_apk(msg: Message, retry_count=5, delay=60):
    for _ in range(retry_count):
        try:
            await upload_github_apk(msg)
            return
        except Exception as e:
            await bot.log_text(f"Error occurred: {e}. Retrying in {delay} seconds...", type="error")
            await asyncio.sleep(delay)

if bot.bot and bot.bot.is_bot:
    @bot.bot.on_message(
        filters.chat(chats=CHANNEL_ID)
        & ~filters.sticker
        & ~filters.via_bot
        & ~filters.forwarded
    )
    async def _upload_github_apk(_, msg: Message):
        await retry_upload_github_apk(msg)

async def upload_github_apk(msg: Message):
    data = msg.text or msg.caption
    pattern = r"https?://github\.com/([^/]+)/([^/?#]+)"
    match = re.search(pattern, data.markdown)
    
    if not match:
        alt_pattern = r"\[.*?(download|source).*?\]\((https?://github\.com/[^/]+/[^/?#]+)\)"
        match = re.search(alt_pattern, data.markdown)
        if match:
            url = match.group(2)
            user, repo = re.search(r"github\.com/([^/]+)/([^/?#]+)", url).groups()
        else:
            return
    else:
        user, repo = match.group(1), match.group(2)

    if not (user and repo):
        await bot.log_text(f"Invalid URL.\nMessage: {msg.link}", type="info")
        return

    paths = [
        f"https://api.github.com/repos/{user}/{repo}/releases/latest",
        f"https://api.github.com/repos/{user}/{repo}/actions/artifacts",
        f"https://api.github.com/repos/{user}/{repo}/tags",
        f"https://api.github.com/repos/{user}/{repo}/releases"
    ]
    
    release_data = None
    for url in paths:
        release_data = await aio.get_json(url)
        if release_data and release_data.get("assets"):
            break

    if not release_data:
        await bot.log_text(f"No release data found.\nMessage: {msg.link}", type="info")
        return

    tag_name = release_data.get("name", "")
    assets = release_data.get("assets", [])
    body = release_data.get("body", "")

    to_dl_files = []
    dl_path = os.path.join("downloads", str(time.time()))

    for asset in assets or []:
        if asset["name"].lower().endswith(".apk"):
            apk_link, name = asset["browser_download_url"], asset["name"]
            if apk_link:
                dl_obj = await Download.setup(
                    url=apk_link, path=dl_path, custom_file_name=name
                )
                to_dl_files.append(dl_obj.download())

    downloaded_files = await asyncio.gather(*to_dl_files)

    if not downloaded_files:
        await bot.log_text(f"No APK files found for this release.\nMessage: {msg.link}", type="info")
        return

    grouped_apks = [
        InputMediaDocument(media=apk.full_path)
        for apk in downloaded_files
    ]

    if not grouped_apks:
        await bot.log_text(f"No APK files found for this release.\nMessage: {msg.link}", type="info")
        return

    translator = Translator()
    detected_lang = translator.detect(body).lang

    if detected_lang != 'en':
        body = translator.translate(body, dest='en').text

    body = body.split('**Full Changelog**: https://github.com/')[0].rstrip()
    
    if len(body) > 2**9:
        body = f"{body[:2**9]}..."
        
    body += f"\n\n**[Full Changelog](https://github.com/{user}/{repo}/releases/latest)**"
        
    channel_info = APK_CHANNEL_ID[msg.chat.id]

    grouped_apks[-1].caption = (
            f"📣 New release for **{repo}**\n"+
            f"Version: `{tag_name}`\n\n"+
            body +
            "\n\n"+
            channel_info["info"]
    )

    await bot.send_media_group(chat_id=channel_info["upload_id"], media=grouped_apks)

    shutil.rmtree(dl_path, ignore_errors=True)
    
