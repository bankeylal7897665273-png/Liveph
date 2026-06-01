import os
import json
import requests
import sys
from io import StringIO
from flask import Flask, request, Response

app = Flask(__name__)

FIREBASE_DB_URL = "https://earning-a9b0c-default-rtdb.firebaseio.com"

# Firebase Utilities
def firebase_get(path):
    r = requests.get(f"{FIREBASE_DB_URL}/{path}.json")
    return r.json()

def firebase_set(path, data):
    requests.put(f"{FIREBASE_DB_URL}/{path}.json", json=data)

def firebase_delete(path):
    requests.delete(f"{FIREBASE_DB_URL}/{path}.json")

def get_settings():
    settings = firebase_get("settings")
    if settings:
        return settings.get("bot_token"), settings.get("vercel_domain", "")
    return None, ""

def send_message(chat_id, text, reply_markup=None):
    token, _ = get_settings()
    if not token: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)

def download_tg_file(file_id):
    token, _ = get_settings()
    if not token: return ""
    file_info = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}").json()
    if file_info.get("ok"):
        file_path = file_info["result"]["file_path"]
        return requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}").text
    return ""

# 🟢 LIVE EXECUTION AND SITE ROUTER
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

    # Fetching code from Firebase Node Hostingbots_s
    file_content = firebase_get(f"Hostingbots_s/hosted_sites/{domain_name}/files/{filename.replace('.', '_')}")
    if not file_content:
        return f"⚠️ File '{filename}' nahi mili.", 404

    site_meta = firebase_get(f"Hostingbots_s/meta_domains/{domain_name}")
    site_type = site_meta.get("type") if site_meta else "HTML"

    # 🔥 LIVE PYTHON EXECUTION BOX
    if site_type == "PYTHON" and filename.endswith(".py"):
        old_stdout = sys.stdout
        redirected_output = sys.stdout = StringIO()
        try:
            # Dynamic code runner execution
            exec(file_content, {'__name__': '__main__'})
            output = redirected_output.getvalue()
        except Exception as e:
            output = f"❌ Python Runtime Error:\n\n{str(e)}\n\n👉 Fix karne ke liye bot par naya code bhein."
        finally:
            sys.stdout = old_stdout
        return Response(output, mimetype="text/plain")
    
    elif filename.endswith(".html"):
        return Response(file_content, mimetype="text/html")
    else:
        return Response(file_content, mimetype="text/plain")

# 🤖 TELEGRAM BOT WEBHOOK API
@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if not update: return "OK", 200

    message = update.get("message", {})
    callback_query = update.get("callback_query", {})

    if callback_query:
        chat_id = callback_query["message"]["chat"]["id"]
        data = callback_query["data"]
        
        if data in ["host_html", "host_python"]:
            h_type = "HTML" if data == "host_html" else "PYTHON"
            firebase_set(f"Hostingbots_s/{chat_id}/state", "uploading")
            firebase_set(f"Hostingbots_s/{chat_id}/hosting_type", h_type)
            firebase_set(f"Hostingbots_s/{chat_id}/temp_files", {})
            send_message(chat_id, f"✅ <b>{h_type} HOSTING SELECTED</b>\n\n📂 <b>UPLOAD ALL FILES:</b>\nApni files bhejna shuru karein.")

        elif data == "submit_files":
            firebase_set(f"Hostingbots_s/{chat_id}/state", "awaiting_domain")
            send_message(chat_id, "✅ Files received!\n\n🌐 Ab apna unique <b>DOMAIN NAME / USERFOLDERNAME</b> bhejiye:")

        elif data.startswith("edit_"):
            domain = data.replace("edit_", "")
            site_data = firebase_get(f"Hostingbots_s/hosted_sites/{domain}")
            files = site_data.get("files", {}) if site_data else {}
            
            file_list = "\n".join([f"📄 {f.replace('_', '.')}" for f in files.keys()])
            firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
            
            msg = f"🛠 <b>MANAGE SITE: {domain}</b>\n\n"
            msg += f"📊 <b>Total Files:</b> {len(files)}\n"
            msg += f"📁 <b>Files List:</b>\n{file_list}\n\n"
            msg += "👉 <i>Delete ke liye bheje:</i> <code>filename.py/delete</code>\n"
            msg += "👉 <i>Add/Fix code ke liye bheje:</i> <code>filename/add</code>"
            send_message(chat_id, msg)

        return "OK", 200

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    document = message.get("document", {})

    if not chat_id: return "OK", 200

    user_state = firebase_get(f"Hostingbots_s/{chat_id}/state") or "idle"
    user_type = firebase_get(f"Hostingbots_s/{chat_id}/hosting_type") or "HTML"

    if text == "/start":
        firebase_set(f"Hostingbots_s/{chat_id}/state", "start")
        msg = "🌟 <b>WELCOME TO SMART VERCEL HOSTING BOT</b> 🌟\n\nSelect kijiye aapko konsi hosting karni hai:"
        markup = {
            "inline_keyboard": [
                [{"text": "🌐 HOSTING HTML", "callback_data": "host_html"}],
                [{"text": "🐍 HOSTING PYTHON", "callback_data": "host_python"}]
            ]
        }
        send_message(chat_id, msg, markup)
        return "OK", 200

    if text.lower() in ["history", "/history"]:
        user_sites = firebase_get("Hostingbots_s/meta_domains") or {}
        found = False
        for dom, meta in user_sites.items():
            if meta.get("owner") == chat_id:
                found = True
                _, vercel_domain = get_settings()
                site_detail = firebase_get(f"Hostingbots_s/hosted_sites/{dom}")
                f_count = len(site_detail.get("files", {})) if site_detail else 0
                
                msg = f"🌐 <b>URL:</b> {vercel_domain}/site/{dom}\n🗂 <b>Domain:</b> {dom}\n📊 <b>Total Files:</b> {f_count}"
                markup = {"inline_keyboard": [[{"text": f"✏️ EDIT {dom}", "callback_data": f"edit_{dom}"}]]}
                send_message(chat_id, msg, markup)
        if not found:
            send_message(chat_id, "⚠️ Aapki koi history nahi mili.")
        return "OK", 200

    if user_state == "uploading" and document:
        f_name = document.get("file_name", "")
        f_id = document.get("file_id", "")
        ext = f_name.split(".")[-1].lower() if "." in f_name else ""

        if user_type == "HTML" and ext == "py":
            send_message(chat_id, "⚠️ PLEASE BACK AND CLICK PYTHON HOSTING\nAapne HTML hosting select ki thi par Python file de rahe hain.")
            return "OK", 200

        code_content = download_tg_file(f_id)
        firebase_set(f"Hostingbots_s/{chat_id}/temp_files/{f_name.replace('.', '_')}", code_content)
        
        markup = {"inline_keyboard": [[{"text": "✅ SUBMIT", "callback_data": "submit_files"}]]}
        send_message(chat_id, "OK 👍\nAgar aapko aur file iske sath upload karni hai toh karein, nahi toh SUBMIT par click karein.", markup)
        return "OK", 200

    if user_state == "awaiting_domain" and text:
        domain_name = text.strip().replace(" ", "_")
        temp_files = firebase_get(f"Hostingbots_s/{chat_id}/temp_files")

        if not temp_files:
            send_message(chat_id, "⚠️ Files missing! Please restart with /start")
            return "OK", 200

        firebase_set(f"Hostingbots_s/hosted_sites/{domain_name}/files", temp_files)
        firebase_set(f"Hostingbots_s/meta_domains/{domain_name}", {"owner": chat_id, "type": user_type})
        firebase_delete(f"Hostingbots_s/{chat_id}/temp_files")
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")

        _, vercel_domain = get_settings()
        send_message(chat_id, f"🎉 <b>HOSTING SUCCESSFUL!</b>\n\n🔗 <b>URL:</b> {vercel_domain}/site/{domain_name}")
        return "OK", 200

    if user_state.startswith("managing_") and text:
        domain = user_state.replace("managing_", "")
        
        if text.lower().endswith("/delete"):
            f_to_del = text.split("/")[0].replace(".", "_")
            if firebase_get(f"Hostingbots_s/hosted_sites/{domain}/files/{f_to_del}"):
                firebase_delete(f"Hostingbots_s/hosted_sites/{domain}/files/{f_to_del}")
                markup = {"keyboard": [[{"text": "UPDATE"}, {"text": "CANCEL"}]], "resize_keyboard": True, "one_time_keyboard": True}
                send_message(chat_id, f"OK ✅\nFile <b>{text.split('/')[0]}</b> deleted.\nClick UPDATE to save.", markup)
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
            send_message(chat_id, f"📝 <b>PASTE CODE NOW</b>\nYa phir <code>{f_to_add}</code> naam ki same file upload karein. Bot code update kar dega.")
            return "OK", 200

    if user_state.startswith("adding_file|"):
        _, domain, target_file = user_state.split("|")
        content = download_tg_file(document.get("file_id")) if document else text
        
        firebase_set(f"Hostingbots_s/hosted_sites/{domain}/files/{target_file.replace('.', '_')}", content)
        firebase_set(f"Hostingbots_s/{chat_id}/state", f"managing_{domain}")
        send_message(chat_id, f"✅ File <b>{target_file}</b> successfully updated/added in {domain}!")
        return "OK", 200

    if text in ["UPDATE", "CANCEL"]:
        firebase_set(f"Hostingbots_s/{chat_id}/state", "idle")
        send_message(chat_id, "✅ Done! Status updated successfully.", {"remove_keyboard": True})
        return "OK", 200

    return "OK", 200
