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

GITHUB_API_URL = "https://api.github.com"
GITLAB_API_URL = "https://gitlab.com/api/v4"
FDROID_URL = "https://f-droid.org"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"
CHAR_LIMIT = 1024

async def fetch_json(url):
    try:
        response = await aio.get(url)
        if response.status == 403 and RATE_LIMIT_RESET_HEADER in response.headers:
            reset_time = int(response.headers[RATE_LIMIT_RESET_HEADER])
            current_time = int(time.time())
            wait_time = reset_time - current_time
            if wait_time > 0:
                await asyncio.sleep(wait_time + 5)  # Biraz daha uzun bekle
            response = await aio.get(url)  # Bekledikten sonra yeniden dene
        return await response.json()
    except Exception as e:
        await bot.log_text(f"API'dan veri çekme hatası. Hata: {str(e)}", type="error")
        return None

async def fetch_text(url):
    try:
        response = await aio.get(url)
        return await response.text()
    except Exception as e:
        await bot.log_text(f"URL'den metin çekme hatası. Hata: {str(e)}", type="error")
        return None

async def process_github(msg: Message):
    data = msg.text or msg.caption
    if not data:
        await bot.log_text(f"Mesajda metin veya açıklama bulunamadı.\nMesaj: {msg.link}", type="info")
        return

    direct_apk_pattern = r"https?://github\.com/[^/]+/[^/]+/releases/download/[^/]+/[^/]+\.apk"
    direct_apk_match = re.search(direct_apk_pattern, data)
    if direct_apk_match:
        apk_link = direct_apk_match.group(0)
        await process_apk_download(apk_link, msg)
        return

    repo_pattern = r"https?://github\.com/([^/]+)/([^/?#]+)(?:/releases(?:/tag/([^/?#]+))?)?"
    repo_match = re.search(repo_pattern, data)
    if not repo_match:
        await bot.log_text(f"GitHub URL'si bulunamadı.\nMesaj: {msg.link}", type="info")
        return

    user, repo, tag = repo_match.group(1), repo_match.group(2), repo_match.group(3)
    url = f"{GITHUB_API_URL}/repos/{user}/{repo}/releases/tags/{tag}" if tag else f"{GITHUB_API_URL}/repos/{user}/{repo}/releases/latest"

    release_data = await fetch_json(url)
    if not release_data:
        await bot.log_text(f"Sürüm verisi bulunamadı.\nMesaj: {msg.link}", type="info")
        await process_alternative_sources(msg)
        return

    tag_name = release_data.get("name", "")
    assets = release_data.get("assets", [])
    body = release_data.get("body", "")

    apk_found = False
    if not assets:
        apk_link_pattern = r"https?://github\.com/[^/]+/[^/]+/releases/download/[^/]+/[^/]+\.apk"
        apk_link_match = re.search(apk_link_pattern, body)
        if apk_link_match:
            apk_link = apk_link_match.group(0)
            await process_apk_download(apk_link, msg)
            apk_found = True

        if not apk_found:
            tag_url = f"{GITHUB_API_URL}/repos/{user}/{repo}/tags"
            tags_data = await fetch_json(tag_url)
            
            if tags_data:
                for tag_info in tags_data:
                    tag_name = tag_info.get("name", "")
                    if "apk" in tag_name.lower():
                        tag_url = f"{GITHUB_API_URL}/repos/{user}/{repo}/releases/tags/{tag_name}"
                        release_data = await fetch_json(tag_url)
                        assets = release_data.get("assets", [])
                        if assets:
                            break

    if not assets:
        await process_alternative_sources(msg)
        return

    await download_and_upload_apks(assets, msg, user, repo, tag_name)

async def process_alternative_sources(msg: Message):
    data = msg.text or msg.caption
    if not data:
        await bot.log_text(f"Mesajda metin veya açıklama bulunamadı.\nMesaj: {msg.link}", type="info")
        return

    gitlab_pattern = r"https?://gitlab\.com/([^/]+)/([^/?#]+)(?:/releases(?:/tag/([^/?#]+))?)?"
    gitlab_match = re.search(gitlab_pattern, data)
    if gitlab_match:
        user, repo, tag = gitlab_match.group(1), gitlab_match.group(2), gitlab_match.group(3)
        url = f"{GITLAB_API_URL}/projects/{user}%2F{repo}/repository/tags"
        tags_data = await fetch_json(url)
        if tags_data:
            for tag_info in tags_data:
                tag_name = tag_info.get("name", "")
                if tag and tag_name == tag:
                    tag_url = f"{GITLAB_API_URL}/projects/{user}%2F{repo}/repository/tags/{tag_name}/repository_files"
                    release_data = await fetch_json(tag_url)
                    if release_data:
                        assets = release_data.get("assets", [])
                        if assets:
                            await download_and_upload_apks(assets, msg, user, repo, tag_name)
                            return

    fdroid_pattern = r"https?://f-droid\.org/en/packages/([^/]+/[^/?#]+)"
    fdroid_match = re.search(fdroid_pattern, data)
    if fdroid_match:
        package_name = fdroid_match.group(1)
        url = f"{FDROID_URL}/fdroid/repo/{package_name}.apk"
        await process_apk_download(url, msg)

async def download_and_upload_apks(assets, msg: Message, user: str, repo: str, tag_name: str):
    to_dl_files = []
    dl_path = os.path.join("downloads", str(time.time()))
    os.makedirs(dl_path, exist_ok=True)

    for asset in assets:
        if asset["name"].lower().endswith(".apk"):
            apk_link, name = asset["browser_download_url"], asset["name"]
            try:
                dl_obj = await Download.setup(url=apk_link, path=dl_path, custom_file_name=name)
                to_dl_files.append(dl_obj.download())
            except Exception as e:
                await bot.log_text(f"APK dosyası '{name}' indirme hatası. Hata: {str(e)}", type="error")

    downloaded_files = await asyncio.gather(*to_dl_files)

    if not downloaded_files or not any(file for file in downloaded_files if file):
        await bot.log_text(f"Başarıyla indirilen APK dosyası bulunamadı.\nMesaj: {msg.link}", type="info")
        shutil.rmtree(dl_path, ignore_errors=True)
        return

    grouped_apks = [InputMediaDocument(media=apk.full_path) for apk in downloaded_files if apk and os.path.isfile(apk.full_path)]

    if not grouped_apks:
        await bot.log_text(f"Geçerli APK dosyası bulunamadı.\nMesaj: {msg.link}", type="info")
        shutil.rmtree(dl_path, ignore_errors=True)
        return

    body = release_data.get("body", "")
    if len(body) > CHAR_LIMIT:
        body_excerpt = body[:CHAR_LIMIT]
        body = f"{body_excerpt}...\n\n**[Full Changelog](https://github.com/{user}/{repo}/releases/latest)**"
    else:
        body += f"\n\n**[Full Changelog](https://github.com/{user}/{repo}/releases/latest)**"

    grouped_apks[-1].caption = (
        f"📣 Yeni sürüm **{repo}** için\n"
        f"Sürüm: `{tag_name}`\n\n"
        f"{body}\n\n"
        f"{APK_CHANNEL_ID[msg.chat.id]['info']}"
    )

        try:
        await bot.send_media_group(
            chat_id=msg.chat.id,
            media=grouped_apks
        )
    except Exception as e:
        await bot.log_text(f"APK'ların gönderilmesi hatası. Hata: {str(e)}", type="error")

from pyrogram import Client, filters
from pyrogram.types import Message
import re
import asyncio
from your_module import upload_apk 

CHANNEL_ID = [-1001552586568, -1001674072540]
APK_CHANNEL_ID = {
    -1001552586568: -1001836098073,
    -1001674072540: -1001724179522,
}

@bot.on_message(filters.text)
async def handle_message(msg: Message):
    if msg.chat.id in CHANNEL_ID:
        
        urls = re.findall(r'https?://\S+', msg.text or "")
        
        for url in urls:
            await upload_apk(url, msg.chat.id)
            
