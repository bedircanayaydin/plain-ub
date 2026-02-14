import asyncio
from datetime import datetime
from typing import Optional

import aiohttp
from pyrogram.errors import FloodWait, MessageIdInvalid

from app import bot, BOT, Message, CustomDB, Config

CHANNEL_ID = -1003826251505
CHECK_INTERVAL = 300
REPO_JSON_URL = "https://raw.githubusercontent.com/Magisk-Modules-Alt-Repo/json/refs/heads/main/modules.json"

MAGISK_COLLECTION = CustomDB["MAGISK_MODULES"]
is_running = False


async def fetch_repo_data() -> Optional[dict]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(REPO_JSON_URL) as response:
                if response.status == 200:
                    return await response.json()
                return None
    except Exception as e:
        print(f"Error fetching repo data: {e}")
        return None


async def fetch_github_release(repo_url: str) -> Optional[dict]:
    try:
        if "github.com" in repo_url:
            parts = repo_url.split("github.com/")[1].split("/")
            owner = parts[0]
            repo = parts[1]
            
            async with aiohttp.ClientSession() as session:
                api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
                async with session.get(api_url) as response:
                    if response.status == 200:
                        return await response.json()
        return None
    except:
        return None


def truncate_text(text: str, max_length: int = 3500) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


async def send_with_flood_protection(chat_id: int, text: str):
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=False
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=False
        )
    except Exception as e:
        print(f"Send error: {e}")


async def get_module_version(module_id: str) -> Optional[str]:
    data = await MAGISK_COLLECTION.find_one({"_id": module_id})
    if data:
        return data.get("version")
    return None


async def save_module_version(module_id: str, version: str):
    await MAGISK_COLLECTION.update_one(
        {"_id": module_id},
        {"$set": {"version": version, "updated_at": datetime.utcnow()}},
        upsert=True
    )


async def check_and_notify_updates():
    data = await fetch_repo_data()
    if not data:
        return
    
    modules = data.get("modules", [])
    
    for module in modules:
        module_id = module.get("id")
        module_name = module.get("name")
        version = module.get("version")
        version_code = module.get("versionCode")
        download_url = module.get("zipUrl")
        changelog = module.get("changelog", "")
        author = module.get("author", "Unknown")
        description = module.get("description", "")
        repo_url = module.get("repository", "")
        
        if not module_id or not version:
            continue
        
        last_version = await get_module_version(module_id)
        
        if last_version is None:
            await save_module_version(module_id, version)
            continue
        
        if last_version != version:
            github_changelog = ""
            if repo_url:
                release_data = await fetch_github_release(repo_url)
                if release_data and release_data.get("body"):
                    github_changelog = release_data.get("body", "")
            
            final_changelog = github_changelog if github_changelog else changelog
            final_changelog = truncate_text(final_changelog, 2000)
            
            message_text = f"""🔄 **New Magisk Module Update**

📦 **Module:** `{module_name}`
👤 **Developer:** {author}
🔖 **Version:** `{version}` (Code: `{version_code}`)
"""

            if description:
                message_text += f"\n📝 **Description:**\n{truncate_text(description, 500)}\n"
            
            if final_changelog:
                message_text += f"\n📋 **Changelog:**\n{final_changelog}\n"
            
            message_text += f"""
⬇️ **Download:** [Click Here]({download_url})

🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
            
            message_text = truncate_text(message_text, 4000)
            
            await send_with_flood_protection(CHANNEL_ID, message_text)
            await save_module_version(module_id, version)
            print(f"✅ Update notification sent for {module_name}")
            
            await asyncio.sleep(2)


async def update_checker_loop():
    global is_running
    is_running = True
    await asyncio.sleep(10)
    
    while is_running:
        try:
            await check_and_notify_updates()
        except Exception as e:
            print(f"Update check error: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)


async def start_on_boot():
    await asyncio.sleep(5)
    task = asyncio.create_task(update_checker_loop(), name="MagiskModuleChecker")
    Config.BACKGROUND_TASKS.append(task)
    print("✅ Magisk module checker started automatically")


@bot.add_cmd(cmd="magiskcheck")
async def manual_check(bot: BOT, message: Message):
    try:
        await message.edit("🔍 Checking updates...")
        await check_and_notify_updates()
        await message.edit("✅ Check completed")
    except MessageIdInvalid:
        try:
            await message.reply("✅ Check completed")
        except:
            pass
    except Exception as e:
        print(f"Error in magiskcheck: {e}")


@bot.add_cmd(cmd="magiskstatus")
async def show_status(bot: BOT, message: Message):
    try:
        status_text = f"📊 **Magisk Checker Status**\n\n"
        status_text += f"🔄 Running: {'Yes' if is_running else 'No'}\n"
        status_text += f"⏱️ Check interval: {CHECK_INTERVAL} seconds\n\n"
        status_text += "**Tracked Modules:**\n"
        
        count = 0
        async for data in MAGISK_COLLECTION.find():
            module_id = data.get("_id")
            version = data.get("version")
            status_text += f"• `{module_id}`: v{version}\n"
            count += 1
        
        if count == 0:
            status_text += "No modules tracked yet"
        
        status_text = truncate_text(status_text, 4000)
        await message.edit(status_text)
    except MessageIdInvalid:
        try:
            await message.reply(status_text)
        except:
            pass
    except Exception as e:
        print(f"Error in magiskstatus: {e}")


@bot.add_cmd(cmd="magiskclear")
async def clear_database(bot: BOT, message: Message):
    try:
        await message.edit("🗑️ Clearing database...")
        result = await MAGISK_COLLECTION.delete_many({})
        await message.edit(f"✅ Cleared {result.deleted_count} modules from database")
    except MessageIdInvalid:
        try:
            await message.reply("✅ Database cleared")
        except:
            pass
    except Exception as e:
        print(f"Error in magiskclear: {e}")


task = asyncio.create_task(start_on_boot(), name="MagiskModuleCheckerInit")
Config.BACKGROUND_TASKS.append(task)
