# Xposed Feed Plugin by Ryuk.

import asyncio

import bs4
from ub_core import Config, bot
from ub_core.utils import aio

POST_CHANNEL = "XposedRepository"

XPOSED_URL = "https://modules.lsposed.org/"


async def init_task():
    Config.BACKGROUND_TASKS.append(
        asyncio.create_task(exposed_worker(), name="xposed_updates")
    )


@bot.add_cmd("cxu")
async def get_exposed_updates(_=None, __=None):
    website_html = await (await aio.session.get(XPOSED_URL)).text()
    website_soup = bs4.BeautifulSoup(website_html, "html.parser")

    first_post = website_soup.find(
        "div",
        class_="MuiPaper-root MuiCard-root jss1023 MuiPaper-elevation1 MuiPaper-rounded",
    )

    head, body = first_post.children

    post_title = head.h2.text
    post_description = head.p.text

    body_children = body.children
    _, source_info = body_children
    source_url = source_info.get("href")

    post_html = await (await aio.session.get(XPOSED_URL + head.get("href"))).text()
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
        f"<b>📦 Module</b>: <code>{post_title}</code> \n\n"
        f"<b>✍️ Description</b>: <code>{post_description}</code> \n\n"
        f"🔗 <code>{version}</code>:\n"
        f'<a href="{url}">Download</a> | <a href="{source_url}">Source</a>\n\n'
        f"<b>🗨️ Support Chat</b>: @XposedRepositoryChat"
    )

    async for msg in bot.get_chat_history(POST_CHANNEL, limit=1):
        msg_text = msg.text or msg.caption
        if getattr(msg_text, "html", "") == text:
            return

    await bot.send_message(chat_id=POST_CHANNEL, text=text, disable_web_page_preview=True)


async def exposed_worker():
    while True:
        try:
            await get_exposed_updates()
        except asyncio.exceptions.CancelledError:
            return
        except Exception as e:
            client.log.error(e, exc_info=True)
        await asyncio.sleep(10800)
