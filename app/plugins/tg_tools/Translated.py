import os
import urllib.request
import urllib.parse
import json
from pyrogram import Client, filters
import re

def translate_text(text, target_lang):
    url = "https://libretranslate.com/translate"
    params = {
        'q': text,
        'source': 'en', 
        'target': target_lang,
        'format': 'text'
    }
    query_string = urllib.parse.urlencode(params)
    data = query_string.encode('utf-8')
    
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            translated_text = result.get('translatedText')
            if not translated_text:
                raise ValueError("Translation API did not return 'translatedText'")
    except Exception as e:
        print(f"Error in translation: {e}")
        return text 
    
    return translated_text

source_channel = '@Xposedapkrepo'

async def translate_and_share(client, description, document):
    def process_translation(text, target_lang):
        markdown_links = re.findall(r'\[.*?\]\(.*?\)', text)
        for i, link in enumerate(markdown_links):
            text = text.replace(link, f"[[{i}]]")
        
        translated_text = translate_text(text, target_lang)
        
        for i, link in enumerate(markdown_links):
            translated_text = translated_text.replace(f"[[{i}]]", link)
        
        return translated_text
    
    target_languages = ['tr', 'es', 'pt', 'id']  
    translations = {lang: process_translation(description, lang) for lang in target_languages}
    
    target_channels = ['@MiuiSystemUpdatesTR', '@miuisystemupdates_es', '@miuisystemupdatesbr','@msu_Indonesia']  
    for channel in target_channels:
        for lang, translated_text in translations.items():
            try:
                await client.send_document(
                    chat_id=channel,
                    document=document.file_id,
                    caption=f"{translated_text}\n\nTranslated from English",
                    parse_mode="Markdown" 
                )
            except Exception as e:
                print(f"Failed to send document to {channel}: {e}")

 @bot.bot.on_message(
        filters.chat(chats=CHANNEL_ID) & filters.document)
async def auto_translate_and_share(client, message):
    if message.document and message.document.mime_type == "application/vnd.android.package-archive":
        description = message.caption if message.caption else "No description"
        await translate_and_share(client, description, message.document)

@bot.bot.on_message(filters.command("translate") & filters.private)
async def manual_translate_and_share(client, message):
    if message.reply_to_message and message.reply_to_message.document and message.reply_to_message.document.mime_type == "application/vnd.android.package-archive":
        description = message.reply_to_message.caption if message.reply_to_message.caption else "No description"
        await translate_and_share(client, description, message.reply_to_message.document)
