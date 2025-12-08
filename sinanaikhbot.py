import google.generativeai as genai
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest
import PIL.Image
import io
import os
import asyncio
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# ---------------------------------------------------------
# ១. ការកំណត់ CONFIGURATION & SYSTEM
# ---------------------------------------------------------
load_dotenv()

# --- Flask Server (Keep Alive for Render) ---
app = Flask('')

@app.route('/')
def home():
    return "✅ SINAN AI BOT IS RUNNING!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# --- API Configuration ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not GOOGLE_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("⚠️ សូមពិនិត្យមើល Environment Variables របស់អ្នក!")

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# ប្រើ Model Flash ព្រោះវាលឿន និងឆ្លាត (អាចប្តូរទៅ pro តាមចិត្ត)
MODEL_NAME = 'gemini-1.5-flash' 

# ស្ថិតិប្រើប្រាស់
bot_stats = {"users": set(), "messages": 0}

# System Prompt ដែលកំណត់អត្តសញ្ញាណ Bot
SYSTEM_INSTRUCTION = """
អ្នកគឺជា "Sinan AI" (ស៊ីណាន AI) ដែលជាជំនួយការឆ្លាតវៃ បង្កើតឡើងដោយស៊ីណាន។
- ភាសា៖ ឆ្លើយតបជាភាសាខ្មែរជានិច្ច (លើកលែងតែកូដ ឬពាក្យបច្ចេកទេស)។
- ឥរិយាបថ៖ រួសរាយ, ឆ្លាត, និងចេះជួយដោះស្រាយបញ្ហា។
- ជំនាញ៖ សរសេរកូដ, វិភាគទិន្នន័យ, បកប្រែ, និងណែនាំយុទ្ធសាស្ត្រ។
- Formatting: ប្រើប្រាស់ Emoji អោយបានសមរម្យដើម្បីអោយអត្ថបទគួរអោយចង់អាន។
"""

# ផ្ទុកប្រវត្តិ Chat (Memory)
user_chats = {}

# ---------------------------------------------------------
# ២. ផ្នែក UI & KEYBOARDS (MENU ទំនើប)
# ---------------------------------------------------------

async def set_bot_commands(application: Application):
    commands = [
        BotCommand("start", "🏠 ម៉ឺនុយដើម (Main Menu)"),
        BotCommand("reset", "🧹 លុបការចងចាំ (New Topic)"),
        BotCommand("help", "🆘 ជំនួយ (Help)"),
    ]
    await application.bot.set_my_commands(commands)

def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("💬 ជជែកលេង", callback_data='mode_chat'),
            InlineKeyboardButton("🧹 ចាប់ផ្តើមថ្មី", callback_data='act_clear')
        ],
        [
            InlineKeyboardButton("📝 សង្ខេបអត្ថបទ", callback_data='mode_summarize'),
            InlineKeyboardButton("💻 ជួយកែកូដ", callback_data='mode_code')
        ],
        [
            InlineKeyboardButton("🌐 បកប្រែ (EN-KH)", callback_data='mode_translate'),
            InlineKeyboardButton("📊 ស្ថិតិ Bot", callback_data='view_stats')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_home_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ត្រឡប់ទៅដើម", callback_data='go_home')]])

# ---------------------------------------------------------
# ៣. UTILITIES (ជំនួយការ)
# ---------------------------------------------------------

# ដោះស្រាយបញ្ហា Markdown ដែលធ្វើអោយ Bot គាំង
def escape_markdown(text: str) -> str:
    # Telegram MarkdownV2 reserved characters
    chars = r"_*[]()~`>#+-=|{}.!"
    for c in chars:
        # យើងមិន escape ទាំងអស់ទេ ព្រោះចង់អោយ Gemini អាចប្រើ Bold/Code បាន
        # នេះជាវិធីសាមញ្ញ បើ Gemini ឆ្លើយមកមាន Format ត្រឹមត្រូវស្រាប់
        pass 
    return text

async def send_long_message(context, chat_id, text, reply_markup=None):
    """កាត់សារវែងៗជាផ្នែកៗ ដើម្បីកុំអោយលើសកំណត់ Telegram (4096 chars)"""
    max_length = 4000
    if len(text) <= max_length:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=reply_markup)
        except BadRequest:
            # បើ Markdown Error, ផ្ញើជាអក្សរធម្មតាវិញ
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    else:
        # បើសារវែងខ្លាំង
        parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        for part in parts[:-1]:
            await context.bot.send_message(chat_id=chat_id, text=part)
        # ផ្នែកចុងក្រោយភ្ជាប់ជាមួយ Button
        await context.bot.send_message(chat_id=chat_id, text=parts[-1], reply_markup=reply_markup)

# ---------------------------------------------------------
# ៤. CORE LOGIC (ខួរក្បាល AI)
# ---------------------------------------------------------

def get_gemini_chat(chat_id):
    if chat_id not in user_chats:
        model = genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=SYSTEM_INSTRUCTION)
        user_chats[chat_id] = model.start_chat(history=[])
    return user_chats[chat_id]

async def process_ai_request(update, context, prompt, image=None, file_data=None, mime_type=None):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Update Stats
    bot_stats["users"].add(user.id)
    bot_stats["messages"] += 1

    # Send "Typing..." action
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    
    try:
        response_text = ""
        
        # ករណីមានរូបភាព
        if image:
            model = genai.GenerativeModel(MODEL_NAME)
            response = model.generate_content([prompt, image])
            response_text = response.text
            
        # ករណីមានឯកសារ (PDF, Audio, etc.)
        elif file_data and mime_type:
            model = genai.GenerativeModel(MODEL_NAME)
            
            # Upload file ទៅ Gemini (In-Memory មិនបាច់ Save ចូល Disk)
            # Gemini File API ត្រូវការ Path, តែយើងអាចប្រើវិធីដាក់ content ផ្ទាល់
            # សំរាប់ File ធំៗ យើងគួរប្រើ File API របស់ Google (Upload)
            # តែដើម្បីងាយស្រួលក្នុងកូដនេះ យើងនឹងប្រើវិធីសាមញ្ញបំផុតសម្រាប់ Text based files
            # *ចំណាំ*: សំរាប់ PDF/Audio ធំៗ ត្រូវការវិធី Upload ពិសេស។ 
            # នៅទីនេះខ្ញុំសន្មតថាវាជា Text/Code file ឬរូបភាព។ 
            
            # សំរាប់កូដនេះ យើងនឹងប្រើវិធី Text extraction សាមញ្ញ ឬ Vision
            # (Gemini 1.5 Flash អាចទទួល Video/Audio/PDF តាម API)
            # ដើម្បីកុំអោយស្មុគស្មាញ យើងនឹងប្រើ prompt ធម្មតាសិន
            response_text = "⚠️ បច្ចុប្បន្ន Bot កំពុងអាប់ដេតមុខងារអានឯកសារផ្ទាល់។ សូមផ្ញើជារូបភាព ឬអក្សរជំនួសវិញ។"
            
        # ករណីអក្សរសុទ្ធ
        else:
            chat = get_gemini_chat(chat_id)
            response = chat.send_message(prompt)
            response_text = response.text

        # ផ្ញើចម្លើយត្រឡប់ទៅវិញ
        await send_long_message(context, chat_id, response_text, reply_markup=get_back_home_btn())

    except Exception as e:
        error_msg = f"❌ **មានបញ្ហាបច្ចេកទេស:**\n`{str(e)}`\nសូមព្យាយាមម្តងទៀត។"
        await context.bot.send_message(chat_id=chat_id, text=error_msg, parse_mode=constants.ParseMode.MARKDOWN)

# ---------------------------------------------------------
# ៥. HANDLERS (អ្នកទទួលសារ)
# ---------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_msg = (
        f"👋 **សួស្តី បង {user.first_name}!**\n\n"
        f"ខ្ញុំគឺ **Sinan AI** ជាជំនួយការផ្ទាល់ខ្លួនរបស់បង។\n"
        f"ខ្ញុំអាចជួយបងបានច្រើនយ៉ាងដូចជា៖\n\n"
        f"• 🧠 ឆ្លើយសំណួរទូទៅ និងបច្ចេកទេស\n"
        f"• 💻 សរសេរ និងកែសម្រួលកូដ\n"
        f"• 👁️ មើលរូបភាព និងវិភាគទិន្នន័យ\n"
        f"• 🗣️ ស្តាប់សារជាសំឡេង\n\n"
        f"⏬ **សូមជ្រើសរើសមុខងារខាងក្រោម:**"
    )
    await update.message.reply_text(welcome_msg, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_main_menu())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    if data == 'go_home':
        await start_command(update, context)
        
    elif data == 'act_clear':
        if chat_id in user_chats: del user_chats[chat_id]
        await query.edit_message_text("🧹 **ការចងចាំត្រូវបានលុប!**\nបងអាចចាប់ផ្តើមប្រធានបទថ្មីបាន។", parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_main_menu())

    elif data == 'view_stats':
        stat_msg = (
            f"📊 **ស្ថិតិ Sinan AI Bot**\n"
            f"━━━━━━━━━━━━━━\n"
            f"👥 អ្នកប្រើប្រាស់សរុប: `{len(bot_stats['users'])}`\n"
            f"📨 សារដែលបានឆ្លើយ: `{bot_stats['messages']}`\n"
            f"🟢 ស្ថានភាព: `Online`"
        )
        await query.edit_message_text(stat_msg, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=get_back_home_btn())

    elif data.startswith('mode_'):
        mode_map = {
            'mode_translate': "សូមផ្ញើអត្ថបទដែលបងចង់បកប្រែ (អង់គ្លេស <-> ខ្មែរ)...",
            'mode_code': "សូមផ្ញើកូដ ឬប្រាប់ពីអ្វីដែលបងចង់អោយខ្ញុំសរសេរ...",
            'mode_summarize': "សូមផ្ញើអត្ថបទវែងៗដែលបងចង់សង្ខេប...",
            'mode_chat': "តោះ! បងចង់សួរអ្វីខ្លះ?"
        }
        await query.edit_message_text(f"✅ **{mode_map[data]}**", reply_markup=get_back_home_btn())
        # យើងអាច Save state ថា user កំពុងស្ថិតក្នុង Mode ណាបានប្រសិនបើចង់ (Optional)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_ai_request(update, context, update.message.text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    img = PIL.Image.open(io.BytesIO(image_bytes))
    
    caption = update.message.caption if update.message.caption else "តើរូបភាពនេះបង្ហាញពីអ្វី?"
    await process_ai_request(update, context, caption, image=img)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # សំរាប់ Voice: Gemini 1.5 Flash អាចស្តាប់បាន ប៉ុន្តែត្រូវការ Upload File API
    # ដើម្បីងាយស្រួល យើងនឹងប្រាប់ User អោយដឹងសិន
    await update.message.reply_text("🎙️ មុខងារស្តាប់សំឡេងកំពុងអាប់ដេត។ សូមសរសេរជាអក្សរសិនបង!", reply_markup=get_back_home_btn())

# ---------------------------------------------------------
# ៦. MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == '__main__':
    keep_alive() # Run Flask Server
    print("🚀 Sinan AI Bot is Starting...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(set_bot_commands).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reset", lambda u,c: handle_callback(u,c))) # Reuse logic
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()
