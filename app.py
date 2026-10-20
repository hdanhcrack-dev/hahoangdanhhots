"""
Zeadx Tool V3.1 - Web Backend
Flask API chạy bot Zalo thật trên server
"""
import os
import json
import time
import threading
import random
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from zlapi import ZaloAPI, ThreadType, Message
from zlapi.models import Mention, MultiMention, MessageStyle, MultiMsgStyle

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# ==================== CONFIG ====================
API_KEY = os.environ.get("ZALO_API_KEY", "api_key")
SECRET_KEY = os.environ.get("ZALO_SECRET_KEY", "secret_key")
COLOR_LIST = ["#DB342E", "#15A85F", "#F27806", "#F7B503", "#FFFFFF", "#000000"]

# ==================== TASK MANAGER ====================
class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()
        self.counter = 0

    def add(self, bot, thread_id, info):
        with self.lock:
            self.counter += 1
            tid = self.counter
            self.tasks[tid] = {
                "bot": bot, "thread_id": thread_id, "info": info,
                "started": datetime.now().strftime("%H:%M:%S"),
                "status": "running"
            }
            return tid

    def stop(self, task_id):
        with self.lock:
            if task_id in self.tasks:
                t = self.tasks[task_id]
                try: t["bot"].running_flag.clear()
                except: pass
                t["status"] = "stopped"
                return t["info"]
            return None

    def stop_all(self):
        with self.lock:
            for t in self.tasks.values():
                try: t["bot"].running_flag.clear()
                except: pass
                t["status"] = "stopped"

    def list(self):
        with self.lock:
            return [{
                "id": tid, "name": t["info"].get("name", "?"),
                "type": t["info"].get("type", "?"),
                "group": t["info"].get("group", "?"),
                "started": t["started"], "status": t["status"]
            } for tid, t in self.tasks.items()]

TM = TaskManager()

# ==================== USER CACHE ====================
USER_CACHE = {}
USER_LOCK = threading.Lock()

def get_user_name(client, uid):
    with USER_LOCK:
        if uid in USER_CACHE: return USER_CACHE[uid]
    try:
        uinfo = client.fetchUserInfo(uid)
        name = uinfo.changed_profiles.get(uid, {}).get('displayName', uid)
    except:
        name = uid
    with USER_LOCK:
        USER_CACHE[uid] = name
    return name

# ==================== BOT CLASSES ====================
class TreongonBot(ZaloAPI):
    def __init__(self, imei, cookies, delay=5, message_text="", font_size=40, color_mode='y'):
        super().__init__(API_KEY, SECRET_KEY, imei, cookies)
        self.delay = delay
        self.message_text = message_text
        self.font_size = font_size
        self.color_mode = color_mode
        self.running_flag = threading.Event()
        self.running_flag.set()

    def spam_messages(self, thread_id, task_name="?"):
        while self.running_flag.is_set():
            try:
                if self.message_text:
                    lines = self.message_text.strip().splitlines()
                    styles, formatted, offset = [], "", 0
                    chosen = random.choice(COLOR_LIST) if self.color_mode == 'n' else None
                    for line in lines:
                        color = random.choice(COLOR_LIST) if self.color_mode == 'y' else chosen
                        line_text = line + "\n"
                        formatted += line_text
                        styles.append(MessageStyle(offset=offset, length=len(line_text),
                                                    style="color", color=color, auto_format=False))
                        styles.append(MessageStyle(offset=offset, length=len(line_text),
                                                    style="font", size=str(self.font_size),
                                                    auto_format=False))
                        offset += len(line_text)
                    self.send(Message(text=formatted, style=MultiMsgStyle(styles)),
                              thread_id=thread_id, thread_type=ThreadType.GROUP)
                time.sleep(self.delay)
            except Exception as e:
                print(f"[Treongon] Error: {e}")
                time.sleep(3)


class TagBot(ZaloAPI):
    def __init__(self, imei, cookies, label="Bot"):
        super().__init__(API_KEY, SECRET_KEY, imei, cookies)
        self.label = label
        self.running_flag = threading.Event()
        self.running_flag.set()

    def fetch_groups(self):
        try:
            all_groups = self.fetchAllGroups()
            out = []
            for gid in all_groups.gridVerMap.keys():
                ginfo = super().fetchGroupInfo(gid)
                gname = ginfo.gridInfoMap.get(gid, {}).get("name", f"Group_{gid}")
                out.append({"id": gid, "name": gname})
            return out
        except Exception as e:
            print(f"[TagBot] fetch_groups error: {e}")
            return []

    def fetch_members(self, group_id):
        try:
            ginfo = super().fetchGroupInfo(group_id)
            mem_ver = ginfo.gridInfoMap.get(group_id, {}).get("memVerList", [])
            ids = [m.split("_")[0] for m in mem_ver]
            return [{"id": uid, "name": get_user_name(self, uid)} for uid in ids]
        except Exception as e:
            print(f"[TagBot] fetch_members error: {e}")
            return []

    def send_tag(self, thread_id, text, user_ids, colored=False):
        try:
            if user_ids == ["@all"]:
                tag = "@All"
                formatted = (text or "").rstrip() + " " + tag
                offset = len(formatted) - len(tag)
                mention = Mention(uid="-1", length=len(tag), offset=offset, auto_format=False)
                if colored:
                    style = MultiMsgStyle([
                        MessageStyle(offset=0, length=len(formatted), style="color",
                                     color=random.choice(COLOR_LIST), auto_format=False),
                        MessageStyle(offset=0, length=len(formatted), style="font",
                                     size="100", auto_format=False),
                    ])
                    self.send(Message(text=formatted, mention=MultiMention([mention]), style=style),
                              thread_id=thread_id, thread_type=ThreadType.GROUP)
                else:
                    self.send(Message(text=formatted, mention=MultiMention([mention])),
                              thread_id=thread_id, thread_type=ThreadType.GROUP)
            else:
                batch_size = 10
                for i in range(0, len(user_ids), batch_size):
                    batch = user_ids[i:i+batch_size]
                    mentions, formatted = [], (text or "").rstrip() + " "
                    for uid in batch:
                        name = get_user_name(self, uid)
                        t = f"@{name}"
                        offset = len(formatted)
                        formatted += t + " "
                        mentions.append(Mention(uid=uid, length=len(t), offset=offset, auto_format=False))
                    if colored:
                        style = MultiMsgStyle([
                            MessageStyle(offset=0, length=len(formatted), style="color",
                                         color=random.choice(COLOR_LIST), auto_format=False),
                            MessageStyle(offset=0, length=len(formatted), style="font",
                                         size="100", auto_format=False),
                        ])
                        self.send(Message(text=formatted, mention=MultiMention(mentions), style=style),
                                  thread_id=thread_id, thread_type=ThreadType.GROUP)
                    else:
                        self.send(Message(text=formatted, mention=MultiMention(mentions)),
                                  thread_id=thread_id, thread_type=ThreadType.GROUP)
                    time.sleep(0.5)
        except Exception as e:
            print(f"[TagBot] send error: {e}")

    def loop_spam(self, thread_id, lines, delay, users, colored=False, task_name="?"):
        while self.running_flag.is_set():
            for line in lines:
                if not self.running_flag.is_set(): break
                self.send_tag(thread_id, line, users, colored)
                time.sleep(delay)

# ==================== API ROUTES ====================

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    return jsonify({"tasks": TM.list()})

@app.route("/api/tasks/<int:tid>", methods=["DELETE"])
def stop_task(tid):
    info = TM.stop(tid)
    if info: return jsonify({"success": True, "task": info})
    return jsonify({"success": False, "error": "Task not found"}), 404

@app.route("/api/tasks/all", methods=["DELETE"])
def stop_all():
    TM.stop_all()
    return jsonify({"success": True})

@app.route("/api/login", methods=["POST"])
def login():
    """Đăng nhập Zalo bằng IMEI + Cookie"""
    data = request.json
    imei = data.get("imei", "").strip()
    cookie_str = data.get("cookie", "").strip()
    if not imei or not cookie_str:
        return jsonify({"success": False, "error": "Thiếu IMEI hoặc Cookie"}), 400
    try:
        cookies = json.loads(cookie_str) if cookie_str.startswith("{") else eval(cookie_str)
        if not isinstance(cookies, dict):
            return jsonify({"success": False, "error": "Cookie phải là dict JSON"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Cookie không hợp lệ: {e}"}), 400

    try:
        bot = TagBot(imei, cookies, "login")
        info = bot.fetchAccountInfo()
        profile = info.profile if hasattr(info, "profile") else {}
        groups = bot.fetch_groups()
        return jsonify({
            "success": True,
            "profile": {
                "name": profile.get("displayName", "Không rõ"),
                "uid": profile.get("userId", "Không rõ"),
                "phone": profile.get("phoneNumber", "Không rõ"),
                "avatar": profile.get("avatar", ""),
            },
            "groups": groups,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Đăng nhập thất bại: {e}"}), 401

@app.route("/api/groups", methods=["POST"])
def get_groups():
    """Lấy danh sách nhóm từ IMEI + Cookie"""
    data = request.json
    try:
        bot = TagBot(data["imei"], data["cookies"], "grp")
        return jsonify({"success": True, "groups": bot.fetch_groups()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/members", methods=["POST"])
def get_members():
    """Lấy thành viên của nhóm"""
    data = request.json
    try:
        bot = TagBot(data["imei"], data["cookies"], "mem")
        return jsonify({"success": True, "members": bot.fetch_members(data["group_id"])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/start/treongon", methods=["POST"])
def start_treongon():
    """Khởi động task Treo Ngôn"""
    data = request.json
    try:
        imei = data["imei"]
        cookies = data["cookies"]
        group_id = data["group_id"]
        group_name = data.get("group_name", group_id)
        message_text = data["message_text"]
        delay = float(data.get("delay", 5))
        font_size = int(data.get("font_size", 40))
        color_mode = data.get("color_mode", "y")

        bot = TreongonBot(imei, cookies, delay, message_text, font_size, color_mode)
        tid = TM.add(bot, group_id, {
            "type": "Treo Ngôn", "group": group_name,
            "name": data.get("task_name", f"Treo Ngôn - {group_name[:20]}")
        })
        threading.Thread(target=bot.spam_messages,
                          args=(group_id, f"Task#{tid}"),
                          daemon=True).start()
        return jsonify({"success": True, "task_id": tid})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/start/tag", methods=["POST"])
def start_tag():
    """Khởi động task Nhây Tag"""
    data = request.json
    try:
        imei = data["imei"]
        cookies = data["cookies"]
        group_id = data["group_id"]
        group_name = data.get("group_name", group_id)
        message_text = data["message_text"]
        delay = float(data.get("delay", 5))
        users = data.get("users", ["@all"])
        colored = data.get("colored", False)

        bot = TagBot(imei, cookies, f"Tag-{group_id[:6]}")
        tid = TM.add(bot, group_id, {
            "type": "Nhây Màu" if colored else "Nhây Thường",
            "group": group_name,
            "name": data.get("task_name", f"Tag - {group_name[:20]}")
        })
        lines = [l.strip() for l in message_text.splitlines() if l.strip()]
        threading.Thread(target=bot.loop_spam,
                          args=(group_id, lines, delay, users, colored, f"Task#{tid}"),
                          daemon=True).start()
        return jsonify({"success": True, "task_id": tid})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# ==================== RUN ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Server running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)