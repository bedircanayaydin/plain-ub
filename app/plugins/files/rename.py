import asyncio
import shutil

from ub_core.utils.downloader import Download, DownloadedFile

from app import BOT, Config, Message, bot
from app.plugins.files.download import telegram_download
from app.plugins.files.upload import upload_to_tg


@bot.add_cmd(cmd="rename")
async def rename(bot: BOT, message: Message):
    """
    CMD: RENAME
    INFO: Upload Files with custom name
    FLAGS: -s for spoiler
    USAGE:
        .rename [ url | reply to message ] file_name.ext
    """
    input = message.filtered_input

    response = await message.reply("Checking input...")

    if not message.replied or not message.replied.media or not message.filtered_input:
        await response.edit(
            "Invalid input...\nReply to a message containing media or give a link and a filename with cmd."
        )
        return

    download_path = Config.TEMP_DOWNLOAD_PATH()
    download_path.mkdir()

    await response.edit("Input verified....Starting Download...")

    if message.replied:
        dl_obj: None = None
        download_coro = telegram_download(
            message=message.replied, dir_name=download_path, file_name=input, response=response
        )

    else:
        url, file_name = input.split(maxsplit=1)
        dl_obj: Download = await Download.setup(
            url=url, dir=download_path, message_to_edit=response, custom_file_name=file_name
        )
        download_coro = dl_obj.download()

    try:
        downloaded_file: DownloadedFile = await download_coro
        await upload_to_tg(file=downloaded_file, message=message, response=response)
        shutil.rmtree(download_path, ignore_errors=True)

    except asyncio.exceptions.CancelledError:
        await response.edit("Cancelled....")

    except TimeoutError:
        await response.edit("Download Timeout...")

    except Exception as e:
        await response.edit(str(e))

    finally:
        if dl_obj:
            await dl_obj.close()
