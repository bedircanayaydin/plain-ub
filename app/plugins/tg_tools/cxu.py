# Uploads Xposed module info to telegram channel
#
# Author: Ryuk <@anonymousx97>
#
# Created: 2026-03-10
#
# Updated: 2026-07-26

import os
import asyncio
from datetime import datetime, timedelta

import bs4
from ub_core import BOT, LOGGER, CustomDB, Message, bot
from ub_core.utils import aio

POST_DB = CustomDB["COMMON_SETTINGS"]

POST_CHANNEL = -1002651613037

XPOSED_URL = "https://backup.modules.lsposed.org/modules.json"


@BOT.register_worker(interval=10800, name="xposed-updates")
@BOT.add_cmd(cmd="cxu")
async def check_xposed_updates(bot: BOT = bot, message: Message = None):
    """
    CMD: CXU
    INFO: Fetches information about the latest Xposed module from LSPosed modules repository.
    FLAGS:
         -f: force whatever the latest module is.
    USAGE: .cxu
    """
    modules_data = await aio.get_json(XPOSED_URL)

    if not modules_data:
        LOGGER.error("Failed to fetch Xposed module data or data is empty.")
        return

    # sort in reverse based on update time
    modules_data.sort(
        key=lambda m: m.get("updatedAt", "1970-01-01T00:00:00Z"), reverse=True
    )

    if message is not None and "-f" in message.flags:
        await upload_info(modules_data[0])
        return

    # reduce the new posts to 150
    del modules_data[150:]

    last_post = await POST_DB.find_one({"_id": "last_updated_post"}) or {}
    old_updated_at: datetime = last_post.get("post_updated_at")

    any_new_post = False

    for i in modules_data:
        post_iso = i.get("updatedAt")

        if post_iso is None or old_updated_at is None:
            continue

        updated_at: datetime = datetime.fromisoformat(post_iso)

        # break when the update date is older than the one in db
        if updated_at <= old_updated_at:
            break

        any_new_post = True
        await upload_info(i)
        await asyncio.sleep(5)

    if not any_new_post:
        if message:
            await message.reply("`No new update found...`")
        else:
            bot.log.info("cxu: no new posts.")

async def upload_info(module: dict):
    text_parts = []

    name = module.get("description", "N/A")
    text_parts.append(f"<b>📦 Module</b>: {name}\n")

    description = module.get("summary", "No description available.")
    text_parts.append(f"<b>✍️ Description</b>: {description}\n")

    version = module.get("latestRelease", "N/A")
    release = module.get("releases", [{}])[0]

    changelog_html = release.get("descriptionHTML")
    if changelog_html:
        soup = bs4.BeautifulSoup(changelog_html, "html.parser")
        text_parts.append(f"<b>📜 Changelog</b>: <code>{version}</code>")
        text_parts.append(
            f"<blockquote expandable=true>{soup.text[0:3000]}</blockquote>\n"
        )

    text_parts.append(f"<b>🏷️ Version</b>: <code>{version}</code>")

    if release.get("isPrerelease"):
        text_parts.append("<b>🚧 Pre-Release</b>: <code>yes</code>")

    if release.get("isDraft"):
        text_parts.append("<b>✍🏻 Draft</b>: <code>yes</code>\n")

    source_url = module.get("sourceUrl")
    release_url = release.get("url") or os.path.join(source_url, "releases")
    text_parts.append(
        f'📥  <a href="{release_url}">Download</a>  |  💻  <a href="{source_url}">Source</a>\n'
    )

    text_parts.append(
        "Join us:\n@XposedRepositoryChat\n@Xposed_Repository\n@Xposed_APK_repository"
    )
    text_parts.append(
        "<blockquote>🔖Don't forget to read the <a href='https://t.me/Xposed_Repository/8'>Reduction of responsibility</a></blockquote>"
    )

    schedule_date = datetime.utcnow() + timedelta(seconds=10)

    await bot.send_message(
        chat_id=POST_CHANNEL,
        text="\n".join(text_parts),
        disable_preview=True,
        schedule_date=schedule_date,
    )

    data = dict(
        package_name=module.get("name"),
        last_release=module.get("latestRelease"),
        post_updated_at=datetime.fromisoformat(module.get("updatedAt")),
        _id="last_updated_post",
    )
    await POST_DB.add_data(data)
