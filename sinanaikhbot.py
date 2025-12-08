import os
import io
import time
import asyncio  # ចាំបាច់សម្រាប់ធ្វើ Animation
import threading
import tempfile
import google.generativeai as genai
from flask import Flask
from dotenv import load_dotenv
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ---------------------------------------------------------
# ១. CONFIGURATION & SERVER KEEP-ALIVE (សម្រាប់ Run លើ Server)
# ---------------------------------------------------------
load_dotenv()

# Web Server ដើម្បីបន្លំ Render/Replit កុំឱ្យដេក
app = Flask('')

@app.route('/')
def home():
    return "✅ Sinan AI Bot Pro is Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# API Credentials
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not GOOGLE_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("❌ សូមបញ្ចូល API Key ក្នុង .env file ជាមុនសិន!")

# Setup Gemini
genai.configure(api_key=GOOGLE_API_KEY)
MODEL_NAME = 'gemini-1.5-flash'  # ប្រើ Flash ដើម្បីល្បឿនលឿន និងសន្សំសំចៃ

# System Prompt
SYSTEM_INSTRUCTION = """
អ្នកគឺជា "Sinan AI Assistant" (ជំនួយការរបស់បង ស៊ីណាន)។
1. ភាសា៖ ប្រើភាសាខ្មែរជាគោល មានសុជីវធម៌ និងច្បាស់លាស់។
2. សមត្ថភាព៖ អាចវិភាគរូបភាព កូដ ឯកសារ និងឆ្លើយតបដូច ChatGPT/Gemini Pro។
3. ការបង្ហាញ៖ ប្រើ Emoji ឱ្យបានសមរម្យ។ ប្រើ Bold សម្រាប់ចំណុចសំខាន់។
4. បើគេសួររឿងកូដ៖ សរសេរកូដក្នុង ```programming_language ... ``` ជានិច្ច។
"""

# ផ្ទុកប្រវត្តិ Chat (In-Memory)
user_chats = {}

# ---------------------------------------------------------
# ២. SMART MENU & UI
# ---------------------------------------------------------

def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("✨ សន្ទនាថ្មី (New Chat)", callback_data='cmd_new'),
            InlineKeyboardButton("🗑️ លុបប្រវត្តិ (Clear)", callback_data='cmd_clear')
        ],
        [
            InlineKeyboardButton("❓ របៀបប្រើ", callback_data='cmd_help'),
            InlineKeyboardButton("👨‍💻 អំពីខ្ញុំ", callback_data='cmd_about')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_response_menu():
    keyboard = [
        [
            InlineKeyboardButton("📝 សង្ខេប", callback_data='act_summarize'),
            InlineKeyboardButton("🇬🇧 ទៅជា English", callback_data='act_translate'),
        ],
        [
             InlineKeyboardButton("🔍 ពន្យល់បន្ថែម", callback_data='act_explain'),
             InlineKeyboardButton("💻 កែកូដ", callback_data='act_fix_code')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------------------------------------------------------
# ៣. AI LOGIC & ANIMATION HANDLER (កន្លែងសំខាន់)
# ---------------------------------------------------------

def get_chat_session(chat_id):
    if chat_id not in user_chats:
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_INSTRUCTION)
        user_chats[chat_id] = model.start_chat(history=[])
    return user_chats[chat_id]

async def process_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, chat_id: int):
    # ១. ផ្ញើសារ "Loading" ជាមុនសិន
    status_msg = await context.bot.send_message(chat_id, "AI កំពុងគិត... 🔄", parse_mode='Markdown')

    # ២. បង្កើតមុខងារ Animation (ដំណើរការនៅ Background)
    async def keep_animating():
        emojis = ["🔄", "⏳", "🧐", "🧠", "💡", "⚡", "✍️"]
        idx = 0
        while True:
            await asyncio.sleep(2.0) # រង់ចាំ 2 វិនាទី
            try:
                idx = (idx + 1) % len(emojis)
                # Edit សារដើម្បីប្តូរ Emoji
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text=f"AI កំពុងគិត... {emojis[idx]}"
                )
            except Exception:
                # ឈប់បើមានបញ្ហា (ឧ. សារត្រូវបានលុប ឬ Edit មិនបាន)
                break 

    # ៣. ចាប់ផ្តើម Animation Task
    animation_task = asyncio.create_task(keep_animating())

    try:
        # ៤. ហៅទៅ AI (ប្រើ asyncio.to_thread ដើម្បីកុំឱ្យគាំង Animation)
        # ព្រោះ function របស់ google genai មិនមែនជា async ពីកំណើត
        chat = get_chat_session(chat_id)
        response = await asyncio.to_thread(chat.send_message, text)

        # ៥. ពេលបានចម្លើយ -> ឈប់ Animation -> លុបសារ Loading
        animation_task.cancel()
        try:
            await context.bot.delete_message(chat_id, status_msg.message_id)
        except:
            pass 

        # ៦. ផ្ញើចម្លើយពិតប្រាកដ
        await send_smart_response(context, chat_id, response.text)

    except Exception as e:
        animation_task.cancel()
        await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=status_msg.message_id, 
            text=f"⚠️ **មានបញ្ហា៖** \n{str(e)}", 
            parse_mode='Markdown'
        )

async def send_smart_response(context, chat_id, text):
    # បើវែងពេក (>4096 តួ) កាត់ដាក់ក្នុងឯកសារ
    if len(text) > 4000:
        file_stream = io.BytesIO(text.encode('utf-8'))
        file_stream.name = "ai_response.md"
        await context.bot.send_document(chat_id=chat_id, document=file_stream, caption="✅ ចម្លើយវែងពេក ខ្ញុំដាក់ក្នុងឯកសារជូនណា៎!")
    else:
        # ផ្ញើចម្លើយធម្មតា ជាមួយប៊ូតុង Menu
        await context.bot.send_message(
            chat_id=chat_id, 
            text=text, 
            parse_mode=constants.ParseMode.MARKDOWN, 
            reply_markup=get_response_menu()
        )

# ---------------------------------------------------------
# ៤. HANDLERS (អ្នកទទួលសារ)
# ---------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_msg = (
        f"👋 **សួស្តី បង {user.last_name}!**\n"
        f"ស្វាគមន៍មកកាន់ **Sinan AI Assistant Pro** 🚀\n\n"
        f"ខ្ញុំត្រៀមខ្លួនរួចរាល់សម្រាប់ជួយបង៖\n"
        f"🔹 សរសេរកូដ & ដោះស្រាយបញ្ហា\n"
        f"🔹 វិភាគឯកសារ & រូបភាព\n"
        f"👇 **សូមសាកល្បងសួរខ្ញុំឥឡូវនេះ!**"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=get_main_menu())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = update.effective_chat.id
    await query.answer() # បំបាត់ Loading នៅលើប៊ូតុង

    # បញ្ជាទូទៅ
    if data == 'cmd_new' or data == 'cmd_clear':
        if chat_id in user_chats: del user_chats[chat_id]
        await query.edit_message_text("🧹 **បានលុបប្រវត្តិរួចរាល់!**\nតោះចាប់ផ្តើមសួរខ្ញុំសាថ្មី...", parse_mode='Markdown', reply_markup=get_main_menu())
    
    elif data == 'cmd_help':
        await query.edit_message_text("💡 គ្រាន់តែផ្ញើសារ រូបភាព ឬឯកសារ ខ្ញុំនឹងឆ្លើយតបភ្លាមៗ!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ត្រឡប់", callback_data='cmd_start')]]))

    elif data == 'cmd_start':
        await start_command(update, context)

    # Smart Actions (សង្ខេប, បកប្រែ...)
    elif data.startswith('act_'):
        prompt = ""
        if data == 'act_summarize': prompt = "សូមសង្ខេបខ្លឹមសារខាងលើឱ្យខ្លី។"
        elif data == 'act_translate': prompt = "Translate the above response to English."
        elif data == 'act_explain': prompt = "ពន្យល់បន្ថែមឱ្យលម្អិត។"
        elif data == 'act_fix_code': prompt = "ជួយពិនិត្យកូដ និងកែសម្រួលឱ្យល្អ។"
        
        # ហៅទៅ Process ដូចការសួរធម្មតា
        await process_ai_request(update, context, prompt, chat_id)

# ទទួលរូបភាព/ឯកសារ/សំឡេង
async def handle_universal_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message = update.message
    
    # កំណត់ប្រភេទឯកសារ
    file_obj = None
    mime_type = ""
    caption = message.caption or "វិភាគឯកសារនេះ"

    if message.photo:
        file_obj = await message.photo[-1].get_file()
        mime_type = "image/jpeg"
    elif message.voice:
        file_obj = await message.voice.get_file()
        mime_type = "audio/ogg"
        caption = "ឆ្លើយតបនឹងសំឡេងនេះ"
    elif message.document:
        file_obj = await message.document.get_file()
        mime_type = message.document.mime_type
    
    if not file_obj: return

    # បង្ហាញ Loading
    status_msg = await context.bot.send_message(chat_id, "📂 កំពុងដំណើរការឯកសារ... ⏳")

    try:
        # Download ដាក់ Temp
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            await file_obj.download_to_drive(custom_path=temp.name)
            temp_path = temp.name

        # Upload ទៅ Gemini
        uploaded_file = await asyncio.to_thread(genai.upload_file, temp_path, mime_type=mime_type)
        
        # Generate ចម្លើយ
        model = genai.GenerativeModel(MODEL_NAME)
        response = await asyncio.to_thread(model.generate_content, [caption, uploaded_file])

        # Cleanup
        os.remove(temp_path)
        await context.bot.delete_message(chat_id, status_msg.message_id)
        
        await send_smart_response(context, chat_id, response.text)

    except Exception as e:
        await context.bot.edit_message_text(f"❌ Error: {str(e)}", chat_id=chat_id, message_id=status_msg.message_id)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_ai_request(update, context, update.message.text, update.effective_chat.id)

# ---------------------------------------------------------
# ៥. SYSTEM START
# ---------------------------------------------------------
if __name__ == '__main__':
    keep_alive() # បើក Web Server
    print("🚀 Sinan AI Assistant (Full Version) is Starting...")
    
    app_bot = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands & Callbacks
    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(CallbackQueryHandler(handle_callback))

    # Media Handlers
    app_bot.add_handler(MessageHandler(filters.PHOTO | filters.VOICE | filters.Document.ALL, handle_universal_media))
    
    # Text Handler (ដាក់ចុងក្រោយ)
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app_bot.run_polling()
