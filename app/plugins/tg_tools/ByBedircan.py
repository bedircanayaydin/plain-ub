import asyncio
import os
import re
import shutil
import time

from pyrogram import filters
from pyrogram.types import InputMediaDocument
from ub_core.utils import Download, aio

from app import Message, bot


CHANNEL_ID = [-1001743931897, -1001743931897]
APK_CHANNEL_ID = {
    -1001743931897:
        {
            "id": -1001743931897,
            "info":
                "👥 Join\n📣 @XposedRepository \n"+
                "💬 @XposedRepositoryChat \n"+
                "@Xposedapkrepo"
        },
    -1001743931897:
        {
            "id": -1001743931897,
            "info":
                "👥 Join\n📣 @FossDroidAndroid \n"+
                "💬 @FossDroid_AndroidChat \n"+
                "@FossDroid_Android_apkrepo"
        },
}

if bot.bot and bot.bot.is_bot:
    @bot.bot.on_message(
        filters.chat(chats=CHANNEL_ID)
        & ~filters.sticker
        & ~filters.via_bot
        & ~filters.forwarded
    )
    async def _upload_github_apk(_, msg: Message):
        return await upload_github_apk(msg)


async def upload_github_apk(msg: Message):
    data = msg.text or msg.caption
    pattern = r"https?://github\.com/([^/]+)/([^/?#]+)"
    match = re.search(pattern, data.markdown)
    if not match:
        # no github link so ignore
        return
    user, repo = match.group(1), match.group(2)

    if not (user and repo):
        await bot.log_text(f"Invalid URL.\nMessage: {msg.link}", type="info")
        return

    url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"

    release_data = await aio.get_json(url)
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

    grouped_apks[-1].caption = (
            f"📣 New release for **{repo}**\n"+
            f"Version: `{tag_name}`\n\n"+

            body +
            "\n\n"+
            APK_CHANNEL_ID[msg.chat.id]["info"]
    )

    await bot.send_media_group(chat_id=APK_CHANNEL_ID[msg.chat.id]["id"], media=grouped_apks)

    shutil.rmtree(dl_path, ignore_errors=True)
