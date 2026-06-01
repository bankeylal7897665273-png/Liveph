import os
import json
import requests
import sys
import tempfile
import subprocess
import shutil
from flask import Flask, request, Response

app = Flask(__name__)

FIREBASE_DB_URL = "https://earning-a9b0c-default-rtdb.firebaseio.com"

# Global dictionary to keep track of running background bots
if 'running_bots' not in globals():
    running_bots = {}

# ==========================================
# ULTRA FAST MEMORY CACHING & DB UTILS
# ==========================================
def firebase_get(path):
    try:
        r = requests.get(f"{FIREBASE_DB_URL}/{path}.json", timeout=5)
        return r.json()
    except:
        return None

def firebase_set(path, data):
    try:
        requests.put(f"{FIREBASE_DB_URL}/{path}.json", json=data, timeout=5)
    except:
        pass

def firebase_delete(path):
    try:
        requests.delete(f"{FIREBASE_DB_URL}/{path}.json", timeout=5)
    except:
        pass

def get_settings():
    settings = firebase_get("settings")
    if settings:
        return settings.get("bot_token"), settings.get("vercel_domain", "")
    return None, ""

# Path Encoder/Decoder to keep Firebase keys clean
def enc_p(path):
    return path.replace('/', '---').replace('.', '___')

def dec_p(path):
    return path.replace('---', '/').replace('___', '.')

# ==========================================
# SUPER FAST TELEGRAM REPLIES
# ==========================================
def send_message(chat_id, text, reply_markup=None):
    token, _ = get_settings()
    if not token: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=4)
    except:
        pass

def download_tg_file(file_id):
    token, _ = get_settings()
    if not token: return ""
    try:
        file_info = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}", timeout=4).json()
        if file_info.get("ok"):
            file_path = file_info["result"]["file_path"]
            return requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=5).text
    except:
        pass
    return ""

# Keyboards
main_keyboard = {
    "keyboard": [
        [{"text": "🌐 HOSTING HTML"}, {"text": "🐍 HOSTING PYTHON"}],
        [{"text": "📊 TOTAL LIST"}]
    ],
    "resize_keyboard": True
}

upload_keyboard = {
    "keyboard": [
        [{"text": "📤 SUBMIT FILES"}],
        [{"text": "🔙 BACK"}]
    ],
    "resize_keyboard": True
}

run_keyboard = {
    "keyboard": [
        [{"text": "🚀 RUN"}],
        [{"text": "🔙 BACK"}]
    ],
    "resize_keyboard": True
}

# ==========================================
# 🟢 LIVE PERSISTENT BACKGROUND ENGINE 
# ==========================================
@app.route('/site/<domain_name>', defaults={'filename': 'index'})
@app.route('/site/<domain_name>/<path:filename>')
def serve_user_site(domain_name, filename):
    global running_bots
    
    site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain_name}")
    if not site_meta:
        return "⚠️ Domain Not Found!", 404

    site_type = site_meta.get("type", "HTML")
    all_files = firebase_get(f"Hostingbots_s/hosted_sites/{domain_name}/files")
    if not all_files:
        return "⚠️ Domain par koi files nahi mili.", 404

    # Direct Routing for HTML Sites
    if site_type == "HTML":
        if "." not in filename:
            filename += ".html"
        target_enc = enc_p(filename)
        file_content = all_files.get(target_enc)
        if not file_content:
            return f"⚠️ File '{filename}' nahi mili.", 404
        if filename.endswith((".html", ".htm")):
            return Response(file_content, mimetype="text/html")
        return Response(file_content, mimetype="text/plain")

    # 🔥 PYTHON PERSISTENT RUNNER (With Auto-Requirements Installer)
    if site_type == "PYTHON":
        # Check if already running live in background
        if domain_name in running_bots:
            proc = running_bots[domain_name]
            if proc.poll() is None:  # Process is still alive and handling loops
                return f"🤖 Bot is already running live 24/7 in background!\n\nStatus: Active ✅\n\nLogs dekhne ke liye Telegram par 'LOGOS' button dabayein."

        # Create unique directory structure for execution
        tmp_dir = os.path.join(tempfile.gettempdir(), f"site_{domain_name}")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)

        main_py_file = None
        has_requirements = False

        # Recreate original file/folder architecture
        for enc_name, file_content in all_files.items():
            dec_name = dec_p(enc_name)
            file_path = os.path.join(tmp_dir, dec_name)
            
            # Make directories if file is inside a folder
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)

            if dec_name == "requirements.txt":
                has_requirements = True
            if dec_name.endswith(".py"):
                if dec_name.startswith("index") or not main_py_file:
                    main_py_file = file_path

        if not main_py_file:
            return "❌ No executable Python (.py) file found in structure.", 400

        # Dynamic Pip Installer Block
        if has_requirements:
            req_path = os.path.join(tmp_dir, "requirements.txt")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], capture_output=True)

        # Launch Bot Process inside Background safely without thread blocking
        log_file_path = os.path.join(tmp_dir, "output.log")
        log_file = open(log_file_path, "w", encoding="utf-8")

        proc = subprocess.Popen(
            [sys.executable, main_py_file],
            cwd=tmp_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Save process instance to avoid duplicate triggers
        running_bots[domain_name] = proc
        
        return f"🚀 <b>FAST B2K BACKGROUND ENGINE DEPLOYED!</b>\n\nBot successfully executed using isolated environment.\n\nMain Script: {os.path.basename(main_py_file)}\nRequirements: {'Installed Automatically' if has_requirements else 'None'}\n\n👉 Ab aap is link ko band kar sakte hain, aapka bot background me bina tute chalta rahega!"

# ==========================================
# 🤖 BOT WEBHOOK CONTROLLER
# ==========================================
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if not update: return "OK", 200

    message = update.get("message", {})
    callback_query = update.get("callback_query", {})

    # INLINE CALLBACKS
    if callback_query:
        chat_id = callback_query["message"]["chat"]["id"]
        data = callback_query["data"]
        
        if data.startswith("edit_"):
            domain = data.replace("edit_", "")
            site_data = firebase_get(f"Hostingbots_s/hosted_sites/{domain}")
            files = site_data.get("files", {}) if site_data else {}
            
            file_list = "\n".join([f"📄 {dec_p(f)}" for f in files.keys()])
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
            
            msg = f"🛠 <b>MANAGE: {domain}</b>\n\n"
            msg += f"<b>Total Files:</b> {len(files)}\n"
            msg += f"<b>Files:</b>\n{file_list}\n\n"
            msg += "👉 <i>Delete:</i> <code>filename.ext/delete</code>\n"
            msg += "👉 <i>Add:</i> <code>filename/add</code> (Ya folder/filename/add)\n"
            msg += "👉 <i>Edit:</i> <code>filename/edit</code>"
            
            markup = {"inline_keyboard": [[{"text": "📁 CREATE FOLDER", "callback_data": "create_folder"}]]}
            send_message(chat_id, msg, run_keyboard)
            send_message(chat_id, "Action choose karein:", markup)

        elif data == "create_folder":
            msg = "📁 <b>Naya Folder Banane Ke Liye:</b>\n\nBas folder ka naam aur last me '/' lagakar bhejein.\nJaise: <code>MyFolder/</code>"
            send_message(chat_id, msg)

        elif data == "rename_file":
            user_state = firebase_get(f"Hostingbots_s/{chat_id}/state") or ""
            if user_state.startswith("editing_file|"):
                _, domain, enc_fpath = user_state.split("|")
                firebase_set(f"Hostingbots_s/{chat_id}/state", f"renaming_file|{domain}|{enc_fpath}")
                send_message(chat_id, "📝 <b>Apna naya file name bhejein:</b>\nJaise: <code>newname.py</code>")

        elif data.startswith("logs_"):
            domain = data.replace("logs_", "")
            log_path = os.path.join(tempfile.gettempdir(), f"site_{domain}", "output.log")
            
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as lf:
                    logs = lf.read()[-3800:]  # Fetch live process buffer logs
            else:
                logs = "Abhi tak koi process logs store nahi hua hai. Live link ko ek baar click karke boot karein."
                
            send_message(chat_id, f"📝 <b>LIVE ENGINE RECAP: {domain}</b>\n\n<code>{logs}</code>")

        return "OK", 200

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    document = message.get("document", {})

    if not chat_id: return "OK", 200

    user_state = firebase_get(f"Hostingbots_s/{chat_id}/state") or "idle"
    user_type = firebase_get(f"Hostingbots_s/{chat_id}/hosting_type") or "HTML"

    # Universal BACK & START
    if "BACK" in text or "back" in text.lower() or "🔙" in text or text == "/start":
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")
        firebase_delete(f"Hostingbots_s/{chat_id}/temp_files")
        msg = "🌟 <b>WELCOME TO FAST B2K  HOSTING BOT</b> 🌟\n\nKripya niche diye gaye keyboard se option select karein:"
        send_message(chat_id, msg, main_keyboard)
        return "OK", 200

    if "RUN" in text or "run" in text.lower() or "🚀" in text:
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")
        send_message(chat_id, "🚀 <b>All Changes Executed & Live!</b> Panel ready.", main_keyboard)
        return "OK", 200

    # Options
    if "HOSTING HTML" in text:
        firebase_set(f"Hostingbots_s/{chat_id}/state", "uploading_html")
        firebase_set(f"Hostingbots_s/{chat_id}/hosting_type", "HTML")
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {})
        send_message(chat_id, "✅ <b>HTML HOSTING SELECTED</b>\n\n📂 Apni files bhejein ya direct <b>SUBMIT FILES</b> dabayein.", upload_keyboard)
        return "OK", 200

    if "HOSTING PYTHON" in text:
        firebase_set(f"Hostingbots_s/{chat_id}/state", "uploading_python")
        firebase_set(f"Hostingbots_s/{chat_id}/hosting_type", "PYTHON")
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {})
        send_message(chat_id, "🐍 <b>PYTHON HOSTING SELECTED</b>\n\n📂 Apni Python/Requirements files bhejein.", upload_keyboard)
        return "OK", 200

    if "TOTAL LIST" in text:
        user_sites = firebase_get("Hostingbots_s/meta_domains") or {}
        found = False
        _, render_domain = get_settings()
        
        for dom, meta in user_sites.items():
            if meta.get("owner") == chat_id:
                found = True
                site_detail = firebase_get(f"Hostingbots_s/hosted_sites/{dom}")
                f_count = len(site_detail.get("files", {})) if site_detail else 0
                s_type = meta.get("type", "HTML")
                
                msg = f"🌐 <b>URL:</b> {render_domain}/site/{dom}\n"
                msg += f"📊 <b>Total File:</b> {f_count}\n"
                msg += f"🗂 <b>Domain Name:</b> {dom}\n"
                msg += f"⚙️ <b>Type:</b> {s_type}"
                
                buttons = [[{"text": f"✏️ EDIT", "callback_data": f"edit_{dom}"}]]
                if s_type == "PYTHON":
                    buttons[0].append({"text": "📜 LOGOS", "callback_data": f"logs_{dom}"})
                
                send_message(chat_id, msg, {"inline_keyboard": buttons})
                
        if not found:
            send_message(chat_id, "Abhi tak aapne koi file host nahi ki hai.", main_keyboard)
        return "OK", 200

    # Multi-upload Flow
    if user_state in ["uploading_html", "uploading_python"] and document:
        f_name = document.get("file_name", "")
        if f_name.split(".")[-1].lower() == "php":
            send_message(chat_id, "PLEASE UPLOAD HTML AUR PYTHON FILES OK NO UPLOAD PHPS")
            return "OK", 200

        code_content = download_tg_file(document.get("file_id"))
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files/{enc_p(f_name)}", code_content)
        send_message(chat_id, f"⚡ Received: <b>{f_name}</b>\nAur files bhejein ya 'SUBMIT FILES' par click karein.")
        return "OK", 200

    if "SUBMIT FILES" in text and user_state in ["uploading_html", "uploading_python"]:
        temp_files = firebase_get(f"Hostingbots_s/{chat_id}/temp_files") or {"dummy": ""}
        if "dummy" in temp_files: temp_files = {}
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files", temp_files)
        firebase_set(f"Hostingbots_s/{chat_id}/state", "awaiting_domain")
        send_message(chat_id, "📂 Files mapped!\n\n🌐 Ab apna Unique <b>DOMAIN NAME</b> bhejiye:", run_keyboard)
        return "OK", 200

    if user_state == "awaiting_domain" and text:
        domain_name = text.strip().replace(" ", "_")
        temp_files = firebase_get(f"Hostingbots_s/{chat_id}/temp_files") or {}

        firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/files", temp_files)
        firebase_set(f"Hostingbots_s/meta_domains/{domain_name}", {"owner": chat_id, "type": user_type})
        firebase_delete(f"Hostingbots_s/{chat_id}/temp_files")
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")

        _, render_domain = get_settings()
        send_message(chat_id, f"🎉 <b>HOSTING SUCCESSFUL!</b>\n\n🔗 <b>URL:</b> {render_domain}/site/{domain_name}", main_keyboard)
        return "OK", 200

    # Manage Structural Logic
    if user_state.startswith("managing_") and text:
        domain = user_state.replace("managing_", "")
        
        # 1. Create Folder
        if text.endswith("/"):
            send_message(chat_id, f"✅ Folder <b>{text}</b> ready!\n\nAb file banane ke liye bhejein: <code>{text}filename.py/add</code>", run_keyboard)
            return "OK", 200

        # 2. Delete
        if text.lower().endswith("/delete"):
            f_to_del = text[:-7]
            enc_del = enc_p(f_to_del)
            if firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{enc_del}") is not None:
                firebase_delete(f"Hostingbots_s/hosted_sites/{domain}/files/{enc_del}")
                
                # Check if running to stop process and trigger clean restart on next load
                if domain in running_bots:
                    try: running_bots[domain].terminate()
                    except: pass
                    del running_bots[domain]
                    
                msg = "Kya aap aur file delete ya add krna hi to command dal ke file delete ya add karo ager kucch nahe krna to click RUN boton"
                send_message(chat_id, f"✅ File <b>{f_to_del}</b> deleted.\n\n" + msg, run_keyboard)
            else:
                send_message(chat_id, "⚠️ File nahi mili.")
            return "OK", 200

        # 3. Add
        if text.lower().endswith("/add"):
            f_to_add = text[:-4]
            if "." not in f_to_add.split("/")[-1]:
                site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain}")
                ext = ".py" if site_meta.get("type") == "PYTHON" else ".html"
                f_to_add += ext
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"adding_file|{domain}|{enc_p(f_to_add)}")
            send_message(chat_id, f"📝 <b>PASTE CODE NOW</b>\nYa phir direct <code>{f_to_add}</code> file upload karein.")
            return "OK", 200

        # 4. Edit
        if text.lower().endswith("/edit"):
            f_to_edit = text[:-5]
            enc_edit = enc_p(f_to_edit)
            content = firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{enc_edit}")
            if content is not None:
                firebase_set(f"Hostingbots_s/{chat_id}/state", f"editing_file|{domain}|{enc_edit}")
                msg = f"📄 <b>File:</b> {f_to_edit}\n\n<code>{content[:3800]}</code>\n\n📝 Naya code bhejein ya file upload karein."
                markup = {"inline_keyboard": [[{"text": "✏️ CHANGE FILE NAME", "callback_data": "rename_file"}]]}
                send_message(chat_id, msg, markup)
            else:
                send_message(chat_id, "⚠️ File nahi mili.")
            return "OK", 200

    # Rename File System
    if user_state.startswith("renaming_file|") and text:
        _, domain, old_enc = user_state.split("|")
        new_enc = enc_p(text)
        old_content = firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{old_enc}")
        if old_content is not None:
            firebase_set(f"Hostingbots_s/hosted_sites/{domain}/files/{new_enc}", old_content)
            firebase_delete(f"Hostingbots_s/hosted_sites/{domain}/files/{old_enc}")
            if domain in running_bots:
                try: running_bots[domain].terminate()
                except: pass
                del running_bots[domain]
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
            send_message(chat_id, "✅ YOUR FILE NAME CHINGE OK", run_keyboard)
        return "OK", 200

    # Write Content Data (Add/Edit save hook)
    if user_state.startswith("adding_file|") or user_state.startswith("editing_file|"):
        _, domain, target_enc = user_state.split("|")
        content = download_tg_file(document.get("file_id")) if document else text
        
        firebase_set(f"Hostingbots_s/hosted_sites/{domain}/files/{target_enc}", content)
        
        # Kill old background worker to allow clean engine restart with new code updates
        if domain in running_bots:
            try: running_bots[domain].terminate()
            except: pass
            del running_bots[domain]
            
        firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
        msg = "✅ <b>Action Successful!</b>\n\nKya aap aur file delete ya add krna hi to command dal ke file delete ya add karo ager kucch nahe krna to click RUN boton"
        send_message(chat_id, msg, run_keyboard)
        return "OK", 200

    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
