import os
import io
import asyncio
import logging
from threading import Thread
from flask import Flask
from dotenv import load_dotenv
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, constants
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest
import PIL.Image

# ---------------------------------------------------------
# ១. CONFIGURATION & SETUP
# ---------------------------------------------------------
load_dotenv()

# Logger សម្រាប់មើលបញ្ហា
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Flask Server (សម្រាប់ Render Keep-Alive)
app = Flask('')
@app.route('/')
def home(): return "<h1>🤖 Sinan AI is Online & Healthy!</h1>"

def run_server(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run_server)
    t.start()

# API Setup
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not GOOGLE_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("⚠️ សូមពិនិត្យមើល API Key របស់អ្នក!")

genai.configure(api_key=GOOGLE_API_KEY)

# ប្រើ Model ថ្មី និងឆ្លាតបំផុត
MODEL_NAME = 'gemini-1.5-flash'

# System Prompt (អត្តចរិតរបស់ Bot)
SYSTEM_PROMPT = """
អ្នកគឺជា "Sinan AI" (ស៊ីណាន AI) ជំនួយការឆ្លាតវៃកម្រិតខ្ពស់។
- បេសកកម្ម៖ ជួយដោះស្រាយបញ្ហា សរសេរកូដ និងផ្តល់យោបល់ល្អៗ។
- ភាសា៖ ឆ្លើយតបជាភាសាខ្មែរ (Khmer) ដោយប្រើពាក្យគួរសម និងច្បាស់លាស់។
- រចនាប័ទ្ម៖ ប្រើ Emoji ខ្លះៗដើម្បីអោយអត្ថបទមានសោភ័ណភាព។
- បច្ចេកទេស៖ បើគេសួររឿងកូដ ត្រូវសរសេរកូដអោយច្បាស់ និងពន្យល់ខ្លីៗ។
"""

# ទុកប្រវត្តិ Chat (Memory)
user_chats = {}

# ---------------------------------------------------------
# ២. HELPER FUNCTIONS (មុខងារជំនួយ)
# ---------------------------------------------------------
def get_main_menu():
    """បង្កើតផ្ទាំង Menu ដ៏ស្រស់ស្អាត"""
    keyboard = [
        [InlineKeyboardButton("💬 ចាប់ផ្តើមសន្ទនា", callback_data='new_chat')],
        [InlineKeyboardButton("📝 ជួយសរសេរកូដ", callback_data='help_code'), InlineKeyboardButton("🎨 វិភាគរូបភាព", callback_data='help_vision')],
        [InlineKeyboardButton("🧹 លុប Memory (Reset)", callback_data='clear_memory')],
        [InlineKeyboardButton("👨‍💻 អំពីអ្នកបង្កើត", url="https://t.me/SreangSinan")] # ដាក់ Link Telegram បងនៅទីនេះ
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_smart_message(context, chat_id, text):
    """មុខងារកាត់អក្សរស្វ័យប្រវត្តិ ពេលអក្សរវែងពេក"""
    MAX_LEN = 4000
    try:
        if len(text) <= MAX_LEN:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=constants.ParseMode.MARKDOWN)
        else:
            # បើវែងពេក កាត់ជាកង់ៗ
            parts = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]
            for part in parts:
                await context.bot.send_message(chat_id=chat_id, text=part)
    except BadRequest:
        # បើ Markdown Error ផ្ញើអក្សរធម្មតាវិញ (Fallback)
        await context.bot.send_message(chat_id=chat_id, text=text)

# ---------------------------------------------------------
# ៣. AI LOGIC (ខួរក្បាល)
# ---------------------------------------------------------
def get_chat_session(chat_id):
    if chat_id not in user_chats:
        model = genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        user_chats[chat_id] = model.start_chat(history=[])
    return user_chats[chat_id]

async def process_ai(update, context, prompt, image=None):
    chat_id = update.effective_chat.id
    
    # បង្ហាញថា Bot កំពុងគិត...
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    try:
        response_text = ""
        if image:
            # វិភាគរូបភាព
            model = genai.GenerativeModel(MODEL_NAME)
            response = model.generate_content([prompt, image])
            response_text = response.text
        else:
            # សន្ទនាធម្មតា
            chat = get_chat_session(chat_id)
            response = chat.send_message(prompt)
            response_text = response.text
        
        await send_smart_message(context, chat_id, response_text)

    except Exception as e:
        error_msg = f"⚠️ **អភ័យទោស!** មានបញ្ហាបន្តិចបន្តួច៖\n`{str(e)}`\nសូមសាកល្បងម្តងទៀត។"
        await context.bot.send_message(chat_id=chat_id, text=error_msg, parse_mode=constants.ParseMode.MARKDOWN)

# ---------------------------------------------------------
# ៤. COMMAND & HANDLERS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"🌟 **សួស្តីបង {user.first_name}!** 🌟\n\n"
        f"ស្វាគមន៍មកកាន់ **Sinan AI Premium**។\n"
        f"ខ្ញុំអាចជួយបងបានគ្រប់រឿង តាំងពីការសរសេរកូដ រហូតដល់ការពិគ្រោះយោបល់។\n\n"
        f"👇 **សូមជ្រើសរើសមុខងារខាងក្រោម:**"
    )
    await update.message.reply_text(welcome_text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_main_menu())

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    if data == 'clear_memory':
        if chat_id in user_chats: del user_chats[chat_id]
        await query.edit_message_text("🧹 **Memory ត្រូវបានសម្អាត!**\nបងអាចចាប់ផ្តើមប្រធានបទថ្មីបាន។")
        
    elif data == 'new_chat':
        await query.edit_message_text("💬 **តោះ! បងមានចម្ងល់អ្វីដែរ?**\nសរសេរមកខ្ញុំបានភ្លាមៗ...")
        
    elif data == 'help_code':
        await query.edit_message_text("💻 **Mode សរសេរកូដ:**\nសូមប្រាប់ខ្ញុំពីកូដដែលបងចង់បាន (Python, HTML, JS...)...")
        
    elif data == 'help_vision':
        await query.edit_message_text("📸 **Mode រូបភាព:**\nសូមផ្ញើរូបភាពមក ខ្ញុំនឹងប្រាប់ថាវាជារូបអ្វី។")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_ai(update, context, update.message.text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    img = PIL.Image.open(io.BytesIO(image_bytes))
    
    caption = update.message.caption if update.message.caption else "តើរូបនេះមានន័យដូចម្តេច?"
    await process_ai(update, context, caption, image=img)

# ---------------------------------------------------------
# ៥. MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == '__main__':
    keep_alive() # Start Flask Server
    print("🚀 Sinan AI Premium is Launching...")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    
    # Messages
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()
