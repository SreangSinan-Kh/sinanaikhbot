import google.generativeai as genai
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import PIL.Image
import io
import os
import tempfile 
import asyncio

# ---------------------------------------------------------
# ១. ការកំណត់ (CONFIGURATION)
# ---------------------------------------------------------
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyAuJA4BSuQnmwrZS_rtDIFL1it4O8IDYag") 
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8536901055:AAGur-CXAyDNXz2EfG-SgQpTV-UedZHkjxs")

MODEL_NAME = 'gemini-2.0-flash' 

# ទុកស្ថិតិ
user_data = {
    "usage_count": 0
}

# Prompt ឆ្លាតវៃ (Super Assistant)
SUPER_SYSTEM_PROMPT = """
អ្នកគឺជា AI Assistant ផ្ទាល់ខ្លួនដ៏ឆ្លាតវៃបំផុត។
តួនាទី៖
1. ឆ្លើយតបច្បាស់ៗ និងរហ័ស។
2. អាចអានឯកសារ (PDF, Excel, Code) និងវិភាគរូបភាព/សំឡេង។
3. បើគេអោយសរសេរកូដ ត្រូវសរសេរ Clean Code។
ភាសា៖ ប្រើភាសាខ្មែរជាគោល។
"""

genai.configure(api_key=GOOGLE_API_KEY)
user_chats = {} 

# ---------------------------------------------------------
# ២. UI & MENU CONFIGURATION
# ---------------------------------------------------------

async def post_init(application: Application):
    """
    មុខងារនេះនឹងបង្កើត Menu (Hamburger button) នៅជាប់កន្លែងវាយអក្សរ
    """
    bot_commands = [
        BotCommand("start", "🏠 ម៉ឺនុយដើម (Dashboard)"),
        BotCommand("new", "✨ សន្ទនាថ្មី (New Chat)"),
        BotCommand("clear", "🗑️ លុបការចងចាំ (Clear)"),
        BotCommand("help", "❓ ជំនួយ (Help)"),
    ]
    await application.bot.set_my_commands(bot_commands)

def get_main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("✨ សន្ទនាថ្មី", callback_data='new_chat'),
            InlineKeyboardButton("🗑️ លុប Memory", callback_data='clear_mem')
        ],
        [
            InlineKeyboardButton("👤 គណនី", callback_data='my_profile'),
            InlineKeyboardButton("❓ ជំនួយ", callback_data='help_mode')
        ],
        [InlineKeyboardButton("🔄 Refresh Dashboard", callback_data='refresh_stats')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔍 ពន្យល់បន្ថែម", callback_data='act_explain'), InlineKeyboardButton("📝 កែសម្រួល", callback_data='act_fix')],
    ]
    return InlineKeyboardMarkup(keyboard)

async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, is_edit=False):
    user = update.effective_user
    count = user_data['usage_count']
    
    # Text
    dashboard_text = (
        f"👋 **សួស្តី, បង {user.first_name}!**\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 **SINAN AI PREMIUM**\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ **គាំទ្រពេញលេញ:**\n"
        f"• 📝 អក្សរ & កូដ (Text/Code)\n"
        f"• 📸 រូបភាព (Vision)\n"
        f"• 🎙️ សំឡេង (Voice)\n"
        f"• 📂 ឯកសារ (PDF, Excel, Word...)\n\n"
        f"📨 Messages: `{count}`\n"
        f"🟢 System: `Online`"
    )

    if is_edit:
        try:
            await update.callback_query.edit_message_text(text=dashboard_text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_main_menu_keyboard())
        except: pass 
    else:
        await update.message.reply_text(text=dashboard_text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_main_menu_keyboard())

# ---------------------------------------------------------
# ៣. LOGIC HANDLERS
# ---------------------------------------------------------

def get_chat_session(chat_id):
    if chat_id not in user_chats:
        model = genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=SUPER_SYSTEM_PROMPT)
        user_chats[chat_id] = model.start_chat(history=[])
    return user_chats[chat_id]

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_dashboard(update, context, is_edit=False)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = update.effective_chat.id
    await query.answer()

    if data == 'refresh_stats':
        await show_dashboard(update, context, is_edit=True)
    elif data == 'new_chat' or data == 'clear_mem':
        if chat_id in user_chats: del user_chats[chat_id]
        msg = "✨ **ចាប់ផ្តើមថ្មី!**\nបងអាចផ្ញើ សារ, រូបភាព, ឬ ឯកសារមកខ្ញុំបាន..."
        await query.edit_message_text(msg, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_main_menu_keyboard())
    elif data == 'help_mode':
        help_text = "❓ **ជំនួយ:**\n- និយាយ (Voice) ដាក់ខ្ញុំបាន\n- ផ្ញើឯកសារ PDF/Excel ខ្ញុំនឹងអាន\n- ផ្ញើរូបភាព ខ្ញុំនឹងវិភាគ"
        await query.edit_message_text(help_text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ត្រឡប់", callback_data='refresh_stats')]]))
    
    # Action Buttons logic
    elif data.startswith('act_'):
        prompt = "ពន្យល់អោយច្បាស់ជាងនេះ" if data == 'act_explain' else "ជួយកែសម្រួលកូដ ឬអត្ថបទខាងលើ"
        await process_ai_request(update, context, prompt, chat_id)

# ---------------------------------------------------------
# ៤. FILE & MEDIA HANDLING (NEW FEATURE)
# ---------------------------------------------------------

async def handle_universal_file(update, context, file_obj, mime_type, user_prompt):
    """Function នេះសម្រាប់ដោះស្រាយរាល់ឯកសារ (Voice, PDF, Doc...)"""
    chat_id = update.effective_chat.id
    user_data['usage_count'] += 1
    
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ កំពុងដំណើរការឯកសារ...")

    try:
        # 1. Download file ពី Telegram
        file_data = await file_obj.get_file()
        
        # កំណត់ extension
        ext = ".bin"
        if mime_type == 'audio/ogg': ext = ".ogg"
        elif mime_type == 'application/pdf': ext = ".pdf"
        
        # Save ចូល Temp file
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
            await file_data.download_to_drive(custom_path=temp_file.name)
            temp_path = temp_file.name

        # 2. Upload ទៅ Gemini
        uploaded_file = genai.upload_file(temp_path, mime_type=mime_type)

        # 3. Generate Content
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([user_prompt, uploaded_file])

        # Cleanup
        os.remove(temp_path)
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)

        # 4. Reply
        await send_smart_response(context, chat_id, response.text)

    except Exception as e:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"⚠️ Error: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ទទួល Voice Message"""
    await handle_universal_file(update, context, update.message.voice, "audio/ogg", "ស្តាប់សំឡេងនេះ ហើយឆ្លើយតបជាភាសាខ្មែរ។")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ទទួលឯកសារគ្រប់ប្រភេទ"""
    doc = update.message.document
    caption = update.message.caption if update.message.caption else f"វិភាគឯកសារ {doc.file_name} នេះ។"
    await handle_universal_file(update, context, doc, doc.mime_type, caption)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ទទួលរូបភាព"""
    chat_id = update.effective_chat.id
    user_data['usage_count'] += 1
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    img = PIL.Image.open(io.BytesIO(image_bytes))
    
    caption = update.message.caption if update.message.caption else "វិភាគរូបនេះ"
    await process_ai_request(update, context, caption, chat_id, image=img)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ទទួលសារអក្សរ"""
    chat_id = update.effective_chat.id
    text = update.message.text
    user_data['usage_count'] += 1
    await process_ai_request(update, context, text, chat_id)

# ---------------------------------------------------------
# ៥. AI CORE ENGINE
# ---------------------------------------------------------
async def process_ai_request(update, context, prompt, chat_id, image=None):
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    try:
        response_text = ""
        if image:
            vision_model = genai.GenerativeModel(MODEL_NAME)
            response = vision_model.generate_content([prompt, image])
            response_text = response.text
        else:
            chat = get_chat_session(chat_id)
            response = chat.send_message(prompt)
            response_text = response.text

        await send_smart_response(context, chat_id, response_text)

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {str(e)}")

async def send_smart_response(context, chat_id, text):
    if len(text) > 4000:
        file_stream = io.BytesIO(text.encode('utf-8'))
        file_stream.name = "response.md"
        await context.bot.send_document(chat_id=chat_id, document=file_stream, caption="✅ ចម្លើយបានភ្ជាប់ក្នុង File។")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_action_keyboard())

# ---------------------------------------------------------
# ៦. SYSTEM START
# ---------------------------------------------------------
if __name__ == '__main__':
    print("🚀 Sinan AI Bot is starting...")
    # ប្រើ post_init ដើម្បីបង្កើត Menu Command ពេល Bot ចាប់ផ្តើម
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", lambda u,c: show_dashboard(u,c,True)))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice)) # បន្ថែម Voice
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document)) # បន្ថែម Document គ្រប់ប្រភេទ
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()