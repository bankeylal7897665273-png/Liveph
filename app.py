import os
import json
import requests
import sys
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
        [{"text": "HOSTING HTML"}, {"text": "HOSTING PYTHON"}],
        [{"text": "TOTAL LIST"}]
    ],
    "resize_keyboard": True
}

run_keyboard = {
    "keyboard": [[{"text": "RUN"}]],
    "resize_keyboard": True
}

# ==========================================
# 🟢 LIVE ENGINE ROUTER (HTML & PYTHON RUNNER)
# ==========================================
@app.route('/site/<domain_name>', defaults={'filename': 'index'})
@app.route('/site/<domain_name>/<path:filename>')
def serve_user_site(domain_name, filename):
    if "." not in filename:
        site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain_name}")
        if site_meta:
            ext = ".py" if site_meta.get("type") == "PYTHON" else ".html"
            filename += ext
        else:
            return "⚠️ Domain Not Found!", 404

    file_content = firebase_get(f"Hostingbots_s/hosted_sites/{domain_name}/files/{filename.replace('.', '_')}")
    if not file_content:
        return f"⚠️ File '{filename}' nahi mili.", 404

    site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain_name}")
    site_type = site_meta.get("type") if site_meta else "HTML"

    if site_type == "PYTHON" and filename.endswith(".py"):
        old_stdout = sys.stdout
        redirected_output = sys.stdout = StringIO()
        try:
            exec(file_content, {'__name__': '__main__'})
            output = redirected_output.getvalue()
            firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/logs", output)
        except Exception as e:
            output = f"❌ Python Runtime Error:\n\n{str(e)}"
            firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/logs", output)
        finally:
            sys.stdout = old_stdout
        return Response(output, mimetype="text/plain")
    
    elif filename.endswith(".html"):
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

    # Inline Query Fixes
    if callback_query:
        chat_id = callback_query["message"]["chat"]["id"]
        data = callback_query["data"]
        
        if data.startswith("edit_"):
            domain = data.replace("edit_", "")
            site_data = firebase_get(f"Hostingbots_s/hosted_sites/{domain}")
            files = site_data.get("files", {}) if site_data else {}
            
            file_list = "\n".join([f"📄 {f.replace('_', '.')}" for f in files.keys()])
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
            
            msg = f"🛠 <b>MANAGE: {domain}</b>\n\n"
            msg += f"<b>Total Files:</b> {len(files)}\n"
            msg += f"<b>Files:</b>\n{file_list}\n\n"
            msg += "👉 <i>Delete:</i> <code>filename.ext/delete</code>\n"
            msg += "👉 <i>Add/Edit:</i> <code>filename/add</code> (Ya sidha file bhein)"
            send_message(chat_id, msg, run_keyboard)

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

    if text == "/start":
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")
        firebase_delete(f"Hostingbots_s/{chat_id}/temp_files")
        msg = "🌟 <b>WELCOME TO FAST B2K  HOSTING BOT</b> 🌟\n\nKripya niche diye gaye keyboard se option select karein:"
        send_message(chat_id, msg, main_keyboard)
        return "OK", 200

    if text in ["RUN", "Run", "run"]:
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")
        send_message(chat_id, "🚀 <b>All Changes Executed & Live!</b> Panel ready.", main_keyboard)
        return "OK", 200

    # Panel Navigation
    if text == "HOSTING HTML":
        firebase_set(f"Hostingbots_s/{chat_id}/state", "uploading_html")
        firebase_set(f"Hostingbots_s/{chat_id}/hosting_type", "HTML")
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {})
        kb = {"keyboard": [[{"text": "SUBMIT FILES"}], [{"text": "RUN"}]], "resize_keyboard": True}
        send_message(chat_id, "✅ <b>HTML HOSTING SELECTED</b>\n\n📂 Multi-files (HTML/JS/Config) bhejna shuru karein.", kb)
        return "OK", 200

    if text == "HOSTING PYTHON":
        firebase_set(f"Hostingbots_s/{chat_id}/state", "uploading_python")
        firebase_set(f"Hostingbots_s/{chat_id}/hosting_type", "PYTHON")
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {})
        kb = {"keyboard": [[{"text": "SUBMIT FILES"}], [{"text": "RUN"}]], "resize_keyboard": True}
        send_message(chat_id, "🐍 <b>PYTHON HOSTING SELECTED</b>\n\n📂 Apni Python (.py) aur config files bhein.", kb)
        return "OK", 200

    if text == "TOTAL LIST":
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
                
                markup = {"inline_keyboard": buttons}
                send_message(chat_id, msg, markup)
                
        if not found:
            send_message(chat_id, "Abhi tak aapne koi file host nahi ki hai.", main_keyboard)
        return "OK", 200

    # Initial Multi-upload file management
    if user_state in ["uploading_html", "uploading_python"] and document:
        f_name = document.get("file_name", "")
        ext = f_name.split(".")[-1].lower() if "." in f_name else ""
        if ext == "php":
            send_message(chat_id, "PLEASE UPLOAD HTML AUR PYTHON FILES OK NO UPLOAD PHPS")
            return "OK", 200

        code_content = download_tg_file(document.get("file_id"))
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files/{f_name.replace('.', '_')}", code_content)
        send_message(chat_id, f"⚡ Received: <b>{f_name}</b>\nAur files bhein ya 'SUBMIT FILES' par click karein.")
        return "OK", 200

    if text == "SUBMIT FILES" and user_state in ["uploading_html", "uploading_python"]:
        temp_files = firebase_get(f"Hostingbots_s/{chat_id}/temp_files")
        if not temp_files:
            send_message(chat_id, "⚠️ Files missing! Please upload files.")
            return "OK", 200
        firebase_set(f"Hostingbots_s/{chat_id}/state", "awaiting_domain")
        send_message(chat_id, "📂 Files mapped!\n\n🌐 Ab apna Unique <b>DOMAIN NAME</b> bhejiye:")
        return "OK", 200

    if user_state == "awaiting_domain" and text:
        domain_name = text.strip().replace(" ", "_")
        temp_files = firebase_get(f"Hostingbots_s/{chat_id}/temp_files")

        firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/files", temp_files)
        firebase_set(f"Hostingbots_s/meta_domains/{domain_name}", {"owner": chat_id, "type": user_type})
        firebase_delete(f"Hostingbots_s/{chat_id}/temp_files")
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")

        _, render_domain = get_settings()
        send_message(chat_id, f"🎉 <b>HOSTING SUCCESSFUL!</b>\n\n🔗 <b>URL:</b> {render_domain}/site/{domain_name}", main_keyboard)
        return "OK", 200

    # Dynamic Editing Block: FIXED MULTI-FILE MAP OVERWRITE
    if user_state.startswith("managing_") and text:
        domain = user_state.replace("managing_", "")
        
        if text.lower().endswith("/delete"):
            f_to_del = text.split("/")[0].replace(".", "_")
            if firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{f_to_del}"):
                firebase_delete(f"Hostingbots_s/hosted_sites/{domain}/files/{f_to_del}")
                msg = "Kya aap aur file delete ya add krna hi to comment dal ke file delete ya add karo ager kucch nahe krna to click RUN boton"
                send_message(chat_id, f"✅ File <b>{text.split('/')[0]}</b> deleted.\n\n" + msg, run_keyboard)
            else:
                send_message(chat_id, "⚠️ File nahi mili.")
            return "OK", 200

        if text.lower().endswith("/add"):
            f_to_add = text.split("/")[0]
            if "." not in f_to_add:
                site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain}")
                ext = ".py" if site_meta.get("type") == "PYTHON" else ".html"
                f_to_add += ext
            
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"adding_file|{domain}|{f_to_add}")
            send_message(chat_id, f"📝 <b>PASTE CODE NOW</b>\nYa phir <code>{f_to_add}</code> file upload karein.")
            return "OK", 200

    # Real-time Multi-Append Workflow Fix
    if user_state.startswith("adding_file|"):
        _, domain, target_file = user_state.split("|")
        content = download_tg_file(document.get("file_id")) if document else text
        
        # Micro-response processing message
        send_message(chat_id, "⏳ <i>Uploading file structure... Please wait...</i>")
        
        # Save file directly inside structural map tree to preserve previous array lists
        firebase_set(f"Hostingbots_s/hosted_sites/{domain}/files/{target_file.replace('.', '_')}", content)
        firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
        
        _, render_domain = get_settings()
        live_url = f"{render_domain}/site/{domain}"
        
        msg = f"✅ <b>Successful Add!</b>\n\n🔗 <b>Updated URL:</b> {live_url}\n\nAgar aapko koi aur file add karni hai toh phir se uska name dalkar file upload kar sakte hain, nahi toh <b>RUN</b> button par click karein."
        send_message(chat_id, msg, run_keyboard)
        return "OK", 200

    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
