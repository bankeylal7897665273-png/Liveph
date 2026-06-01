import os
import json
import requests
import sys
import tempfile
import subprocess
from io import StringIO
from flask import Flask, request, Response

app = Flask(__name__)

FIREBASE_DB_URL = "https://earning-a9b0c-default-rtdb.firebaseio.com"

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

# --- FOLDER & FILE PATH ENCODING HACK ---
# Firebase me '/' aur '.' allow nahi hota, isliye hum isko encode kar rahe hain
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

# ==========================================
# KEYBOARDS WITH EMOJIS & BACK BUTTONS
# ==========================================
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
# 🟢 LIVE ENGINE ROUTER (EVENT LOOP FIXED)
# ==========================================
@app.route('/site/<domain_name>', defaults={'filename': 'index'})
@app.route('/site/<domain_name>/<path:filename>')
def serve_user_site(domain_name, filename):
    site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain_name}")
    if not site_meta:
        return "⚠️ Domain Not Found!", 404

    site_type = site_meta.get("type", "HTML")
    
    if "." not in filename:
        ext = ".py" if site_type == "PYTHON" else ".html"
        filename += ext

    all_files = firebase_get(f"Hostingbots_s/hosted_sites/{domain_name}/files")
    if not all_files:
        return "⚠️ Koi file nahi mili. Panel se files add karein.", 404

    target_enc = enc_p(filename)
    file_content = all_files.get(target_enc)
    
    # Auto-detect fallback
    if not file_content and filename.startswith("index"):
        target_ext = "___py" if site_type == "PYTHON" else "___html"
        for f_name, f_content in all_files.items():
            if f_name.endswith(target_ext):
                filename = dec_p(f_name)
                file_content = f_content
                break

    if not file_content:
        return f"⚠️ File '{filename}' nahi mili. URL check karein.", 404

    # 🔥 PYTHON ISOLATED EXECUTION (Fixes Event Loop Is Closed Error)
    if site_type == "PYTHON" and filename.endswith(".py"):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tf:
                tf.write(file_content)
                temp_path = tf.name
            
            # Run code in completely new async-safe process
            result = subprocess.run([sys.executable, temp_path], capture_output=True, text=True, timeout=30)
            output = result.stdout
            if result.stderr:
                output += f"\n❌ Errors:\n{result.stderr}"
            
            os.remove(temp_path)
            firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/logs", output)
        except subprocess.TimeoutExpired:
            output = "❌ Python execution took too long (> 30s). Process killed."
            firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/logs", output)
        except Exception as e:
            output = f"❌ Python Runtime Error:\n\n{str(e)}"
            firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/logs", output)
            
        return Response(output, mimetype="text/plain")
    
    elif filename.endswith((".html", ".htm")):
        return Response(file_content, mimetype="text/html")
    else:
        return Response(file_content, mimetype="text/plain")

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
                send_message(chat_id, "📝 <b>Apna naya file name bhejein:</b>\nJaise: <code>newname.py</code> ya <code>folder/newname.py</code>")

        elif data.startswith("logs_"):
            domain = data.replace("logs_", "")
            logs = firebase_get(f"Hostingbots_s/hosted_sites/{domain}/logs")
            if not logs:
                logs = "Abhi tak koi log nahi bana hai. Live URL par ek baar run karein."
            send_message(chat_id, f"📝 <b>LIVE LOGOS OUTPUT: {domain}</b>\n\n<code>{logs}</code>")

        return "OK", 200

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    document = message.get("document", {})

    if not chat_id: return "OK", 200

    user_state = firebase_get(f"Hostingbots_s/{chat_id}/state") or "idle"
    user_type = firebase_get(f"Hostingbots_s/{chat_id}/hosting_type") or "HTML"

    # Universal BACK & START Button Handler
    if "BACK" in text or "back" in text.lower() or "🔙" in text or text == "/start":
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")
        firebase_delete(f"Hostingbots_s/{chat_id}/temp_files")
        msg = "🌟 <b>WELCOME TO FAST B2K HOSTING BOT</b> 🌟\n\nKripya niche diye gaye keyboard se option select karein:"
        send_message(chat_id, msg, main_keyboard)
        return "OK", 200

    if "RUN" in text or "run" in text.lower():
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")
        send_message(chat_id, "🚀 <b>All Changes Executed & Live!</b> Panel ready.", main_keyboard)
        return "OK", 200

    # Panel Navigation
    if "HOSTING HTML" in text:
        firebase_set(f"Hostingbots_s/{chat_id}/state", "uploading_html")
        firebase_set(f"Hostingbots_s/{chat_id}/hosting_type", "HTML")
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {})
        send_message(chat_id, "✅ <b>HTML HOSTING SELECTED</b>\n\n📂 Apni files bhejein, ya bina upload kiye direct <b>SUBMIT FILES</b> dabayein.", upload_keyboard)
        return "OK", 200

    if "HOSTING PYTHON" in text:
        firebase_set(f"Hostingbots_s/{chat_id}/state", "uploading_python")
        firebase_set(f"Hostingbots_s/{chat_id}/hosting_type", "PYTHON")
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {})
        send_message(chat_id, "🐍 <b>PYTHON HOSTING SELECTED</b>\n\n📂 Apni files bhejein, ya bina upload kiye direct <b>SUBMIT FILES</b> dabayein.", upload_keyboard)
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

    # File Upload Process
    if user_state in ["uploading_html", "uploading_python"] and document:
        f_name = document.get("file_name", "")
        ext = f_name.split(".")[-1].lower() if "." in f_name else ""
        if ext == "php":
            send_message(chat_id, "PLEASE UPLOAD HTML AUR PYTHON FILES OK NO UPLOAD PHPS")
            return "OK", 200

        code_content = download_tg_file(document.get("file_id"))
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files/{enc_p(f_name)}", code_content)
        send_message(chat_id, f"⚡ Received: <b>{f_name}</b>\nAur files bhejein ya 'SUBMIT FILES' par click karein.")
        return "OK", 200

    if "SUBMIT FILES" in text and user_state in ["uploading_html", "uploading_python"]:
        temp_files = firebase_get(f"Hostingbots_s/{chat_id}/temp_files")
        if not temp_files:
            firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {"dummy": ""}) # Create empty template
            
        firebase_set(f"Hostingbots_s/{chat_id}/state", "awaiting_domain")
        send_message(chat_id, "📂 Action Processed!\n\n🌐 Ab apna Unique <b>DOMAIN NAME / FOLDER NAME</b> bhejiye:", run_keyboard)
        return "OK", 200

    if user_state == "awaiting_domain" and text:
        domain_name = text.strip().replace(" ", "_")
        temp_files = firebase_get(f"Hostingbots_s/{chat_id}/temp_files")

        # Clean dummy if user didn't upload files initially
        if "dummy" in temp_files: del temp_files["dummy"]

        firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/files", temp_files)
        firebase_set(f"Hostingbots_s/meta_domains/{domain_name}", {"owner": chat_id, "type": user_type})
        firebase_delete(f"Hostingbots_s/{chat_id}/temp_files")
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")

        _, render_domain = get_settings()
        send_message(chat_id, f"🎉 <b>HOSTING SUCCESSFUL!</b>\n\n🔗 <b>URL:</b> {render_domain}/site/{domain_name}", main_keyboard)
        return "OK", 200

    # ==========================================
    # DYNAMIC FOLDER, ADD, DELETE, EDIT BLOCK
    # ==========================================
    if user_state.startswith("managing_") and text:
        domain = user_state.replace("managing_", "")
        
        # 1. CREATE FOLDER
        if text.endswith("/"):
            folder_name = text.strip()
            msg = f"✅ Folder <b>{folder_name}</b> ready!\n\nAb is folder me file dalne ke liye aise likhein:\n<code>{folder_name}filename.py/add</code>"
            send_message(chat_id, msg, run_keyboard)
            return "OK", 200

        # 2. DELETE FILE
        if text.lower().endswith("/delete"):
            f_to_del = text[:-7] # Remove /delete
            enc_del = enc_p(f_to_del)
            
            if firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{enc_del}") is not None:
                firebase_delete(f"Hostingbots_s/hosted_sites/{domain}/files/{enc_del}")
                msg = "Kya aap aur file delete ya add krna hi to command dal ke file delete ya add karo ager kucch nahe krna to click RUN boton"
                send_message(chat_id, f"✅ File <b>{f_to_del}</b> deleted.\n\n" + msg, run_keyboard)
            else:
                send_message(chat_id, "⚠️ File nahi mili.")
            return "OK", 200

        # 3. ADD FILE
        if text.lower().endswith("/add"):
            f_to_add = text[:-4] # Remove /add
            if "." not in f_to_add.split("/")[-1]:
                site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain}")
                ext = ".py" if site_meta.get("type") == "PYTHON" else ".html"
                f_to_add += ext
            
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"adding_file|{domain}|{enc_p(f_to_add)}")
            send_message(chat_id, f"📝 <b>PASTE CODE NOW</b>\nYa phir direct <code>{f_to_add}</code> ki file upload karein.")
            return "OK", 200

        # 4. EDIT FILE
        if text.lower().endswith("/edit"):
            f_to_edit = text[:-5] # Remove /edit
            enc_edit = enc_p(f_to_edit)
            
            content = firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{enc_edit}")
            if content is not None:
                firebase_set(f"Hostingbots_s/{chat_id}/state", f"editing_file|{domain}|{enc_edit}")
                msg = f"📄 <b>File:</b> {f_to_edit}\n\n<code>{content[:3800]}</code>\n\n📝 Naya code paste karein ya file upload karein edit karne ke liye."
                markup = {"inline_keyboard": [[{"text": "✏️ CHANGE FILE NAME", "callback_data": "rename_file"}]]}
                send_message(chat_id, msg, markup)
            else:
                send_message(chat_id, "⚠️ Ye file mili nahi. Pehle /add karein.")
            return "OK", 200

    # 5. RENAME FILE LOGIC
    if user_state.startswith("renaming_file|") and text:
        _, domain, old_enc = user_state.split("|")
        new_enc = enc_p(text)
        
        old_content = firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{old_enc}")
        if old_content is not None:
            firebase_set(f"Hostingbots_s/hosted_sites/{domain}/files/{new_enc}", old_content)
            firebase_delete(f"Hostingbots_s/hosted_sites/{domain}/files/{old_enc}")
            
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
            send_message(chat_id, "✅ YOUR FILE NAME CHINGE OK", run_keyboard)
        else:
            send_message(chat_id, "⚠️ Error renaming file.", run_keyboard)
        return "OK", 200

    # RECEIVING NEW FILE CONTENT (For Add or Edit)
    if user_state.startswith("adding_file|") or user_state.startswith("editing_file|"):
        _, domain, target_enc = user_state.split("|")
        content = download_tg_file(document.get("file_id")) if document else text
        
        firebase_set(f"Hostingbots_s/hosted_sites/{domain}/files/{target_enc}", content)
        firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
        
        msg = f"✅ <b>Action Successful!</b>\n\nKya aap aur file delete ya add krna hi to command dal ke file delete ya add karo ager kucch nahe krna to click RUN boton"
        send_message(chat_id, msg, run_keyboard)
        return "OK", 200

    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
