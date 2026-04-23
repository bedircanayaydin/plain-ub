import asyncio
import io
import pathlib
from collections.abc import Callable
from mimetypes import guess_type

from google.genai.types import CustomMetadata, FileSearchStore, ListDocumentsConfig, UploadToFileSearchStoreConfig
from ub_core.utils.helpers import create_chunks, run_unknown_callable

from app import BOT, Message
from app.plugins.ai.gemini import async_client


async def get_stores(client=async_client):
    async for store in await client.file_search_stores.list():
        yield store


async def list_files(
    store: FileSearchStore, config: ListDocumentsConfig = None, file_filter: Callable = None, client=async_client
):
    """
    store: Store to delete from
    file_filter: to check which file to delete
        example:
            def filter(file):
                return file.display_name == "abc"
                or
                return "/path/" in file.display_name
                or
                return file.modification_time == some date
    """
    async for file in await client.file_search_stores.documents.list(parent=store.name, config=config):
        if file_filter is not None:
            if not await run_unknown_callable(file_filter, file):
                continue
        yield file


async def delete_files(
    store: FileSearchStore, config: ListDocumentsConfig = None, file_filter: Callable = None, client=async_client
) -> int:
    """
    store: Store to delete from
    file_filter: to check which file to delete
        example:
            def filter(file):
                return file.display_name == "abc"
                or
                return "/path/" in file.display_name
                or
                return file.modification_time == some date
    """
    coroutines = [
        client.file_search_stores.documents.delete(name=file.name, config={"force": True})
        async for file in list_files(store, config, file_filter)
    ]
    for chunk in create_chunks(coroutines, chunk_size=15):
        await asyncio.gather(*chunk)
    return len(coroutines)


async def upload_file_to_store(
    store: FileSearchStore,
    file: str | pathlib.Path | io.BytesIO,
    file_name: str,
    custom_metadata: list[CustomMetadata] = None,
    client=async_client,
):
    config = UploadToFileSearchStoreConfig(
        display_name=file_name,
        mime_type=guess_type(file_name)[0],
        chunking_config={"white_space_config": {"max_tokens_per_chunk": 512, "max_overlap_tokens": 60}},
        custom_metadata=custom_metadata,
    )

    operation = await client.file_search_stores.upload_to_file_search_store(
        file_search_store_name=store.name, file=file, config=config
    )

    while not operation.done:
        operation = await client.operations.get(operation)
        await asyncio.sleep(5)

    return operation


@BOT.add_cmd("delete_store")
async def delete_store(bot: BOT, message: Message):
    stores = [s async for s in get_stores()]

    if not stores:
        await message.reply("`No stores in gemini cloud storage...`")
        return

    store_names = [s.name for s in stores]
    reply = await message.reply(
        f"Stores:"
        f"\n<blockquote expandable><pre>{'\n\n'.join(store_names)}</pre></blockquote>"
        f"\nReply or quote the name to delete."
    )
    selection, _ = await reply.get_response(
        timeout=60, reply_to_message_id=reply.id, from_user=message.from_user.id, quote=True
    )
    if selection not in store_names:
        await message.reply("Invalid selection!")
        return

    await async_client.file_search_stores.delete(name=selection, config={"force": True})
    await message.reply("Deleted!")
