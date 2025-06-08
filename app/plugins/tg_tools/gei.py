import asyncio
import os
import re
import shutil
import time
import requests
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Optional, Tuple
import xml.etree.ElementTree as ET

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

def extract_github_urls(text: str) -> List[str]:
    urls = []
    
    github_patterns = [
        r'https?://github\.com/[^/\s]+/[^/\s]+(?:/[^\s]*)?',
        r'https?://www\.github\.com/[^/\s]+/[^/\s]+(?:/[^\s]*)?',
    ]
    
    telegram_patterns = [
        r'\[([^\]]*)\]\((https?://github\.com/[^)]+)\)',
        r'<a[^>]*href=["\']?(https?://github\.com/[^"\'>\s]+)["\']?[^>]*>.*?</a>',
        r'https://t\.me/[^/]+/\d+\?url=(https?://github\.com/[^&\s]+)',
    ]
    
    for pattern in github_patterns:
        urls.extend(re.findall(pattern, text, re.IGNORECASE))
    
    for pattern in telegram_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                urls.append(match[1] if len(match) > 1 else match[0])
            else:
                urls.append(match)
    
    cleaned_urls = []
    for url in urls:
        if 'github.com' in url:
            cleaned_url = url.split('?')[0].split('#')[0]
            if cleaned_url not in cleaned_urls:
                cleaned_urls.append(cleaned_url)
    
    return cleaned_urls

def extract_fdroid_urls(text: str) -> List[str]:
    fdroid_patterns = [
        r'https?://f-droid\.org/[^\s]+',
        r'https?://fdroid\.org/[^\s]+',
        r'\[([^\]]*)\]\((https?://f-droid\.org/[^)]+)\)',
        r'<a[^>]*href=["\']?(https?://f-droid\.org/[^"\'>\s]+)["\']?[^>]*>.*?</a>',
    ]
    
    urls = []
    for pattern in fdroid_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                urls.append(match[1] if len(match) > 1 else match[0])
            else:
                urls.append(match)
    
    return list(set(urls))

def parse_github_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    match = re.search(r'github\.com/([^/]+)/([^/?#]+)', url)
    return match.groups() if match else (None, None)

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

async def get_latest_release_data(user: str, repo: str) -> Optional[Dict]:
    endpoints = [
        f"https://api.github.com/repos/{user}/{repo}/releases/latest",
        f"https://api.github.com/repos/{user}/{repo}/releases"
    ]
    
    for endpoint in endpoints:
        try:
            data = await aio.get_json(endpoint)
            if isinstance(data, list) and data:
                return data[0]
            elif data and not isinstance(data, list):
                return data
        except Exception as e:
            print(f"Error fetching {endpoint}: {e}")
            await asyncio.sleep(1)
    
    return None

async def get_github_actions_artifacts(user: str, repo: str) -> List[Dict]:
    try:
        artifacts_url = f"https://api.github.com/repos/{user}/{repo}/actions/artifacts"
        data = await aio.get_json(artifacts_url)
        
        artifacts = data.get("artifacts", [])
        apk_artifacts = []
        
        for artifact in artifacts:
            if ("apk" in artifact.get("name", "").lower() or 
                "release" in artifact.get("name", "").lower()):
                apk_artifacts.append({
                    "name": artifact.get("name"),
                    "download_url": artifact.get("archive_download_url"),
                    "created_at": artifact.get("created_at"),
                    "expired": artifact.get("expired", False)
                })
        
        apk_artifacts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return apk_artifacts[:5]
        
    except Exception as e:
        print(f"Error fetching GitHub Actions artifacts: {e}")
        return []

async def search_fdroid_apk(package_name: str) -> Optional[Dict]:
    try:
        fdroid_repo_url = "https://f-droid.org/repo/index-v1.json"
        repo_data = await aio.get_json(fdroid_repo_url)
        
        apps = repo_data.get("apps", {})
        packages = repo_data.get("packages", {})
        
        if package_name in apps:
            app_info = apps[package_name]
            if package_name in packages:
                versions = packages[package_name]
                if versions:
                    latest_version = max(versions, key=lambda x: x.get("versionCode", 0))
                    return {
                        "name": app_info.get("name", package_name),
                        "version": latest_version.get("versionName", ""),
                        "apk_name": latest_version.get("apkName", ""),
                        "download_url": f"https://f-droid.org/repo/{latest_version.get('apkName', '')}"
                    }
    except Exception as e:
        print(f"Error searching F-Droid: {e}")
    
    return None

async def search_apk_in_repo(user: str, repo: str) -> List[Dict]:
    search_endpoints = [
        f"https://api.github.com/search/code?q=extension:apk+repo:{user}/{repo}",
        f"https://api.github.com/repos/{user}/{repo}/contents",
        f"https://api.github.com/repos/{user}/{repo}/git/trees/main?recursive=1",
        f"https://api.github.com/repos/{user}/{repo}/git/trees/master?recursive=1"
    ]
    
    apk_files = []
    
    for endpoint in search_endpoints:
        try:
            data = await aio.get_json(endpoint)
            
            if "search/code" in endpoint:
                items = data.get("items", [])
                for item in items:
                    if item.get("name", "").lower().endswith(".apk"):
                        apk_files.append({
                            "name": item.get("name"),
                            "download_url": item.get("html_url").replace("/blob/", "/raw/")
                        })
            
            elif "contents" in endpoint:
                if isinstance(data, list):
                    for item in data:
                        if item.get("name", "").lower().endswith(".apk"):
                            apk_files.append({
                                "name": item.get("name"),
                                "download_url": item.get("download_url")
                            })
            
            elif "git/trees" in endpoint:
                tree = data.get("tree", [])
                for item in tree:
                    if item.get("path", "").lower().endswith(".apk"):
                        apk_files.append({
                            "name": os.path.basename(item.get("path")),
                            "download_url": f"https://github.com/{user}/{repo}/raw/main/{item.get('path')}"
                        })
                        
        except Exception as e:
            print(f"Error searching {endpoint}: {e}")
            continue
    
    return apk_files

async def download_apk_files(apk_list: List[Dict], dl_path: str) -> List:
    to_dl_files = []
    
    for apk_info in apk_list:
        name = apk_info.get("name")
        url = apk_info.get("download_url")
        
        if url and name:
            try:
                dl_obj = await Download.setup(url=url, dir=dl_path, custom_file_name=name)
                to_dl_files.append(dl_obj.download())
            except Exception as e:
                print(f"Error setting up download for {name}: {e}")
    
    if to_dl_files:
        return await asyncio.gather(*to_dl_files, return_exceptions=True)
    return []

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
            await asyncio.sleep(300)  

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

async def process_enhanced_github_search(msg: Message):
    data = msg.text or msg.caption or ""
    
    if msg.photo or msg.document:
        if hasattr(msg, 'caption') and msg.caption:
            data = msg.caption
        elif hasattr(msg, 'text') and msg.text:
            data = msg.text
    
    github_urls = extract_github_urls(data)
    fdroid_urls = extract_fdroid_urls(data)
    
    if github_urls:
        await process_github_urls(msg, github_urls)
    
    if fdroid_urls:
        await process_fdroid_urls(msg, fdroid_urls)

async def process_github_urls(msg: Message, github_urls: List[str]):
    for github_url in github_urls:
        user, repo = parse_github_url(github_url)
        
        if not (user and repo):
            continue
        
        dl_path = os.path.join("downloads", str(time.time()))
        
        try:
            release_data = await get_latest_release_data(user, repo)
            apk_files_info = []
            
            if release_data and release_data.get("assets"):
                for asset in release_data.get("assets", []):
                    if asset["name"].lower().endswith(".apk"):
                        apk_files_info.append({
                            "name": asset["name"],
                            "download_url": asset["browser_download_url"]
                        })
            
            if not apk_files_info:
                github_artifacts = await get_github_actions_artifacts(user, repo)
                for artifact in github_artifacts:
                    if not artifact.get("expired", False):
                        apk_files_info.append(artifact)
            
            if not apk_files_info:
                apk_files_info = await search_apk_in_repo(user, repo)
            
            if not apk_files_info:
                await bot.log_text(f"No APK files found for {user}/{repo}.\nMessage: {msg.link}", type="info")
                continue
            
            downloaded_files = await download_apk_files(apk_files_info, dl_path)
            
            valid_files = [f for f in downloaded_files if f and not isinstance(f, Exception)]
            
            if not valid_files:
                await bot.log_text(f"Failed to download APK files for {user}/{repo}.\nMessage: {msg.link}", type="error")
                continue
            
            grouped_apks = [InputMediaDocument(media=apk.path) for apk in valid_files]
            
            if not grouped_apks:
                continue
            
            tag_name = release_data.get("name", "") if release_data else "Latest"
            body = release_data.get("body", "") if release_data else f"Latest APK from {user}/{repo}"
            
            detected_lang = detect_language(body)
            if detected_lang != 'en':
                translated_body = translate_text(body, target_language='en', source_language=detected_lang)
                body = translated_body
            
            body = body.split('**Full Changelog**: https://github.com/')[0].rstrip()
            
            if len(body) > 2**9:
                body = f"{body[:2**9]}..."
            
            body += f"\n\n**[Repository](https://github.com/{user}/{repo})**"
            
            grouped_apks[-1].caption = (
                f"📣 New release for **{repo}**\n"
                f"Version: `{tag_name}`\n\n"
                f"{body}\n\n"
                f"{APK_CHANNEL_ID[msg.chat.id]['info']}"
            )
            
            await bot.send_media_group(chat_id=APK_CHANNEL_ID[msg.chat.id]["id"], media=grouped_apks)
            
        except Exception as e:
            await bot.log_text(f"Error processing {user}/{repo}: {e}", type="error")
        finally:
            if os.path.exists(dl_path):
                shutil.rmtree(dl_path, ignore_errors=True)

async def process_fdroid_urls(msg: Message, fdroid_urls: List[str]):
    for fdroid_url in fdroid_urls:
        try:
            package_match = re.search(r'/packages/([^/]+)', fdroid_url)
            if package_match:
                package_name = package_match.group(1)
                fdroid_data = await search_fdroid_apk(package_name)
                
                if fdroid_data:
                    dl_path = os.path.join("downloads", str(time.time()))
                    
                    try:
                        dl_obj = await Download.setup(
                            url=fdroid_data["download_url"], 
                            dir=dl_path, 
                            custom_file_name=fdroid_data["apk_name"]
                        )
                        downloaded_file = await dl_obj.download()
                        
                        if downloaded_file:
                            grouped_apks = [InputMediaDocument(media=downloaded_file.path)]
                            grouped_apks[0].caption = (
                                f"📣 F-Droid APK: **{fdroid_data['name']}**\n"
                                f"Version: `{fdroid_data['version']}`\n\n"
                                f"Downloaded from F-Droid repository\n\n"
                                f"{APK_CHANNEL_ID[msg.chat.id]['info']}"
                            )
                            
                            await bot.send_media_group(chat_id=APK_CHANNEL_ID[msg.chat.id]["id"], media=grouped_apks)
                    finally:
                        if os.path.exists(dl_path):
                            shutil.rmtree(dl_path, ignore_errors=True)
                            
        except Exception as e:
            await bot.log_text(f"Error processing F-Droid URL {fdroid_url}: {e}", type="error")

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