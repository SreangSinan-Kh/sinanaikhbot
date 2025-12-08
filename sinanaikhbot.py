import os
import time
import asyncio
import threading
import datetime
import google.generativeai as genai
from flask import Flask, render_template_string
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv

# ---------------------------------------------------------
# ១. CONFIGURATION (ការកំណត់សុវត្ថិភាព)
# ---------------------------------------------------------
# Load .env សម្រាប់ពេលបង Run នៅក្នុងកុំព្យូទ័រ (Local)
# ប៉ុន្តែពេលនៅលើ Render វានឹងចាប់យកពី Environment Variables ដោយខ្លួនឯង
load_dotenv()

# ចាប់យក Key ពី Render Environment
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ពិនិត្យមើលថាតើមាន Key ឬអត់ (ការពារកុំឱ្យ Run ទៅ Error)
if not GOOGLE_API_KEY or not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ រកមិនឃើញ API Key ទេ! សូមពិនិត្យមើល Environment Variables ក្នុង Render របស់អ្នក។")

# កំណត់ពេលចាប់ផ្តើម (ដើម្បីគណនា Uptime)
START_TIME = datetime.datetime.now()

# Setup AI
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# ---------------------------------------------------------
# ២. STUNNING WEB DASHBOARD (HTML កប់ក្នុង Python)
# ---------------------------------------------------------
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="km">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sinan AI | Status</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Battambang:wght@400;700&family=Orbitron:wght@500;900&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Battambang', sans-serif; background-color: #000; color: white; overflow: hidden; }
        .neon-text { text-shadow: 0 0 15px rgba(6, 182, 212, 0.7); font-family: 'Orbitron', sans-serif; }
        .glass-panel {
            background: rgba(20, 20, 20, 0.6);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }
        .status-dot {
            box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7);
            animation: pulse-green 2s infinite;
        }
        @keyframes pulse-green {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
        }
    </style>
</head>
<body class="flex items-center justify-center h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900">
    <div class="glass-panel w-full max-w-3xl rounded-2xl p-10 m-4 relative overflow-hidden">
        
        <div class="flex justify-between items-end mb-10 border-b border-gray-800 pb-6">
            <div>
                <h1 class="text-4xl font-bold text-white neon-text mb-2">SINAN AI</h1>
                <p class="text-gray-400 text-sm tracking-widest">SECURE SYSTEM v2.0</p>
            </div>
            <div class="flex items-center gap-2 bg-green-500/10 px-4 py-1 rounded border border-green-500/20">
                <div class="w-2 h-2 bg-green-500 rounded-full status-dot"></div>
                <span class="text-green-500 font-mono text-xs font-bold">OPERATIONAL</span>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="p-6 rounded-xl bg-white/5 border border-white/5 hover:border-cyan-500/30 transition-all">
                <i class="fa-solid fa-server text-cyan-400 text-2xl mb-4"></i>
                <div class="text-gray-500 text-xs font-mono mb-1">UPTIME</div>
                <div class="text-2xl font-bold tracking-tight">{{ uptime }}</div>
            </div>
            <div class="p-6 rounded-xl bg-white/5 border border-white/5 hover:border-purple-500/30 transition-all">
                <i class="fa-solid fa-brain text-purple-400 text-2xl mb-4"></i>
                <div class="text-gray-500 text-xs font-mono mb-1">ENGINE</div>
                <div class="text-xl font-bold">Gemini 1.5</div>
            </div>
            <div class="p-6 rounded-xl bg-white/5 border border-white/5 hover:border-blue-500/30 transition-all">
                <i class="fa-solid fa-shield-halved text-blue-400 text-2xl mb-4"></i>
                <div class="text-gray-500 text-xs font-mono mb-1">ENV SECURITY</div>
                <div class="text-xl font-bold text-blue-400">Protected</div>
            </div>
        </div>

        <div class="mt-10 text-center">
            <p class="text-gray-600 text-[10px] font-mono">DEPLOYED ON RENDER | DEVELOPED BY SINAN</p>
        </div>
    </div>
</body>
</html>
"""

# ---------------------------------------------------------
# ៣. FLASK SERVER (Keep Alive & Dashboard)
# ---------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    delta = datetime.datetime.now() - START_TIME
    uptime_str = str(delta).split('.')[0]
    return render_template_string(DASHBOARD_HTML, uptime=uptime_str)

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

# ---------------------------------------------------------
# ៤. TELEGRAM BOT HANDLERS
# ---------------------------------------------------------

# Menu ក្នុង Telegram
def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("💬 សន្ទនាថ្មី", callback_data='new'),
            InlineKeyboardButton("🧹 លុបប្រវត្តិ", callback_data='clear')
        ],
        [
            InlineKeyboardButton("📊 មើល Status", callback_data='status'),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.last_name
    welcome_text = (
        f"👋 **សួស្តី បង {user}!**\n"
        f"ប្រព័ន្ធ AI ដំណើរការដោយសុវត្ថិភាព (Environment Protected) 🔐\n"
        f"តើបងចង់ឱ្យខ្ញុំជួយអ្វីថ្ងៃនេះ?"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=get_main_menu())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'status':
        delta = datetime.datetime.now() - START_TIME
        uptime = str(delta).split('.')[0]
        await query.edit_message_text(f"📊 **System Status:**\n✅ Online\n⏱️ Uptime: `{uptime}`\n🔐 API Security: `Encrypted`", parse_mode='Markdown', reply_markup=get_main_menu())
    
    elif query.data == 'new' or query.data == 'clear':
        await query.edit_message_text("✨ បានចាប់ផ្តើមថ្មី!", reply_markup=get_main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    # 1. Animation (Loading)
    loading_msg = await context.bot.send_message(chat_id, "AI កំពុងគិត... 🔄")
    
    async def animate():
        emojis = ["🔄", "⏳", "🧐", "🧠", "💡"]
        i = 0
        while True:
            await asyncio.sleep(2)
            try:
                i = (i + 1) % len(emojis)
                await context.bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=loading_msg.message_id, 
                    text=f"AI កំពុងគិត... {emojis[i]}"
                )
            except: break
            
    task = asyncio.create_task(animate())

    try:
        # 2. Call Gemini AI
        response = await asyncio.to_thread(model.generate_content, user_text)
        
        # 3. Stop Animation
        task.cancel()
        try: await context.bot.delete_message(chat_id, loading_msg.message_id)
        except: pass

        # 4. Send Response
        await context.bot.send_message(chat_id, response.text, parse_mode='Markdown')

    except Exception as e:
        task.cancel()
        await context.bot.edit_message_text(chat_id=chat_id, message_id=loading_msg.message_id, text=f"⚠️ Error: {e}")

# ---------------------------------------------------------
# ៥. MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == '__main__':
    print("🚀 SINAN AI: Secure Boot...")
    keep_alive() # Start Web Server
    
    app_bot = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(CallbackQueryHandler(callback_handler))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app_bot.run_polling()
