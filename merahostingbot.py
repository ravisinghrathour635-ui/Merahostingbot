# -*- coding: utf-8 -*-
import hashlib
import telebot
import subprocess
import os
import json
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import logging
import threading
import sys
import atexit
import requests
import re
from pymongo import MongoClient
import certifi
import dns.resolver

# ============================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ============================================
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
OWNER_ID = int(os.environ.get('OWNER_ID', '7692672287'))
ADMIN_ID = int(os.environ.get('ADMIN_ID', '7692672287'))
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', 'MS_HAC4KER')
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/PHANTOM_CODERS')
MONGO_URL = os.environ.get('MONGO_URL', 'YOUR_MONGODB_URL_HERE')

# Force Sub Channels
FSUB_CH_1_ID = os.environ.get('FSUB_CH_1_ID', '@MS_HAC4KER_bio')
FSUB_CH_2_ID = os.environ.get('FSUB_CH_2_ID', '@MS_HAC4KER7')
FSUB_LINK_1 = os.environ.get('FSUB_LINK_1', 'https://t.me/PHANTOM_CODERS_bio')
FSUB_LINK_2 = os.environ.get('FSUB_LINK_2', 'https://t.me/PHANTOM_CODERS7')

# ============================================
# FLASK KEEP ALIVE (FOR RENDER)
# ============================================
from flask import Flask
from threading import Thread
import socket

app = Flask('')

@app.route('/')
def home():
    return "RAJPUT File Host Bot - Running Successfully!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Flask Server running on Port {port}")
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ============================================
# LOGGING SETUP
# ============================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================
# SECURITY SYSTEM
# ============================================
RISKY_KEYWORDS = [
    "rm -rf", "shutil.rmtree", "os.remove", "os.rmdir",
    "os.system", "subprocess.call", "subprocess.Popen",
    "os.walk", "glob.glob",
    "/storage", "/data/data", "/sdcard", "/etc/passwd",
    "eval(", "exec(", "bot_token", "api_id", "api_hash",
    "telegram.Bot", "Client(", "sudo", "chmod"
]

def scan_content_for_risk(content):
    if not content: return False, "No Content"
    try:
        text = content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else str(content)
        for keyword in RISKY_KEYWORDS:
            if keyword in text: return True, keyword
    except: pass
    return False, None

# ============================================
# FOLDER SETUP
# ============================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)

# ============================================
# MONGODB CONNECTION
# ============================================
try:
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8']
    mongo_client = MongoClient(MONGO_URL, tlsCAFile=certifi.where())
    db = mongo_client['RajputFileHostDB']
    col_files = db['files']
    col_subs = db['subscriptions']
    col_config = db['config']
    mongo_client.admin.command('ping')
    logger.info("✅ Connected to MongoDB Successfully!")
except Exception as e:
    logger.error(f"❌ MongoDB Connection Failed: {e}")
    mongo_client = None
    db = None

# ============================================
# BOT INITIALIZATION
# ============================================
bot = telebot.TeleBot(TOKEN)

# ============================================
# DATA STRUCTURES
# ============================================
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# File upload limits
FREE_USER_LIMIT = 3
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# ============================================
# BUTTON LAYOUTS
# ============================================
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "ℹ️ Help & Guide"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "ℹ️ Help & Guide"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["👑 Admin Panel", "🗃️ User Files (Admin)"],
    ["📞 Contact Owner"]
]

# ============================================
# HELPER FUNCTIONS
# ============================================
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_user_joined(user_id):
    if user_id in admin_ids: return True
    try:
        s1 = bot.get_chat_member(FSUB_CH_1_ID, user_id).status
        s2 = bot.get_chat_member(FSUB_CH_2_ID, user_id).status
        if s1 in ['left', 'kicked'] or s2 in ['left', 'kicked']: return False
        return True
    except: return True

def get_fsub_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("📢 Join Channel 1", url=FSUB_LINK_1)
    btn2 = types.InlineKeyboardButton("📢 Join Channel 2", url=FSUB_LINK_2)
    markup.add(btn1, btn2)
    markup.add(types.InlineKeyboardButton("✅ Verify & Continue", callback_data="verify_join"))
    return markup

# ============================================
# TELEGRAM MODULES MAPPING
# ============================================
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'requests': 'requests',
    'flask': 'Flask',
    'pymongo': 'pymongo',
    'dns': 'dnspython',
    'bs4': 'beautifulsoup4',
    'cv2': 'opencv-python-headless',
    'PIL': 'Pillow',
    'yt_dlp': 'yt-dlp',
    'numpy': 'numpy',
    'pandas': 'pandas',
    'sklearn': 'scikit-learn'
}

# ============================================
# MONGODB OPERATIONS
# ============================================
def load_data_from_mongo():
    if db is None: return
    logger.info("📥 Loading data from MongoDB...")
    
    # Load subscriptions
    for doc in col_subs.find():
        try:
            uid = doc['_id']
            user_subscriptions[uid] = {'expiry': datetime.fromisoformat(doc['expiry'])}
        except: pass

    # Load user files
    for doc in col_files.find():
        try:
            uid = doc['_id']
            user_folder = get_user_folder(uid)
            loaded_files = []
            
            for file_data in doc.get('files_data', []): 
                fname = file_data.get('name')
                ftype = file_data.get('type')
                content = file_data.get('content')
                zip_name = file_data.get('zip_name')
                zip_content = file_data.get('zip_content')
                
                restored = False
                if zip_name and zip_content:
                    try:
                        zip_path = os.path.join(user_folder, zip_name)
                        with open(zip_path, 'wb') as f: f.write(zip_content)
                        with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(user_folder)
                        
                        req_path = os.path.join(user_folder, 'requirements.txt')
                        if os.path.exists(req_path):
                            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
                        restored = True
                    except: pass

                if not restored and fname and content:
                    file_path = os.path.join(user_folder, fname)
                    if not os.path.exists(file_path):
                        with open(file_path, 'w', encoding='utf-8', errors='ignore') as f: f.write(content)
                
                if fname: loaded_files.append((fname, ftype))
            
            if loaded_files: user_files[uid] = loaded_files
        except: pass

    # Load active users & admins
    try:
        config_doc = col_config.find_one({'_id': 'global_data'})
        if config_doc:
            active_users.update(set(config_doc.get('active_users', [])))
            admin_ids.update(set(config_doc.get('admins', [])))
            global bot_locked
            bot_locked = config_doc.get('bot_locked', False)
    except: pass

    admin_ids.add(OWNER_ID)
    if ADMIN_ID != OWNER_ID: admin_ids.add(ADMIN_ID)
    logger.info(f"✅ Data Loaded: {len(active_users)} Users, {len(user_files)} User Folders")

# Load data on startup
load_data_from_mongo()

# ============================================
# PENDING FILES MANAGER
# ============================================
PENDING_JSON = "pending_data.json"

def get_short_hash(file_name):
    return hashlib.md5(file_name.encode()).hexdigest()[:10]

def save_pending_entry(f_hash, user_id, file_name):
    data = {}
    try:
        if os.path.exists(PENDING_JSON):
            with open(PENDING_JSON, 'r') as f: data = json.load(f)
    except: pass
    data[f_hash] = {'uid': user_id, 'name': file_name}
    with open(PENDING_JSON, 'w') as f: json.dump(data, f)

def get_pending_entry(f_hash):
    try:
        if os.path.exists(PENDING_JSON):
            with open(PENDING_JSON, 'r') as f: return json.load(f).get(f_hash)
    except: pass
    return None

def remove_pending_entry(f_hash):
    try:
        if os.path.exists(PENDING_JSON):
            with open(PENDING_JSON, 'r') as f: data = json.load(f)
            if f_hash in data:
                del data[f_hash]
                with open(PENDING_JSON, 'w') as f: json.dump(data, f)
    except: pass

# ============================================
# FILE MANAGEMENT
# ============================================
def ensure_user_data_loaded(user_id):
    if user_id in user_files and user_files[user_id]: return True
    if db is not None:
        try:
            user_doc = col_files.find_one({'_id': int(user_id)})
            if user_doc:
                loaded_files = []
                for f in user_doc.get('files_data', []):
                    loaded_files.append((f['name'], f['type']))
                user_files[user_id] = loaded_files
                return True
        except: pass
    return False

def get_file_name_from_hash(user_id, file_hash):
    user_id = int(user_id)
    ensure_user_data_loaded(user_id)
    if user_id in user_files:
        for item in user_files[user_id]:
            fname = item[0] if isinstance(item, (list, tuple)) else item
            if get_short_hash(fname) == file_hash: return fname
    return None

def save_user_file(user_id, file_name, file_type='py', zip_content=None, zip_name=None, forced_risk=None):
    if user_id not in user_files: user_files[user_id] = []
    
    file_content = ""
    if not zip_content:
        try:
            user_folder = get_user_folder(user_id)
            file_path = os.path.join(user_folder, file_name)
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: file_content = f.read()
        except: pass

    scan_data = zip_content if zip_content else file_content
    is_risky, found_keyword = scan_content_for_risk(scan_data)
    if forced_risk: is_risky, found_keyword = True, forced_risk
    
    file_status = "approved"
    if user_id != OWNER_ID and is_risky: file_status = "pending"

    user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
    user_files[user_id].append((file_name, file_type))

    if db is not None:
        try:
            new_entry = {
                "name": file_name, "type": file_type, "content": file_content,
                "zip_name": zip_name, "zip_content": zip_content,
                "status": file_status, "updated_at": datetime.now().isoformat()
            }
            col_files.update_one({'_id': user_id}, {'$pull': {'files_data': {'name': file_name}}}, upsert=True)
            col_files.update_one({'_id': user_id}, {'$push': {'files_data': new_entry}}, upsert=True)
        except: pass

    if file_status == "pending":
        f_hash = get_short_hash(file_name)
        save_pending_entry(f_hash, user_id, file_name)
        msg = f"⚠️ **SECURITY ALERT!**\n👤 User: `{user_id}`\n📂 File: `{file_name}`\n🚫 Found: `{found_keyword}`"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{f_hash}"),
                   types.InlineKeyboardButton("❌ Delete", callback_data=f"disapprove_{user_id}_{f_hash}"))
        try:
            bot.send_message(OWNER_ID, msg, reply_markup=markup, parse_mode='Markdown')
            bot.send_message(user_id, f"⚠️ Your file `{file_name}` contains suspicious code. Sent for Owner Approval.")
        except: pass
        return True
    return False

def remove_user_file_db(user_id, file_name):
    if user_id in user_files:
        user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
        if not user_files[user_id]: del user_files[user_id]
        if db is not None:
            try:
                col_files.update_one({'_id': user_id}, {'$pull': {'files_data': {'name': file_name}}})
            except: pass

# ============================================
# SCRIPT RUNNING FUNCTIONS
# ============================================
def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except:
            if script_key in bot_scripts: del bot_scripts[script_key]
            return False
    return False

def kill_process_tree(process_info):
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close'):
            process_info['log_file'].close()
        
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            try:
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try: child.terminate()
                    except: pass
                parent.terminate()
            except: pass
    except: pass

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    if db is not None:
        try:
            user_doc = col_files.find_one({'_id': script_owner_id}, {'files_data': 1})
            if user_doc:
                for f in user_doc.get('files_data', []):
                    if f.get('name') == file_name and f.get('status') == "pending":
                        bot.reply_to(message_obj_for_reply, "⛔ **Access Denied:** File pending Owner Approval.")
                        return
        except: pass

    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Error: Script not found!")
            remove_user_file_db(script_owner_id, file_name)
            return

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            free_port = s.getsockname()[1]
        
        user_env = os.environ.copy()
        user_env["PORT"] = str(free_port)
        logger.info(f"Assigning Port {free_port} to user script {file_name}")

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        
        process = subprocess.Popen(
            [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
            stdin=subprocess.PIPE, encoding='utf-8', errors='ignore', env=user_env
        )
        
        bot_scripts[script_key] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id,
            'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key
        }
        bot.reply_to(message_obj_for_reply, f"✅ Python script started! (Port: {free_port})")

    except Exception as e:
        logger.error(f"Error starting Python script: {e}")
        bot.reply_to(message_obj_for_reply, f"Error: {e}")

# ============================================
# FILE HANDLING
# ============================================
def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_check_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file: new_file.write(downloaded_file_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        risky_found = False
        risky_reason = None
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(('.py', '.js', '.sh', '.txt', '.json')):
                    file_check_path = os.path.join(root, file)
                    try:
                        with open(file_check_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            is_bad, keyword = scan_content_for_risk(content)
                            if is_bad:
                                risky_found = True
                                risky_reason = f"{keyword} (found in {file})"
                                break
                    except: pass
            if risky_found: break

        user_files_list = []
        for root, dirs, files in os.walk(temp_dir):
            for f in files: user_files_list.append(f)
            
        main_script_name = None; file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']; preferred_js = ['index.js', 'main.js', 'bot.js']
        
        for p in preferred_py:
            if p in user_files_list: main_script_name = p; file_type = 'py'; break
        if not main_script_name:
             for p in preferred_js:
                 if p in user_files_list: main_script_name = p; file_type = 'js'; break
        if not main_script_name:
            py_files = [f for f in user_files_list if f.endswith('.py')]
            js_files = [f for f in user_files_list if f.endswith('.js')]
            if py_files: main_script_name = py_files[0]; file_type = 'py'
            elif js_files: main_script_name = js_files[0]; file_type = 'js'
        
        if not main_script_name:
            bot.reply_to(message, "❌ No Python (.py) or Node (.js) script found inside ZIP!"); return

        is_pending = save_user_file(
            user_id, main_script_name, file_type, 
            zip_content=downloaded_file_content, zip_name=file_name_zip,
            forced_risk=risky_reason
        )
        
        if is_pending: return
        else:
            final_zip_path = os.path.join(user_folder, file_name_zip)
            with open(final_zip_path, 'wb') as f: f.write(downloaded_file_content)
            
            with zipfile.ZipFile(final_zip_path, 'r') as z: z.extractall(user_folder)

            req_file_path = os.path.join(user_folder, 'requirements.txt')
            if os.path.exists(req_file_path):
                bot.reply_to(message, "📦 Installing modules from ZIP...", parse_mode='Markdown')
                try: subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file_path])
                except: pass

            bot.reply_to(message, f"✅ Zip Verified & Safe. Starting `{main_script_name}`...", parse_mode='Markdown')
            main_script_path = os.path.join(user_folder, main_script_name)
            threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()

    except zipfile.BadZipFile:
        bot.reply_to(message, "❌ Error: Invalid ZIP file.")
    except Exception as e:
        logger.error(f"❌ Error processing zip for {user_id}: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass

# ============================================
# BOT COMMAND HANDLERS
# ============================================
def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row_buttons_text])
    return markup

def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not is_user_joined(user_id):
        bot.send_message(chat_id, "⚠️ **Please Join Our Channels First!**", reply_markup=get_fsub_markup(), parse_mode='Markdown')
        return

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot locked by admin. Try later.")
        return

    if user_id not in active_users:
        active_users.add(user_id)

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    
    if user_id == OWNER_ID: user_status = "👑 Owner"
    elif user_id in admin_ids: user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"
        else: user_status = "🆓 Free User"
    else: user_status = "🆓 Free User"

    welcome_msg_text = (f"〽️ Welcome, {message.from_user.first_name}!\n\n🆔 Your User ID: `{user_id}`\n"
                        f"🔰 Your Status: {user_status}\n"
                        f"📁 Files Uploaded: {current_files} / {limit_str}\n\n"
                        f"🤖 Host & run Python (`.py`) or JS (`.js`) scripts.\n"
                        f"👇 Use buttons or type commands.")
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked by admin, cannot accept files.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached. Delete files first.")
        return
    bot.reply_to(message, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    
    if not user_files_list:
        bot.reply_to(message, "📂 Your files:\n\n(No files uploaded yet)")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        f_hash = get_short_hash(file_name)
        cb_data = f'file_{user_id}_{f_hash}'
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=cb_data))
        
    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
    bot.reply_to(message, "📂 Your files:\nClick to manage.", reply_markup=markup, parse_mode='Markdown')

# ============================================
# BOT MESSAGE HANDLERS
# ============================================
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message): _logic_send_welcome(message)

@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not is_user_joined(user_id):
        bot.reply_to(message, "⛔ **Access Denied!**\nFile upload karne ke liye Channels join karein.", reply_markup=get_fsub_markup())
        return

    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked, cannot accept files.")
        return

    doc = message.document
    file_name = doc.file_name
    if not file_name: 
        bot.reply_to(message, "⚠️ No file name."); return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Unsupported type! Only `.py`, `.js`, `.zip` allowed.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached.")
        return

    try:
        download_wait_msg = bot.reply_to(message, f"⏳ Downloading `{file_name}`...")
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)
        bot.edit_message_text(f"✅ Downloaded `{file_name}`. Processing...", chat_id, download_wait_msg.message_id)
        
        user_folder = get_user_folder(user_id)
        if file_ext == '.zip':
            handle_zip_file(downloaded_file_content, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f: f.write(downloaded_file_content)
            save_user_file(user_id, file_name, file_ext[1:])
            bot.reply_to(message, f"✅ File saved! Starting `{file_name}`...")
            threading.Thread(target=run_script, args=(file_path, user_id, user_folder, file_name, message)).start()

    except Exception as e:
        logger.error(f"❌ Error handling file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ============================================
# BUTTON HANDLERS
# ============================================
BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": lambda m: bot.reply_to(m, f"Updates: {UPDATE_CHANNEL}"),
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": lambda m: bot.reply_to(m, "⚡ Bot is running fast!"),
    "📞 Contact Owner": lambda m: bot.reply_to(m, f"Contact: @{YOUR_USERNAME}"),
    "📊 Statistics": lambda m: bot.reply_to(m, f"📊 Stats:\nUsers: {len(active_users)}\nFiles: {sum(len(f) for f in user_files.values())}"),
    "ℹ️ Help & Guide": lambda m: bot.reply_to(m, "🤖 How to use:\n1. Send .py/.js file\n2. Bot will run it\n3. Use /checkfiles to manage"),
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    if not is_user_joined(message.from_user.id):
        bot.reply_to(message, "⛔ **Access Denied!**\nPehle Channels join karein.", reply_markup=get_fsub_markup())
        return
    logic_func = BUTTON_TEXT_TO_LOGIC.get(message.text)
    if logic_func: logic_func(message)

# ============================================
# CALLBACK HANDLERS
# ============================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    data = call.data
    
    if data == 'verify_join':
        if is_user_joined(call.from_user.id):
            bot.answer_callback_query(call.id, "✅ Verified!")
            _logic_send_welcome(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ Join Channels First!", show_alert=True)
        return
    
    elif data == 'back_to_main':
        bot.answer_callback_query(call.id)
        bot.edit_message_text("〽️ Main Menu", call.message.chat.id, call.message.message_id)
    
    elif data.startswith('file_'):
        try:
            _, user_id_str, f_hash = data.split('_', 2)
            user_id = int(user_id_str)
            file_name = get_file_name_from_hash(user_id, f_hash)
            if file_name:
                is_running = is_bot_running(user_id, file_name)
                markup = types.InlineKeyboardMarkup(row_width=2)
                if is_running:
                    markup.row(
                        types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{user_id}_{f_hash}'),
                        types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{user_id}_{f_hash}')
                    )
                else:
                    markup.row(
                        types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{user_id}_{f_hash}'),
                        types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{user_id}_{f_hash}')
                    )
                markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='check_files'))
                bot.edit_message_text(f"⚙️ Controls: `{file_name}`", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        except: pass

# ============================================
# CLEANUP AND RESTART
# ============================================
def cleanup():
    logger.warning("Shutdown. Cleaning up processes...")
    for key in list(bot_scripts.keys()):
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
    logger.warning("Cleanup finished.")

atexit.register(cleanup)

def restart_program():
    print("♻️ Restarting bot in 5 seconds...")
    time.sleep(5)
    python = sys.executable
    os.execl(python, python, *sys.argv)

# ============================================
# MAIN EXECUTION
# ============================================
if __name__ == '__main__':
    print("🤖 Bot Starting Up...")
    
    # Start Flask server
    try:
        keep_alive()
        print("✅ Flask Server Started.")
    except Exception as e:
        print(f"⚠️ Flask Error: {e}")
    
    # Load data
    try:
        load_data_from_mongo()
        print("✅ Data loaded successfully.")
    except Exception as e:
        print(f"⚠️ Database Error: {e}")
    
    print("🚀 Starting Bot Polling...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print(f"💥 Bot Error: {e}")
            if "409" in str(e):
                print("⚠️ Conflict Error! Waiting 15s...")
                time.sleep(15)
            else:
                restart_program()
        except KeyboardInterrupt:
            print("🛑 Bot stopped by user.")
            sys.exit()