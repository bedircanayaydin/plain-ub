# Xposed Feed Plugin by Ryuk.

import asyncio
from datetime import datetime, timedelta

import bs4
from ub_core import Config, CustomDB, bot
from ub_core.utils import aio

POST_DB = CustomDB["XPOSED_UPDATDES"]

POST_CHANNEL = "-1002651613037"

XPOSED_URL = "https://modules.lsposed.org/"


async def init_task():
    Config.BACKGROUND_TASKS.append(
        asyncio.create_task(exposed_worker(), name="xposed_updates")
    )


@bot.add_cmd("cxu")
async def get_exposed_updates(_=None, message=None):
    website_html = await aio.get_text(XPOSED_URL)
    website_soup = bs4.BeautifulSoup(website_html, "html.parser")

    first_post = website_soup.find(
        "div",
        class_="MuiPaper-root MuiCard-root jss816 MuiPaper-elevation1 MuiPaper-rounded",
    )

    head, body = first_post.children

    post_title = head.h2.text
    post_description = head.p.text

    _, source_info = body.children
    source_url = source_info.get("href")

    post_html = await aio.get_text(XPOSED_URL + head.get("href"))
    post_soup = bs4.BeautifulSoup(post_html, "html.parser")
    post_data = post_soup.find(
        "div", class_="MuiGrid-root MuiGrid-item MuiGrid-grid-xs-12 MuiGrid-grid-md-3"
    )

    for child in list(post_data.children)[0]:
        if child.h2.text == "Releases":
            url = child.h3.a.get("href")
            version = child.h3.text
            break

    text = (
        f"<b>📦 Module</b>: {post_title} \n\n"
        f"<b>✍️ Description</b>: {post_description} \n\n"
        f"🔗 <code>{version}</code>:\n"
        f'<a href="{url}">Download</a> | <a href="{source_url}">Source</a>\n\n'
        f"<b>🗨️ Support Chat</b>: @XposedRepositoryChat"
    )

    is_new_post = await check_and_insert_to_db(text)
    if not is_new_post:
        if message:
            await message.reply("No new update found.")
        return

    schedule_date = datetime.utcnow() + timedelta(seconds=10)

    await bot.send_message(
        chat_id=-1001552586568, text=text, disable_preview=True, schedule_date=schedule_date
    )


async def check_and_insert_to_db(text):
    old_post = await POST_DB.find_one({"_id": "last_updated_post"}) or {}
    if old_post.get("post_text") == text:
        return

    data_to_insert = dict(_id="last_updated_post", post_text=text)
    await POST_DB.add_data(data_to_insert)
    return 1


async def exposed_worker():
    while True:
        try:
            await get_exposed_updates()
        except asyncio.exceptions.CancelledError:
            return
        except Exception as e:
            bot.log.error(e, exc_info=True)
        await asyncio.sleep(10800)
