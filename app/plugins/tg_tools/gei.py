import asyncio
import os
import re
import shutil
import time
import requests

from pyrogram import filters
from pyrogram.types import InputMediaDocument
from ub_core.utils import Download, aio
from app import Message, bot

CHANNEL_ID = [-1002651613037, -1001674072540]
APK_CHANNEL_ID = {
    -1002651613037: {
        "id": -1002435387627,
        "info": (
            "👥 Join\n📣 @XposedRepository \n"
            "💬 @XposedRepositoryChat \n"
            "@Xposedapkrepo"
        ),
    },
    -1001674072540: {
        "id": -1001724179522,
        "info": (
            "👥 Join\n📣 @FossDroidAndroid \n"
            "💬 @FossDroid_AndroidChat \n"
            "@FossDroid_Android_apkrepo"
        ),
    },
}

def detect_language(text):
    url = "https://api.mymemory.translated.net/get"
    params = {'q': text, 'langpair': 'auto|en'}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        response_json = response.json()
        detected_lang = response_json.get('responseData', {}).get('detectedSourceLanguage', 'en')
        return detected_lang
    except requests.RequestException as e:
        print(f"Request error: {e}")
    except ValueError as e:
        print(f"JSON decode error: {e}")
    return 'en'

def translate_text(text, target_language='en', source_language='auto'):
    url = "https://api.mymemory.translated.net/get"
    params = {'q': text, 'langpair': f'{source_language}|{target_language}'}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        response_json = response.json()
        translated_text = response_json.get('responseData', {}).get('translatedText', text)
        return translated_text
    except requests.RequestException as e:
        print(f"Request error: {e}")
    except ValueError as e:
        print(f"JSON decode error: {e}")
    return text

async def retry_upload_github_apk(msg: Message, retry_count=5, delay=300):
    for attempt in range(retry_count):
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
            await bot.log_text(f"No GitHub URL found in the message.\nMessage: {msg.link}", type="info")
            await search_github_for_apk(msg)
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
        try:
            release_data = await aio.get_json(url)
            if release_data and release_data.get("assets"):
                break
        except requests.RequestException as e:
            print(f"Request error for {url}: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying if rate limit is hit

    if not release_data:
        await bot.log_text(f"No release data found.\nMessage: {msg.link}", type="info")
        await search_github_for_apk(msg)
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
                dl_obj = await Download.setup(url=apk_link, dir=dl_path, custom_file_name=name)
                to_dl_files.append(dl_obj.download())

    downloaded_files = await asyncio.gather(*to_dl_files)

    if not downloaded_files:
        await bot.log_text(f"No APK files found for this release.\nMessage: {msg.link}", type="info")
        await search_github_for_apk(msg)
        return

    grouped_apks = [
        InputMediaDocument(media=apk.path)
        for apk in downloaded_files
    ]

    if not grouped_apks:
        await bot.log_text(f"No APK files found for this release.\nMessage: {msg.link}", type="info")
        return

    detected_lang = detect_language(body)
    if detected_lang != 'en':
        translated_body = translate_text(body, target_language='en', source_language=detected_lang)
        body = translated_body

    body = body.split('**Full Changelog**: https://github.com/')[0].rstrip()

    if len(body) > 2**9:
        body = f"{body[:2**9]}..."
        
    body += f"\n\n**[Full Changelog](https://github.com/{user}/{repo}/releases/latest)**"

    grouped_apks[-1].caption = (
        f"📣 New release for **{repo}**\n"
        f"Version: `{tag_name}`\n\n"
        f"{body}\n\n"
        f"{APK_CHANNEL_ID[msg.chat.id]['info']}"
    )

    await bot.send_media_group(chat_id=APK_CHANNEL_ID[msg.chat.id]["id"], media=grouped_apks)

    shutil.rmtree(dl_path, ignore_errors=True)

async def search_github_for_apk(msg: Message):
    search_query = "APK file"
    search_url = f"https://api.github.com/search/code?q={search_query}+in:file+extension:apk"
    dl_path = os.path.join("downloads", str(time.time()))  
    
    try:
        response = requests.get(search_url)
        response.raise_for_status()
        search_results = response.json()
        
        for item in search_results.get('items', []):
            file_url = item.get('html_url')
            file_name = item.get('name')
            if file_url and file_name.lower().endswith(".apk"):
                await bot.log_text(f"Found APK: {file_name} - {file_url}", type="info")
                dl_obj = await Download.setup(url=apk_link, dir=dl_path, custom_file_name=name)
                downloaded_file = await dl_obj.download()
                
                if downloaded_file:
                    grouped_apks = [InputMediaDocument(media=downloaded_file.path)]
                    grouped_apks[0].caption = (
                        f"📣 New APK found: **{file_name}**\n"
                        f"Download: [Link]({file_url})\n\n"
                        f"{APK_CHANNEL_ID[msg.chat.id]['info']}"
                    )
                    await bot.send_media_group(chat_id=APK_CHANNEL_ID[msg.chat.id]["id"], media=grouped_apks)
                    
                return
                
    except requests.RequestException as e:
        print(f"Search request error: {e}")
    except ValueError as e:
        print(f"JSON decode error: {e}")

async def copy_and_validate_link(msg: Message):
    data = msg.text or msg.caption

    pattern = r"https?://github\.com/([^/]+)/([^/?#]+)"
    match = re.search(pattern, data.markdown)

    if match:
        copied_url = match.group(0)
        
        response = requests.get(copied_url)
        if response.status_code == 200:
            await upload_github_apk(msg)
        else:
            await bot.log_text(f"Invalid URL: {copied_url}\nMessage: {msg.link}", type="error")
    else:
        await bot.log_text(f"No valid GitHub URL found in the message.\nMessage: {msg.link}", type="info")
        
async def copy_and_validate_link(msg: Message):
    data = msg.text or msg.caption

    pattern = r"https?://github\.com/([^/]+)/([^/?#]+)"
    match = re.search(pattern, data.markdown)

    if match:
        copied_url = match.group(0)
        
        response = requests.get(copied_url)
        if response.status_code == 200:
            await upload_github_apk(msg)
        else:
            await bot.log_text(f"Invalid URL: {copied_url}\nMessage: {msg.link}", type="error")
    else:
        await bot.log_text(f"No valid GitHub URL found in the message.\nMessage: {msg.link}", type="info")
