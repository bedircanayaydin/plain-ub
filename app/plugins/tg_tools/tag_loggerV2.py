from pyrogram import Client, filters
import requests
import time

bot_token = "1866553713:AAFl3rKqrEWozw9reMet0HRM155r4Dci6hA"
app = Client("my_bot", bot_token=1866553713:AAFl3rKqrEWozw9reMet0HRM155r4Dci6hA)

XPOSED_JSON_URL = "https://modules.lsposed.org/modules.json"

@app.on_message(filters.command("check_updates"))
def check_xposed_updates(client, message):
    while True:
        response = requests.get(https://modules.lsposed.org/modules.json)
        updates = response.json()
        
        if 'updates' in updates:
            for update in updates['updates']:
                github_link = update.get('github_link', 'No GitHub link available')
                support_chat = "@XposedRepositoryChat"
                
                module_info = f"Module: {update['module_name']} 📦\n" \
                              f"Version: {update['version']} 🆕\n" \
                              f"Description: {update['description']} ✍️\n" \
                              f"Support: {support_chat} 💬\n" \
                              f"Details: {github_link} 🔗"
                
                message.reply_text(module_info)
        else:
            message.reply_text("No new updates found. 😕")
        
        time.sleep(10800)

app.run()
