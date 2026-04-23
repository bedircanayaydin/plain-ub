import pickle
import traceback

from google.genai.chats import AsyncChat
from pyrogram.enums import ChatType, ParseMode
from ub_core import BOT, Convo, Message, bot

from app.plugins.ai.gemini import (
    async_client,
    execute_and_send_function_call,
    export_history,
    get_model_config,
    loop_until_sent,
)
from app.plugins.ai.gemini.code import create_plugin
from app.plugins.ai.gemini.utils import create_prompts, run_basic_check


@bot.add_cmd(cmd="aic")
@run_basic_check
async def ai_chat(bot: BOT, message: Message):
    """
    CMD: AICHAT
    INFO: Have a Conversation with Gemini AI.
    FLAGS:
        -s: use search
        -i: use image gen/edit mode
        -a: audio output
        -sp: multi speaker output
    USAGE:
        .aic hello
        keep replying to AI responses with text | media [no need to reply in DM]
        After 5 minutes of Idle bot will export history and stop chat.
        use .load_history to continue

    """
    chat = async_client.chats.create(**get_model_config(message.flags))
    await do_convo(chat=chat, prompt_message=message)


@bot.add_cmd(cmd="lh")
@run_basic_check
async def history_chat(bot: BOT, message: Message):
    """
    CMD: LOAD_HISTORY
    INFO: Load a Conversation with Gemini AI from previous session.
    USAGE:
        .lh {question} [reply to history document]
    """
    reply = message.replied

    if not message.input:
        await message.reply(f"Ask a question along with {message.trigger}{message.cmd}")
        return
    expected_name = "AI_Chat_History.pkl"

    try:
        file_name = reply.document.file_name
        assert file_name == expected_name or file_name.endswith("chat_history.pkl")
    except (AssertionError, AttributeError):
        await message.reply("Reply to a Valid History file.")
        return

    resp = await message.reply("`Loading History...`")

    doc = await reply.download(in_memory=True)
    doc.seek(0)
    history = pickle.load(doc)

    await resp.edit("__History Loaded... Resuming chat__")

    if file_name == expected_name:
        chat = async_client.chats.create(**get_model_config(message.flags), history=history)
        await do_convo(chat=chat, prompt_message=message)
    else:
        await create_plugin(bot, message, history)


CHAT_CONVO_CACHE: dict[str, Convo] = {}


def pop_old_convo(message: Message):
    old_conversation = CHAT_CONVO_CACHE.get(message.unique_chat_user_id)
    if old_conversation in Convo.CONVO_DICT[message.chat.id]:
        Convo.CONVO_DICT[message.chat.id].remove(old_conversation)


async def do_convo(chat: AsyncChat, prompt_message: Message):
    pop_old_convo(prompt_message)

    if prompt_message.chat.type in (ChatType.PRIVATE, ChatType.BOT):
        reply_to_user_id = None
    else:
        reply_to_user_id = prompt_message._client.me.id

    async with Convo(
        client=prompt_message._client,
        chat_id=prompt_message.chat.id,
        timeout=300,
        check_for_duplicates=False,
        from_user=prompt_message.from_user.id,
        reply_to_user_id=reply_to_user_id,
    ) as conversation:
        CHAT_CONVO_CACHE[prompt_message.unique_chat_user_id] = conversation
        wait_for_response = False

        while True:
            try:
                if wait_for_response:
                    prompt_message = await conversation.get_response()

                prompt = await create_prompts(prompt_message, is_chat=wait_for_response, check_size=False)

                reply_to_id = prompt_message.id

                ai_response = await loop_until_sent(chat=chat, tg_convo=conversation, parts=prompt)

                if ai_response.function_call:
                    ai_response = await execute_and_send_function_call(
                        chat=chat, tg_convo=conversation, ai_response=ai_response
                    )

                if ai_response.text.strip():
                    await conversation.send_message(
                        text=f"**>•><**\n{ai_response.quoted_text()}",
                        reply_to_id=reply_to_id,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_preview=True,
                    )

                for image in ai_response.all_image_files:
                    await conversation.send_photo(photo=image, reply_to_id=reply_to_id)

                for audio in ai_response.all_audio_files:
                    await conversation.send_voice(
                        voice=audio, waveform=audio.waveform, reply_to_id=reply_to_id, duration=audio.duration
                    )

            except TimeoutError:
                CHAT_CONVO_CACHE.pop(prompt_message.unique_chat_user_id, 0)
                await export_history(chat, prompt_message)
                return

            except Exception:
                await conversation.send_message(text=f"```\n{traceback.format_exc()}```", reply_to_id=reply_to_id)

            wait_for_response = True
