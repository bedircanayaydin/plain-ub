import asyncio
import os
import re
import shutil
import time

from pyrogram import filters
from pyrogram.types import InputMediaDocument
from ub_core.utils import Download, aio

from app import Message, bot

CHANNEL_ID = [-1001552586568, -1001674072540]
APK_CHANNEL_ID = {
    -1001552586568:
        {
            "id": -1001836098073,
            "info":
                "👥 Join\n📣 @XposedRepository \n"+
                "💬 @XposedRepositoryChat \n"+
                "@Xposedapkrepo"
        },
    -1001674072540:
        {
            "id": -1001724179522,
            "info":
                "👥 Join\n📣 @FossDroidAndroid \n"+
                "💬 @FossDroid_AndroidChat \n"+
                "@FossDroid_Android_apkrepo"
        },
}

if bot.bot and bot.bot.is_bot:
    @bot.bot.on_message(
        filters.chat(chats=CHANNEL_ID) & ~filters.sticker & ~filters.via_bot & ~filters.forwarded
    )
    async def _upload_github_apk(_, msg: Message):
        return await upload_github_apk(msg)

async def upload_github_apk(msg: Message):
    data = msg.text or msg.caption
    if not data:
        await bot.log_text(f"No text or caption found in the message.\nMessage: {msg.link}", type="info")
        return

    # Check if message contains a direct APK link
    direct_apk_pattern = r"https?://github\.com/[^/]+/[^/]+/releases/download/[^/]+/[^/]+\.apk"
    direct_apk_match = re.search(direct_apk_pattern, data)
    if direct_apk_match:
        apk_link = direct_apk_match.group(0)
        await process_apk_download(apk_link, msg)
        return

    # Check if message contains a GitHub repository URL
    repo_pattern = r"https?://github\.com/([^/]+)/([^/?#]+)(?:/releases(?:/tag/([^/?#]+))?)?"
    repo_match = re.search(repo_pattern, data)
    if not repo_match:
        await bot.log_text(f"No GitHub URL found in the message.\nMessage: {msg.link}", type="info")
        return

    user, repo, tag = repo_match.group(1), repo_match.group(2), repo_match.group(3)
    if tag:
        url = f"https://api.github.com/repos/{user}/{repo}/releases/tags/{tag}"
    else:
        url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"

    release_data = await aio.get_json(url)
    if not release_data:
        await bot.log_text(f"No release data found.\nMessage: {msg.link}", type="info")
        return

    tag_name = release_data.get("name", "")
    assets = release_data.get("assets", [])
    body = release_data.get("body", "")

    if not assets:
        await bot.log_text(f"No assets found in the release.\nMessage: {msg.link}", type="info")
        return

    to_dl_files = []
    dl_path = os.path.join("downloads", str(time.time()))
    os.makedirs(dl_path, exist_ok=True)

    for asset in assets:
        if asset["name"].lower().endswith(".apk"):
            apk_link, name = asset["browser_download_url"], asset["name"]
            if apk_link:
                try:
                    dl_obj = await Download.setup(
                        url=apk_link, path=dl_path, custom_file_name=name
                    )
                    to_dl_files.append(dl_obj.download())
                except Exception as e:
                    await bot.log_text(f"Failed to download APK file '{name}'. Error: {str(e)}", type="error")

    downloaded_files = await asyncio.gather(*to_dl_files)

    if not downloaded_files or not any(file for file in downloaded_files if file):
        await bot.log_text(f"No APK files were downloaded successfully.\nMessage: {msg.link}", type="info")
        shutil.rmtree(dl_path, ignore_errors=True)
        return

    grouped_apks = [
        InputMediaDocument(media=apk.full_path)
        for apk in downloaded_files if apk and os.path.isfile(apk.full_path)
    ]

    if not grouped_apks:
        await bot.log_text(f"No valid APK files found for this release.\nMessage: {msg.link}", type="info")
        shutil.rmtree(dl_path, ignore_errors=True)
        return

    body = body.split('**Full Changelog**: https://github.com/')[0].rstrip()
    if len(body) > 1024:  # 1024 is the maximum caption length in Telegram
        body = f"{body[:1024]}..."
    
    body += f"\n\n**[Full Changelog](https://github.com/{user}/{repo}/releases/latest)**"

    grouped_apks[-1].caption = (
        f"📣 New release for **{repo}**\n"
        f"Version: `{tag_name}`\n\n"
        f"{body}\n\n"
        f"{APK_CHANNEL_ID[msg.chat.id]['info']}"
    )

    try:
        await bot.send_media_group(chat_id=APK_CHANNEL_ID[msg.chat.id]["id"], media=grouped_apks)
    except Exception as e:
        await bot.log_text(f"Failed to send media group. Error: {str(e)}", type="error")
    
    shutil.rmtree(dl_path, ignore_errors=True)

async def process_apk_download(apk_link, msg: Message):
    dl_path = os.path.join("downloads", str(time.time()))
    os.makedirs(dl_path, exist_ok=True)
    
    name = apk_link.split('/')[-1]
    try:
        dl_obj = await Download.setup(
            url=apk_link, path=dl_path, custom_file_name=name
        )
        downloaded_file = await dl_obj.download()
    except Exception as e:
        await bot.log_text(f"Failed to download APK file '{name}'. Error: {str(e)}", type="error")
        shutil.rmtree(dl_path, ignore_errors=True)
        return

    if not downloaded_file or not os.path.isfile(downloaded_file.full_path):
        await bot.log_text(f"No valid APK file found for the download.\nMessage: {msg.link}", type="info")
        shutil.rmtree(dl_path, ignore_errors=True)
        return

    grouped_apks = [InputMediaDocument(media=downloaded_file.full_path)]

    grouped_apks[0].caption = (
        f"📣 New APK file available\n"
        f"Name: `{name}`\n\n"
        f"{APK_CHANNEL_ID[msg.chat.id]['info']}"
    )

    try:
        await bot.send_media_group(chat_id=APK_CHANNEL_ID[msg.chat.id]["id"], media=grouped_apks)
    except Exception as e:
        await bot.log_text(f"Failed to send media group. Error: {str(e)}", type="error")
    
    shutil.rmtree(dl_path, ignore_errors=True)
    
