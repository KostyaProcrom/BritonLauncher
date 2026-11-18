import webview
import minecraft_launcher_lib
import subprocess
import threading
import os
import sys
import shutil
import json
import re
import base64
import hmac
import hashlib
import time
import requests
import nbtlib
from nbtlib import Compound, List, String, Byte
import webbrowser
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

CURRENT_VERSION = "3.8.1"
GITHUB_REPO = "KostyaProcrom/BritonLauncher"
UPDATE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

SITE_URL = "https://kostyaprocrom.github.io/BritonLauncher/"
LAUNCHER_SECRET = "577b977f8870b4a173026dc3ca5962300ad353f38cb0a4ba9464b41f4daba6b3"
CODE_TTL_MS = 7 * 24 * 60 * 60 * 1000
ADMIN_NICKS = {"kostyakosmos": "main", "britonlauncher": "admin"}

DEFAULT_REDIRECT = "https://login.microsoftonline.com/common/oauth2/nativeclient"

# ==================== ПУТИ ====================
BASE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), ".britonlauncher"
)
os.makedirs(BASE_DIR, exist_ok=True)
for folder in ["mods", "resourcepacks", "shaderpacks", "custom_menu"]:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

CUSTOM_MENU_PATH = os.path.join(BASE_DIR, "custom_menu", "index.html")
if not os.path.exists(CUSTOM_MENU_PATH):
    default_html = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>body { background: #12060a; color: white; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;}</style></head>
<body>
    <h1>Кастомное меню</h1>
    <p>Отредактируй этот файл в папке .britonlauncher/custom_menu/index.html</p>
</body>
</html>"""
    try:
        with open(CUSTOM_MENU_PATH, "w", encoding="utf-8") as f:
            f.write(default_html)
    except Exception:
        pass

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
NICK_PATH = os.path.join(BASE_DIR, "nickname.txt")
ACCOUNT_PATH = os.path.join(BASE_DIR, "account.json")
OPTIONS_PATH = os.path.join(BASE_DIR, "options.txt")

MENU_PACK_NAME = "BritonMenu.zip"
MENU_PACK_PATH = os.path.join(BASE_DIR, "resourcepacks", MENU_PACK_NAME)


def bundled_asset(*parts):
    """Путь к файлу, вложенному в .exe (PyInstaller) или лежащему рядом с main.py."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _read_options_lines():
    try:
        with open(OPTIONS_PATH, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except Exception:
        return []


def _write_options_lines(lines):
    os.makedirs(os.path.dirname(OPTIONS_PATH), exist_ok=True)
    with open(OPTIONS_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _menu_pack_entry():
    return "file/" + MENU_PACK_NAME


def _menu_pack_enabled():
    entry = _menu_pack_entry()
    for line in _read_options_lines():
        if line.startswith("resourcePacks:"):
            raw = line.split(":", 1)[1].strip()
            try:
                packs = json.loads(raw) if raw else []
            except Exception:
                packs = []
            return isinstance(packs, list) and entry in packs
    return False


def _set_menu_pack_enabled(enabled):
    entry = _menu_pack_entry()
    lines = _read_options_lines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("resourcePacks:"):
            found = True
            raw = line.split(":", 1)[1].strip()
            try:
                packs = json.loads(raw) if raw else []
            except Exception:
                packs = []
            if not isinstance(packs, list):
                packs = []
            packs = [p for p in packs if p != entry]
            if enabled:
                packs.append(entry)
            if not packs:
                packs = ["vanilla"]
            lines[i] = "resourcePacks:" + json.dumps(packs, ensure_ascii=False)
            break
    if not found:
        packs = ["vanilla"] + ([entry] if enabled else [])
        lines.append("resourcePacks:" + json.dumps(packs, ensure_ascii=False))

    # Если пак попал в несовместимые — убираем, чтобы Minecraft его не отключал.
    for i, line in enumerate(lines):
        if line.startswith("incompatibleResourcePacks:"):
            raw = line.split(":", 1)[1].strip()
            try:
                packs = json.loads(raw) if raw else []
            except Exception:
                packs = []
            if isinstance(packs, list) and entry in packs:
                packs = [p for p in packs if p != entry]
                lines[i] = "incompatibleResourcePacks:" + json.dumps(packs, ensure_ascii=False)
            break

    _write_options_lines(lines)

_cfg_lock = threading.RLock()
_ms_lock = threading.Lock()
_ms_pending = {"state": None, "verifier": None}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": f"BritonLauncher/{CURRENT_VERSION}"})


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {"theme": "redsea", "ram": "4G", "nickname": "", "version": "1.20.1",
            "modloader": "Vanilla", "show_console": False, "use_custom_menu": False,
            "client_id": "", "redirect_uri": DEFAULT_REDIRECT, "site_account": {}}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_nickname():
    if os.path.exists(NICK_PATH):
        try:
            with open(NICK_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def save_nickname(nick):
    try:
        with open(NICK_PATH, "w", encoding="utf-8") as f:
            f.write(nick)
    except Exception:
        pass


def load_account():
    if os.path.exists(ACCOUNT_PATH):
        try:
            with open(ACCOUNT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("refresh_token") and data.get("name"):
                    return data
        except Exception:
            pass
    return None


def save_account(acc):
    try:
        with open(ACCOUNT_PATH, "w", encoding="utf-8") as f:
            json.dump(acc, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clear_account():
    try:
        if os.path.exists(ACCOUNT_PATH):
            os.remove(ACCOUNT_PATH)
    except Exception:
        pass


def sanitize_ram(ram):
    """Приводит объём памяти к формату JVM: 4G / 2048M."""
    ram = (ram or "4G").strip().upper().replace(" ", "")
    if ram.isdigit():
        ram += "M"
    if not re.match(r"^\d+[MG]$", ram):
        ram = "4G"
    return ram


# ==================== ВХОД ЧЕРЕЗ САЙТ ====================
def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text):
    text = (text or "").strip()
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def verify_launcher_code(code):
    """Проверяет код с сайта и возвращает данные аккаунта.

    Формат: BLS1.<base64url(json)>.<base64url(HMAC-SHA256)>
    """
    code = (code or "").strip().replace("\n", "").replace("\r", "")
    parts = code.split(".")
    if len(parts) != 3 or parts[0] != "BLS1":
        raise ValueError("Неверный формат кода")

    payload_b64, sig_b64 = parts[1], parts[2]
    expected = hmac.new(
        LAUNCHER_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_b64url_encode(expected), sig_b64):
        raise ValueError("Подпись кода не совпадает")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise ValueError("Код повреждён")

    nick = str(payload.get("n", "")).strip()
    if not re.match(r"^[A-Za-z0-9_]{3,16}$", nick):
        raise ValueError("Некорректный ник в коде")

    issued = int(payload.get("t", 0) or 0)
    if issued <= 0 or int(time.time() * 1000) - issued > CODE_TTL_MS:
        raise ValueError("Код устарел — получи новый на сайте")

    role = payload.get("r") if payload.get("r") in ("admin", "player") else "player"
    fixed = ADMIN_NICKS.get(nick.lower())
    if fixed:
        role = "admin"
    return {
        "nick": nick,
        "role": role,
        "main": fixed == "main",
        "muted": bool(payload.get("mu")),
        "login_at": time.strftime("%d.%m.%Y %H:%M"),
    }


config = load_config()
config.setdefault("theme", "redsea")
config.setdefault("use_custom_menu", False)
config.setdefault("client_id", "")
config.setdefault("redirect_uri", DEFAULT_REDIRECT)
config.setdefault("site_account", {})
_saved_nick = load_nickname()
if _saved_nick:
    config["nickname"] = _saved_nick

account = load_account()

_release_versions = None
_versions_lock = threading.Lock()


def fetch_release_versions_sync():
    global _release_versions
    with _versions_lock:
        if _release_versions is None:
            try:
                all_v = minecraft_launcher_lib.utils.get_version_list()
                rel = [v["id"] for v in all_v if v.get("type") == "release"]
                _release_versions = rel if rel else ["1.20.1"]
            except Exception:
                _release_versions = ["1.20.1"]
        return _release_versions


def add_server_to_list(server_name, server_ip):
    servers_file = os.path.join(BASE_DIR, "servers.dat")
    try:
        if not os.path.exists(servers_file):
            nbt_file = nbtlib.File({"servers": List[Compound]([])})
        else:
            nbt_file = nbtlib.load(servers_file, gzipped=False)
        for srv in nbt_file.get("servers", []):
            try:
                if str(srv["ip"]) == server_ip:
                    return False
            except Exception:
                continue
        nbt_file.setdefault("servers", List[Compound]([]))
        nbt_file["servers"].append(Compound({
            "name": String(server_name), "ip": String(server_ip), "acceptTextures": Byte(1)
        }))
        nbt_file.save(servers_file, gzipped=False)
        return True
    except Exception:
        try:
            nbt_file = nbtlib.File({"servers": List[Compound]([])})
            nbt_file["servers"].append(Compound({
                "name": String(server_name), "ip": String(server_ip), "acceptTextures": Byte(1)
            }))
            nbt_file.save(servers_file, gzipped=False)
        except Exception:
            pass
        return False


def _ver_tuple(v):
    m = re.search(r"(\d+(?:\.\d+)*)", v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def _ms_error_text(e):
    name = type(e).__name__
    if name == "AzureAppNotPermitted":
        return ("Azure App без доступа к Minecraft API. Подай заявку: "
                "https://aka.ms/mce-reviewappid")
    if name == "AccountNotOwnMinecraft":
        return "У аккаунта Microsoft нет купленного Minecraft."
    if name == "InvalidRefreshToken":
        return "Токен истёк. Войди заново."
    return f"{name}: {e}"


class Api:
    def __init__(self):
        self._window = None

    # ---------- служебное ----------
    def _safe_eval(self, js):
        if not self._window:
            return
        try:
            self._window.evaluate_js(js)
        except Exception:
            pass

    def minimize(self):
        try:
            if self._window:
                self._window.minimize()
        except Exception:
            pass

    def maximize(self):
        if not self._window:
            return
        for fn in ("maximize", "toggle_fullscreen"):
            try:
                getattr(self._window, fn)()
                return
            except Exception:
                continue

    def close(self):
        with _cfg_lock:
            save_config(config)
        try:
            if self._window:
                self._window.destroy()
        except Exception:
            pass

    def _set_status(self, text, color="#8b949e", icon="⏳"):
        safe_text = json.dumps(text)
        self._safe_eval(
            f"setStatus({safe_text}, {json.dumps(color)}, {json.dumps(icon)});"
        )

    def get_config(self):
        with _cfg_lock:
            return dict(config)

    def get_versions(self):
        return fetch_release_versions_sync()

    def get_custom_menu_html(self):
        if config.get("use_custom_menu", False) and os.path.exists(CUSTOM_MENU_PATH):
            try:
                with open(CUSTOM_MENU_PATH, "r", encoding="utf-8") as f:
                    return {"ok": True, "html": f.read()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Кастомное меню отключено или не найдено"}

    # ---------- ресурспак с меню Minecraft ----------
    def get_menu_pack_status(self):
        return {
            "ok": True,
            "installed": os.path.exists(MENU_PACK_PATH),
            "enabled": _menu_pack_enabled(),
            "path": MENU_PACK_PATH,
            "name": MENU_PACK_NAME,
        }

    def install_menu_pack(self):
        src = bundled_asset("assets", MENU_PACK_NAME)
        if not os.path.exists(src):
            return {"ok": False, "error": "Ресурспак не найден в сборке лаунчера"}
        try:
            os.makedirs(os.path.dirname(MENU_PACK_PATH), exist_ok=True)
            shutil.copyfile(src, MENU_PACK_PATH)
            _set_menu_pack_enabled(True)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self._set_status("Ресурспак меню установлен", "#22c55e", "✅")
        return self.get_menu_pack_status()

    def set_menu_pack_enabled(self, enabled):
        enabled = bool(enabled)
        if enabled and not os.path.exists(MENU_PACK_PATH):
            return self.install_menu_pack()
        try:
            _set_menu_pack_enabled(enabled)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self._set_status(
            "Меню Minecraft включено" if enabled else "Меню Minecraft выключено",
            "#22c55e",
            "✅",
        )
        return self.get_menu_pack_status()

    def open_resourcepacks_folder(self):
        try:
            path = os.path.dirname(MENU_PACK_PATH)
            os.makedirs(path, exist_ok=True)
            os.startfile(path)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_nickname(self, nick):
        nick = (nick or "").strip()
        if not nick:
            return {"ok": False, "error": "Ник пустой"}
        save_nickname(nick)
        with _cfg_lock:
            config["nickname"] = nick
            save_config(config)
        self._set_status(f"Ник «{nick}» сохранён", "#22c55e", "✅")
        return {"ok": True}

    def save_settings(self, data):
        data = data or {}
        with _cfg_lock:
            config.update({
                "theme": data.get("theme", config.get("theme", "redsea")),
                "ram": sanitize_ram(data.get("ram", config.get("ram", "4G"))),
                "show_console": bool(data.get("show_console", config.get("show_console", False))),
                "version": data.get("version", config.get("version", "1.20.1")),
                "modloader": data.get("modloader", config.get("modloader", "Vanilla")),
                "use_custom_menu": bool(data.get("use_custom_menu", config.get("use_custom_menu", False))),
            })
            save_config(config)
        self._set_status("Настройки сохранены", "#22c55e", "✅")
        return {"ok": True}

    def set_theme(self, theme):
        allowed = {"purple", "ocean", "forest", "light", "redsea", "black"}
        if theme not in allowed:
            return {"ok": False, "error": "Неизвестная тема"}
        with _cfg_lock:
            config["theme"] = theme
            save_config(config)
        self._safe_eval(f"applyTheme({json.dumps(theme)});")
        return {"ok": True, "theme": theme}

    # ---------- Вход через сайт ----------
    def get_site_account(self):
        with _cfg_lock:
            acc = dict(config.get("site_account") or {})
        if not acc.get("nick"):
            return {"logged_in": False, "site_url": SITE_URL}
        return {
            "logged_in": True,
            "nick": acc.get("nick", ""),
            "role": acc.get("role", "player"),
            "main": bool(acc.get("main")),
            "muted": bool(acc.get("muted")),
            "login_at": acc.get("login_at", ""),
            "site_url": SITE_URL,
        }

    def site_open(self):
        try:
            webbrowser.open(SITE_URL + "#account")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def site_login(self, code):
        try:
            acc = verify_launcher_code(code)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"Не удалось прочитать код: {e}"}
        with _cfg_lock:
            config["site_account"] = acc
            config["nickname"] = acc["nick"]
            save_config(config)
        save_nickname(acc["nick"])
        self._set_status(f"Вход через сайт: {acc['nick']}", "#22c55e", "✅")
        return {"ok": True, **acc}

    def site_logout(self):
        with _cfg_lock:
            config["site_account"] = {}
            save_config(config)
        return {"ok": True}

    # ---------- Microsoft авторизация ----------
    def _ms_creds(self):
        with _cfg_lock:
            return ((config.get("client_id") or "").strip(),
                    (config.get("redirect_uri") or DEFAULT_REDIRECT).strip())

    def get_account(self):
        if account and account.get("name"):
            return {"logged_in": True, "name": account.get("name", ""),
                    "uuid": account.get("id", "")}
        return {"logged_in": False, "name": "", "uuid": ""}

    def ms_start(self):
        client_id, redirect_uri = self._ms_creds()
        if not client_id:
            return {"ok": False, "error": "Укажи Client ID в настройках (Azure App)"}
        try:
            url, state, verifier = minecraft_launcher_lib.microsoft_account.get_secure_login_data(
                client_id, redirect_uri
            )
        except Exception as e:
            return {"ok": False, "error": _ms_error_text(e)}
        with _ms_lock:
            _ms_pending["state"] = state
            _ms_pending["verifier"] = verifier
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return {"ok": True, "url": url}

    def ms_finish(self, redirected_url):
        client_id, redirect_uri = self._ms_creds()
        if not client_id:
            return {"ok": False, "error": "Client ID не задан"}
        with _ms_lock:
            state = _ms_pending.get("state")
            verifier = _ms_pending.get("verifier")
        if not state:
            return {"ok": False, "error": "Сначала нажми «Войти через Microsoft»"}
        redirected_url = (redirected_url or "").strip()
        if not redirected_url:
            return {"ok": False, "error": "Вставь URL после входа"}
        try:
            auth_code = minecraft_launcher_lib.microsoft_account.parse_auth_code_url(
                redirected_url, state
            )
        except AssertionError:
            return {"ok": False, "error": "State не совпал. Войди заново."}
        except KeyError:
            return {"ok": False, "error": "В URL нет параметра code."}
        except Exception as e:
            return {"ok": False, "error": "Неверный URL: " + str(e)[:100]}
        try:
            data = minecraft_launcher_lib.microsoft_account.complete_login(
                client_id, None, redirect_uri, auth_code, verifier
            )
        except Exception as e:
            return {"ok": False, "error": _ms_error_text(e)}
        self._store_account(data)
        return {"ok": True, "name": data.get("name", ""), "uuid": data.get("id", "")}

    def _store_account(self, data):
        global account
        account = {
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", ""),
        }
        save_account(account)

    def ms_logout(self):
        global account
        account = None
        clear_account()
        return {"ok": True}

    def _refresh_account_sync(self):
        """Пытается обновить токен. Возвращает актуальный account или None."""
        global account
        if not account or not account.get("refresh_token"):
            return account
        client_id, redirect_uri = self._ms_creds()
        if not client_id:
            return account
        try:
            data = minecraft_launcher_lib.microsoft_account.complete_refresh(
                client_id, None, redirect_uri, account["refresh_token"]
            )
            self._store_account(data)
        except Exception:
            pass  # оставляем старый токен — вдруг ещё живой
        return account

    # ---------- Modrinth ----------
    def search_modrinth(self, query, project_type, loader, version):
        query = (query or "").strip()
        if not query:
            return {"ok": False, "error": "Пустой запрос"}
        if project_type not in ("mod", "resourcepack", "shader", "datapack", "modpack"):
            return {"ok": False, "error": "Неизвестный тип проекта"}
        try:
            loader_l = (loader or "vanilla").lower()
            facets = [[f"project_type:{project_type}"]]
            if project_type == "mod" and loader_l in ("fabric", "forge", "quilt", "neoforge"):
                facets.append([f"categories:{loader_l}"])
            facets.append([f"versions:{version}"])
            params = {"query": query, "limit": 15, "facets": json.dumps(facets)}
            r = SESSION.get("https://api.modrinth.com/v2/search", params=params, timeout=15)
            r.raise_for_status()
            hits = r.json().get("hits", [])
            return {"ok": True, "hits": [
                {"title": h.get("title", "?"), "slug": h.get("slug", ""),
                 "author": h.get("author", "?"),
                 "downloads": h.get("downloads", 0), "icon": h.get("icon_url", "")}
                for h in hits]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    def download_modrinth(self, slug, project_type, loader, version):
        if not slug:
            return {"ok": False, "error": "Пустой slug"}
        folder_map = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
        if project_type not in folder_map:
            return {"ok": False, "error": "Этот тип нельзя скачать"}
        try:
            url = f"https://api.modrinth.com/v2/project/{slug}/version"
            params = {"game_versions": json.dumps([version])}
            loader_l = (loader or "vanilla").lower()
            if project_type == "mod" and loader_l in ("fabric", "forge", "quilt", "neoforge"):
                params["loaders"] = json.dumps([loader_l])
            r = SESSION.get(url, params=params, timeout=15)
            r.raise_for_status()
            vlist = r.json()
            if not isinstance(vlist, list) or not vlist:
                return {"ok": False, "error": "Нет совместимых версий"}
            vlist = sorted(vlist, key=lambda v: v.get("date_published", ""), reverse=True)
            files = vlist[0].get("files", [])
            if not files:
                return {"ok": False, "error": "Файлы не найдены"}
            pf = next((f for f in files if f.get("primary")), files[0])
            target = os.path.join(BASE_DIR, folder_map[project_type])
            os.makedirs(target, exist_ok=True)
            path = os.path.join(target, os.path.basename(pf["filename"]))
            data = SESSION.get(pf["url"], timeout=120).content
            if not data:
                return {"ok": False, "error": "Пустой файл"}
            with open(path, "wb") as f:
                f.write(data)
            return {"ok": True, "filename": pf["filename"]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    # ---------- Запуск ----------
    def launch_game(self, nick, version, loader, ram, show_console, server_ip=None):
        nick = (nick or "").strip()
        has_acc = bool(account and account.get("access_token"))
        if not nick and not has_acc:
            self._set_status("Ошибка: введи ник или войди в аккаунт!", "#ef4444", "❌")
            return {"ok": False, "error": "Нет ника и нет входа"}
        ram = sanitize_ram(ram)
        if nick:
            save_nickname(nick)
        with _cfg_lock:
            config.update({"version": version, "modloader": loader,
                           "ram": ram, "show_console": bool(show_console)})
            if nick:
                config["nickname"] = nick
            save_config(config)
        threading.Thread(target=self._launch_bg,
                         args=(nick, version, loader, ram, bool(show_console), server_ip),
                         daemon=True).start()
        return {"ok": True}

    def _find_installed(self, version, token):
        try:
            installed = minecraft_launcher_lib.utils.get_installed_versions(BASE_DIR)
        except Exception:
            return version
        cands = [v["id"] for v in installed
                 if version in v.get("id", "") and token in v.get("id", "").lower()]
        return cands[-1] if cands else version

    def _install_mod_loader(self, loader_choice, version):
        lc = (loader_choice or "Vanilla").strip().lower()
        if lc == "fabric":
            self._set_status("Установка Fabric...", "#f59e0b", "⏳")
            try:
                installed_id = minecraft_launcher_lib.fabric.install_fabric(version, BASE_DIR)
            except Exception as e:
                raise RuntimeError(f"Fabric: {e}")
            if isinstance(installed_id, str) and installed_id:
                return installed_id
            return self._find_installed(version, "fabric")
        if lc == "forge":
            self._set_status("Установка Forge...", "#f59e0b", "⏳")
            try:
                installed_id = minecraft_launcher_lib.forge.install_forge_version(version, BASE_DIR)
            except Exception as e:
                raise RuntimeError(f"Forge: {e}")
            if isinstance(installed_id, str) and installed_id:
                return installed_id
            return self._find_installed(version, "forge")
        return version

    def _launch_bg(self, nickname, version, loader_choice, ram, show_console, server_ip=None):
        try:
            self._safe_eval("setPlayBusy(true);")
            self._set_status(f"Проверка и установка {version}...", "#f59e0b", "⏳")

            minecraft_launcher_lib.install.install_minecraft_version(version, BASE_DIR)
            launch_version = self._install_mod_loader(loader_choice, version)

            acc = self._refresh_account_sync()
            if acc and acc.get("access_token") and acc.get("id"):
                username = acc.get("name", nickname) or nickname
                uuid = acc.get("id", "")
                token = acc.get("access_token", "")
                self._safe_eval("setStatus('Вход выполнен: ' + "
                                + json.dumps(acc.get("name", ""))
                                + ", '#22c55e', '✅');")
            else:
                username, uuid, token = nickname, "", ""

            self._set_status(f"Запуск {launch_version}...", "#22c55e", "🚀")
            options = {
                "username": username, "uuid": uuid, "token": token,
                "jvmArguments": [f"-Xmx{ram}", f"-Xms{ram}"],
            }
            if server_ip:
                options["customArgs"] = ["--quickPlayMultiplayer", server_ip]

            command = minecraft_launcher_lib.command.get_minecraft_command(
                launch_version, BASE_DIR, options
            )

            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            if show_console:
                self._open_console_window(command)
            else:
                process = subprocess.Popen(
                    command, cwd=BASE_DIR,
                    startupinfo=startupinfo, creationflags=creationflags
                )
                process.wait()
                self._set_status("Игра закрыта", "#8b949e", "✅")

        except Exception as e:
            self._set_status(f"Ошибка: {str(e)[:90]}", "#ef4444", "❌")
        finally:
            if not show_console:
                self._safe_eval("setPlayBusy(false);")

    def _open_console_window(self, command):
        def run():
            try:
                root = tk.Tk()
            except Exception:
                return
            root.title("BritonLauncher - Консоль игры")
            root.geometry("800x500")
            root.configure(bg="#0e0a14")

            text_area = ScrolledText(root, bg="#12060a", fg="#ffe6ec",
                                     font=("Consolas", 10), insertbackground="white")
            text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text_area.insert(tk.END, "> " + " ".join(command) + "\n\n")
            text_area.configure(state='disabled')

            alive = {"v": True}

            def append_text(text):
                if not alive["v"]:
                    return
                try:
                    text_area.configure(state='normal')
                    text_area.insert(tk.END, text)
                    text_area.see(tk.END)
                    text_area.configure(state='disabled')
                except Exception:
                    pass

            def read_output(process):
                try:
                    for line in iter(process.stdout.readline, b""):
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace")
                        root.after(0, append_text, decoded)
                    root.after(0, append_text, "\n[Игра закрыта]\n")
                except Exception:
                    pass
                finally:
                    self._safe_eval("setPlayBusy(false);")
                    self._set_status("Игра закрыта", "#8b949e", "✅")

            def on_close():
                alive["v"] = False
                try:
                    root.destroy()
                except Exception:
                    pass

            root.protocol("WM_DELETE_WINDOW", on_close)

            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            try:
                process = subprocess.Popen(
                    command, cwd=BASE_DIR,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    startupinfo=startupinfo, creationflags=creationflags
                )
            except Exception:
                on_close()
                return

            threading.Thread(target=read_output, args=(process,), daemon=True).start()

            try:
                root.mainloop()
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()

    def check_updates(self):
        current = CURRENT_VERSION
        try:
            r = SESSION.get(UPDATE_URL, timeout=10)
            if r.status_code != 200:
                return {"ok": False, "current": current}
            data = r.json()
            latest = (data.get("tag_name") or "").lstrip("v")
            url = data.get("html_url", "")
            if not latest:
                return {"ok": False, "current": current}
            available = _ver_tuple(latest) > _ver_tuple(current)
            return {"ok": True, "latest": latest, "url": url,
                    "update_available": available, "current": current}
        except Exception:
            return {"ok": False, "current": current}

    def open_url(self, url):
        if url:
            webbrowser.open(url)


HTML = """<!DOCTYPE html>
<html lang="ru" data-theme="redsea">
<head>
<meta charset="UTF-8">
<title>BritonLauncher</title>
<style>
:root, :root[data-theme="purple"] { --bg:#0b0d12; --bg-soft:#10141c; --glass:rgba(22,27,34,0.6); --glass-border:rgba(255,255,255,0.06); --text:#eef2f9; --text-dim:#8b949e; --text-mute:#5b6472; --grad-1:#a855f7; --grad-2:#ec4899; --accent:#a855f7; --accent-soft:rgba(168,85,247,0.15); --green:#22c55e; --orange:#f59e0b; --red:#ef4444; --body-bg: radial-gradient(circle at 15% 10%, rgba(168,85,247,0.10), transparent 45%), radial-gradient(circle at 85% 90%, rgba(236,72,153,0.08), transparent 45%), var(--bg); }
:root[data-theme="ocean"] { --bg:#081018; --bg-soft:#0d1a24; --glass:rgba(15,30,42,0.6); --glass-border:rgba(120,220,255,0.10); --text:#e3f6ff; --text-dim:#7ea8c0; --text-mute:#4a6b80; --grad-1:#06b6d4; --grad-2:#3b82f6; --accent:#06b6d4; --accent-soft:rgba(6,182,212,0.15); --green:#22c55e; --orange:#f59e0b; --red:#ef4444; --body-bg: radial-gradient(circle at 15% 10%, rgba(6,182,212,0.14), transparent 45%), radial-gradient(circle at 85% 90%, rgba(59,130,246,0.10), transparent 45%), var(--bg); }
:root[data-theme="forest"] { --bg:#0a1210; --bg-soft:#0f1a16; --glass:rgba(18,32,26,0.6); --glass-border:rgba(100,255,180,0.08); --text:#e6fff1; --text-dim:#84a896; --text-mute:#507060; --grad-1:#10b981; --grad-2:#84cc16; --accent:#10b981; --accent-soft:rgba(16,185,129,0.15); --green:#22c55e; --orange:#f59e0b; --red:#ef4444; --body-bg: radial-gradient(circle at 15% 10%, rgba(16,185,129,0.14), transparent 45%), radial-gradient(circle at 85% 90%, rgba(132,204,22,0.10), transparent 45%), var(--bg); }
:root[data-theme="redsea"] { --bg:#12060a; --bg-soft:#1a0a10; --glass:rgba(30,12,18,0.65); --glass-border:rgba(255,90,120,0.12); --text:#ffe6ec; --text-dim:#c08a96; --text-mute:#7a4a56; --grad-1:#ef4444; --grad-2:#f97316; --accent:#ef4444; --accent-soft:rgba(239,68,68,0.18); --green:#22c55e; --orange:#f59e0b; --red:#ff6b6b; --body-bg: radial-gradient(circle at 15% 10%, rgba(239,68,68,0.18), transparent 45%), radial-gradient(circle at 85% 90%, rgba(249,115,22,0.12), transparent 45%), var(--bg); }
:root[data-theme="light"] { --bg:#f4f5fa; --bg-soft:#ffffff; --glass:rgba(255,255,255,0.75); --glass-border:rgba(20,20,40,0.08); --text:#1a1d2e; --text-dim:#5c647a; --text-mute:#9aa0b4; --grad-1:#8b5cf6; --grad-2:#ec4899; --accent:#7c3aed; --accent-soft:rgba(124,58,237,0.12); --green:#059669; --orange:#d97706; --red:#dc2626; --body-bg: radial-gradient(circle at 15% 10%, rgba(139,92,246,0.10), transparent 45%), radial-gradient(circle at 85% 90%, rgba(236,72,153,0.08), transparent 45%), var(--bg); }
:root[data-theme="black"] { --bg:#000; --bg-soft:#0a0a0a; --glass:rgba(15,15,15,0.75); --glass-border:rgba(255,255,255,0.10); --text:#fff; --text-dim:#a0a0a0; --text-mute:#606060; --grad-1:#fff; --grad-2:#a0a0a0; --accent:#fff; --accent-soft:rgba(255,255,255,0.10); --green:#22c55e; --orange:#f59e0b; --red:#ef4444; --body-bg: radial-gradient(circle at 15% 10%, rgba(255,255,255,0.04), transparent 45%), radial-gradient(circle at 85% 90%, rgba(255,255,255,0.02), transparent 45%), var(--bg); }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; background: var(--body-bg); color: var(--text); font-family: 'Segoe UI', 'Inter', 'Roboto', Arial, sans-serif; overflow: hidden; user-select: none; transition: background 0.3s, color 0.3s; -webkit-font-smoothing: antialiased; }
.ico { display: inline-block; width: 20px; height: 20px; vertical-align: middle; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
#titlebar { height: 56px; display: flex; align-items: center; padding: 0 8px 0 18px; background: var(--glass); backdrop-filter: blur(14px); border-bottom: 1px solid var(--glass-border); }
.brand { display: flex; align-items: center; gap: 10px; }
.brand-logo { width: 34px; height: 34px; border-radius: 10px; background: linear-gradient(135deg, var(--grad-1), var(--grad-2)); display: grid; place-items: center; font-weight: 800; font-size: 17px; color: white; box-shadow: 0 6px 22px var(--accent-soft); }
.brand-name { font-weight: 700; font-size: 15px; }
.brand-ver { font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); margin-left: 4px; }
.title-account { margin-left: auto; margin-right: 8px; display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; background: var(--accent-soft); border: 1px solid var(--glass-border); color: var(--text); font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit; transition: all 0.15s; }
.title-account:hover { border-color: var(--accent); }
.title-account .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-mute); flex-shrink: 0; }
.title-account.admin .dot { background: var(--accent); }
.title-account .role { font-size: 9px; letter-spacing: 0.5px; color: var(--accent); font-weight: 800; }
.title-account .role.muted { color: #facc15; }
.win-btns { margin-left: 0; display: flex; gap: 4px; }
.win-btn { width: 44px; height: 36px; background: transparent; border: none; color: var(--text-dim); font-size: 14px; font-weight: 700; border-radius: 10px; cursor: pointer; transition: all 0.15s; display: grid; place-items: center; }
.win-btn:hover { background: rgba(128,128,128,0.15); color: var(--text); }
.win-btn.close:hover { background: #c42b1c; color: white; }
.container { display: flex; gap: 16px; height: calc(100vh - 57px); padding: 16px; }
.nav-bar { width: 84px; background: var(--glass); backdrop-filter: blur(14px); border: 1px solid var(--glass-border); border-radius: 22px; padding: 14px 8px; display: flex; flex-direction: column; gap: 10px; align-items: center; overflow-y: auto; }
.nav-ver { margin-top: auto; font-size: 10px; font-weight: 800; color: var(--text-mute); letter-spacing: 0.4px; padding: 6px 0 2px; }
.nav-item { width: 60px; padding: 10px 0 8px; background: transparent; border: none; border-radius: 16px; color: var(--text-mute); font-size: 10px; font-weight: 600; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 4px; transition: all 0.18s; font-family: inherit; }
.nav-item .ico { width: 22px; height: 22px; }
.nav-item:hover { background: rgba(128,128,128,0.1); color: var(--text); }
.nav-item.active { background: linear-gradient(135deg, var(--accent-soft), transparent); color: var(--text); box-shadow: inset 0 0 0 1px var(--accent); }
.content { flex: 1; background: var(--glass); backdrop-filter: blur(14px); border: 1px solid var(--glass-border); border-radius: 22px; padding: 28px 32px; overflow-y: auto; position: relative; }
.hero { position: relative; padding: 32px; border-radius: 22px; background: radial-gradient(circle at 100% 0%, var(--accent-soft), transparent 55%), radial-gradient(circle at 0% 100%, var(--accent-soft), transparent 55%), linear-gradient(135deg, var(--accent-soft), transparent); border: 1px solid var(--accent-soft); overflow: hidden; margin-bottom: 24px; }
.hero > * { position: relative; z-index: 1; }
.hero-title { font-size: 30px; font-weight: 800; background: linear-gradient(135deg, var(--text), var(--accent)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 6px; display: flex; align-items: center; gap: 10px; }
.hero-title .ico { width: 30px; height: 30px; stroke: var(--accent); stroke-width: 2.2; -webkit-text-fill-color: initial; }
.hero-sub { color: var(--text-dim); font-size: 13px; margin-bottom: 26px; }
.hero-form { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 14px; margin-bottom: 26px; }
.hero-field label { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px; color: var(--text-mute); margin-bottom: 6px; font-weight: 700; }
.hero-field .row { display: flex; gap: 8px; }
input, select { width: 100%; padding: 13px 14px; background: var(--bg-soft); border: 1px solid var(--glass-border); border-radius: 14px; color: var(--text); font-size: 13px; font-family: inherit; outline: none; transition: all 0.15s; }
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.btn-icon { width: 46px; height: 46px; flex-shrink: 0; background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-soft); border-radius: 14px; cursor: pointer; transition: all 0.15s; display: grid; place-items: center; }
.btn-icon:hover { background: var(--accent); color: white; }
.btn-play { height: 62px; width: 100%; background: linear-gradient(135deg, var(--grad-1), var(--grad-2)); color: white; border: none; border-radius: 16px; font-size: 17px; font-weight: 800; letter-spacing: 0.5px; cursor: pointer; box-shadow: 0 12px 32px var(--accent-soft); transition: all 0.18s; display: flex; align-items: center; justify-content: center; gap: 10px; }
.btn-play:hover { transform: translateY(-2px); box-shadow: 0 16px 40px var(--accent-soft); }
.btn-play:disabled { background: var(--bg-soft); color: var(--text-mute); box-shadow: none; cursor: not-allowed; transform: none; }
.btn-play svg { width: 20px; height: 20px; }
.status-box { display: flex; align-items: center; gap: 10px; padding: 12px 16px; background: var(--bg-soft); border: 1px solid var(--glass-border); border-radius: 14px; font-size: 12px; margin-top: 20px; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-mute); flex-shrink: 0; transition: background 0.3s; }
.status-dot.loading { background: var(--orange); animation: pulse 1s ease-in-out infinite; }
.status-dot.ok { background: var(--green); }
.status-dot.error { background: var(--red); }
.status-dot.info { background: var(--accent); }
@keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(1.2); } }
#status-text { color: var(--text-dim); flex: 1; }
.account-box { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--bg-soft); border: 1px solid var(--glass-border); border-radius: 14px; margin-bottom: 18px; font-size: 13px; }
.account-head { width: 34px; height: 34px; border-radius: 50%; background: linear-gradient(135deg, var(--grad-1), var(--grad-2)); display: grid; place-items: center; font-weight: 800; color: #fff; flex-shrink: 0; }
.account-name { font-weight: 700; color: var(--green); }
.account-box .spacer { flex: 1; }
.account-role { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px; font-size: 10px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; background: rgba(197, 160, 89, 0.18); color: var(--accent); }
.account-mute { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px; font-size: 10px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; background: rgba(234, 179, 8, 0.18); color: #facc15; }
.site-login-row { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.site-login-row input { flex: 1; min-width: 180px; padding: 9px 12px; border-radius: 10px; border: 1px solid var(--glass-border); background: var(--bg-soft); color: var(--text); font: inherit; font-size: 12px; outline: none; }
.site-login-row input:focus { border-color: var(--accent); }
.site-hint { color: var(--text-mute); font-size: 11px; margin-top: 6px; }
.admin-card { background: var(--bg-soft); border: 1px solid var(--glass-border); border-radius: 16px; padding: 16px 18px; margin-bottom: 18px; display: grid; gap: 10px; max-width: 520px; }
.admin-row { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; color: var(--text-dim); }
.admin-row b { color: var(--text); }
.admin-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.ms-input-row { display: flex; gap: 8px; margin-top: 8px; }
.page-title { font-size: 24px; font-weight: 800; margin-bottom: 4px; display: flex; align-items: center; gap: 10px; }
.page-title .grad { background: linear-gradient(135deg, var(--grad-1), var(--grad-2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.page-title svg { stroke: var(--accent); -webkit-text-fill-color: initial; }
.page-sub { color: var(--text-dim); font-size: 13px; margin-bottom: 22px; }
.search-row { display: flex; gap: 10px; margin-bottom: 22px; }
.search-row input { flex: 1; }
.btn { padding: 13px 22px; background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-soft); border-radius: 14px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.15s; font-family: inherit; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
.btn:hover { background: var(--accent); color: white; }
.btn svg { width: 16px; height: 16px; }
.btn.primary { background: linear-gradient(135deg, var(--grad-1), var(--grad-2)); color: white; border: none; box-shadow: 0 6px 20px var(--accent-soft); }
.btn.primary:hover { transform: translateY(-1px); }
.btn.green { background: rgba(34,197,94,0.15); color: var(--green); border: 1px solid rgba(34,197,94,0.35); }
.btn.green:hover { background: rgba(34,197,94,0.28); }
.btn.full { width: 100%; margin-top: 14px; }
.results-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-bottom: 18px; }
.result-item { display: flex; align-items: center; gap: 12px; padding: 14px; background: var(--bg-soft); border: 1px solid var(--glass-border); border-radius: 16px; cursor: pointer; transition: all 0.15s; }
.result-item:hover { transform: translateY(-2px); border-color: var(--accent); }
.result-item.selected { border-color: var(--accent); background: linear-gradient(135deg, var(--accent-soft), transparent); box-shadow: 0 0 0 1px var(--accent); }
.result-icon { width: 40px; height: 40px; border-radius: 10px; background: var(--accent-soft); display: grid; place-items: center; color: var(--accent); flex-shrink: 0; font-weight: 800; font-size: 16px; }
.result-info { flex: 1; min-width: 0; }
.result-title { font-weight: 700; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.result-meta { font-size: 11px; color: var(--text-dim); margin-top: 3px; display: flex; gap: 8px; }
.result-meta .badge { background: rgba(128,128,128,0.12); padding: 1px 6px; border-radius: 6px; }
.page-status { font-size: 12px; color: var(--text-dim); padding: 12px 0; }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.settings-section { background: var(--bg-soft); border: 1px solid var(--glass-border); border-radius: 18px; padding: 20px; }
.settings-section h3 { font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--text-mute); margin-bottom: 14px; font-weight: 700; }
.settings-section input { margin-top: 8px; }
.switch-row { display: flex; align-items: center; justify-content: space-between; font-size: 13px; }
.switch { position: relative; width: 48px; height: 26px; background: rgba(128,128,128,0.2); border-radius: 13px; cursor: pointer; transition: background 0.2s; flex-shrink: 0; }
.switch.on { background: linear-gradient(135deg, var(--grad-1), var(--grad-2)); }
.switch::after { content: ''; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; background: white; border-radius: 50%; transition: left 0.2s; box-shadow: 0 2px 6px rgba(0,0,0,0.3); }
.switch.on::after { left: 25px; }
.menu-pack-actions { display: flex; gap: 10px; flex-wrap: wrap; margin: 4px 0 10px; }
.menu-pack-actions .btn { flex: 1 1 160px; }
.theme-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; }
.theme-card { position: relative; padding: 10px; background: var(--bg); border: 2px solid transparent; border-radius: 14px; cursor: pointer; transition: all 0.18s; text-align: center; }
.theme-card:hover { transform: translateY(-2px); border-color: var(--accent); }
.theme-card.active { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.theme-preview { width: 100%; height: 54px; border-radius: 10px; margin-bottom: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.25); }
.theme-name { font-size: 12px; font-weight: 700; color: var(--text); }
.theme-check { position: absolute; top: 6px; right: 8px; width: 20px; height: 20px; border-radius: 50%; background: var(--accent); color: white; font-size: 12px; display: none; place-items: center; font-weight: 900; }
.theme-card.active .theme-check { display: grid; }
#custom-menu-iframe { width: 100%; height: 100%; border: none; background: transparent; display: none; }
</style>
</head>
<body>

<div id="titlebar" class="pywebview-drag-region">
  <div class="brand">
    <div class="brand-logo">B</div>
    <div class="brand-name">BritonLauncher</div>
  </div>
  <button class="title-account" id="title-account" onclick="titleAccountClick()" title="Войти через сайт">
    <span class="dot"></span><span class="ta-nick">Войти</span>
  </button>
  <div class="win-btns">
    <button class="win-btn" onclick="pywebview.api.minimize()">—</button>
    <button class="win-btn" onclick="pywebview.api.maximize()">□</button>
    <button class="win-btn close" onclick="pywebview.api.close()">✕</button>
  </div>
</div>

<div class="container">
  <div class="nav-bar">
    <button class="nav-item active" data-page="launch" onclick="showPage('launch')">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>
      Запуск
    </button>
    <button class="nav-item" data-page="mods" onclick="showPage('mods')">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
      Моды
    </button>
    <button class="nav-item" data-page="resourcepacks" onclick="showPage('resourcepacks')">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/></svg>
      Ресурсы
    </button>
    <button class="nav-item" data-page="shaders" onclick="showPage('shaders')">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
      Шейдеры
    </button>
    <button class="nav-item" data-page="admin" id="nav-admin" style="display:none" onclick="showPage('admin')">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
      Админка
    </button>
    <button class="nav-item" data-page="settings" onclick="showPage('settings')">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      Настройки
    </button>
    <div class="nav-ver" title="Версия лаунчера">v3.8.1</div>
  </div>
  <div class="content" id="content">
    <iframe id="custom-menu-iframe"></iframe>
  </div>
</div>

<script>
let selectedItem = null;
let selectedType = null;
const state = { version: '1.20.1', loader: 'Vanilla' };

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function showToast(msg) {
  const d = document.createElement('div');
  d.textContent = msg;
  d.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;padding:10px 18px;border-radius:12px;font-size:13px;font-weight:700;z-index:9999;box-shadow:0 8px 24px rgba(0,0,0,.4);transition:opacity .3s;max-width:80vw;';
  document.body.appendChild(d);
  setTimeout(() => { d.style.opacity = '0'; setTimeout(() => d.remove(), 300); }, 2600);
}

function applyTheme(id) { document.documentElement.setAttribute('data-theme', id); }
function setStatus(text, color, icon) {
  const t = document.getElementById('status-text');
  const d = document.getElementById('status-dot');
  if (t) { t.textContent = text; t.style.color = color || 'var(--text-dim)'; }
  if (d) {
    d.className = 'status-dot';
    if (icon === '⏳') d.classList.add('loading');
    else if (icon === '✅') d.classList.add('ok');
    else if (icon === '❌') d.classList.add('error');
    else if (icon === 'ℹ️') d.classList.add('info');
    else if (icon === '☕') d.classList.add('info');
    else if (icon === '⚠️') d.classList.add('error');
  }
}
function setPlayBusy(b) {
  const btn = document.getElementById('play-btn');
  if (!btn) return;
  btn.disabled = b;
  btn.innerHTML = b
    ? '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:20px;height:20px;"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> Запуск...'
    : '<svg class="ico" viewBox="0 0 24 24" fill="currentColor" style="width:20px;height:20px;"><polygon points="6 3 20 12 6 21 6 3" stroke="none"/></svg> ИГРАТЬ';
}

async function saveNick() {
  const nick = (document.getElementById('nick')?.value || '').trim();
  if (!nick) { setStatus('Ник пустой', 'var(--red)', '❌'); showToast('Введите ник'); return; }
  const res = await window.pywebview.api.save_nickname(nick);
  if (res && res.ok) showToast('Ник сохранён');
}
async function startGame(serverIp = null) {
  const nick = (document.getElementById('nick')?.value || '').trim();
  const cfg = await window.pywebview.api.get_config();
  await window.pywebview.api.launch_game(nick, state.version, state.loader, cfg.ram, cfg.show_console, serverIp);
}

function updateAdminNav(acc) {
  const nav = document.getElementById('nav-admin');
  if (nav) nav.style.display = acc && acc.logged_in && acc.role === 'admin' ? 'flex' : 'none';
}

function updateTitleAccount(acc) {
  const el = document.getElementById('title-account');
  if (!el) return;
  window.__titleAcc = acc || null;
  if (acc && acc.logged_in) {
    el.classList.toggle('admin', acc.role === 'admin');
    el.innerHTML = '<span class="dot"></span><span class="ta-nick">' + escapeHtml(acc.nick) + '</span>'
      + (acc.role === 'admin' ? '<span class="role">' + (acc.main ? 'ГЛАВНЫЙ АДМИН' : 'АДМИН') + '</span>' : '')
      + (acc.muted ? '<span class="role muted">МУТ</span>' : '');
    el.title = acc.role === 'admin' ? 'Открыть админ-панель' : 'Аккаунт сайта';
  } else {
    el.classList.remove('admin');
    el.innerHTML = '<span class="dot"></span><span class="ta-nick">Войти</span>';
    el.title = 'Войти через сайт';
  }
}

function titleAccountClick() {
  const acc = window.__titleAcc;
  if (acc && acc.logged_in && acc.role === 'admin') {
    showPage('admin');
    return;
  }
  showPage('launch').then(() => {
    setTimeout(() => document.getElementById('site-code')?.focus(), 250);
  });
}

function roleLabel(acc) {
  if (!acc || !acc.logged_in || acc.role !== 'admin') return 'ИГРОК';
  return acc.main ? 'ГЛАВНЫЙ АДМИН' : 'АДМИН';
}

async function refreshAccount() {
  const acc = await window.pywebview.api.get_site_account();
  updateAdminNav(acc);
  updateTitleAccount(acc);
  const box = document.getElementById('account-box');
  if (!box) return;
  if (acc.logged_in) {
    box.innerHTML = '<div class="account-head">' + escapeHtml(acc.nick.charAt(0).toUpperCase()) + '</div>'
      + '<div>Вход через сайт: <span class="account-name">' + escapeHtml(acc.nick) + '</span>'
      + '<span class="account-role">' + roleLabel(acc) + '</span>'
      + (acc.muted ? '<span class="account-mute">МУТ</span>' : '') + '</div>'
      + '<div class="spacer"></div>'
      + (acc.role === 'admin' ? '<button class="btn" onclick="goAdmin()">Админ-панель</button>' : '')
      + '<button class="btn" onclick="siteLogout()">Выйти</button>';
  } else {
    box.innerHTML = '<div style="flex:1">'
      + '<div>Аккаунт сайта: <b>не выполнен</b></div>'
      + '<div class="site-login-row"><input id="site-code" placeholder="Вставь код с сайта" spellcheck="false" />'
      + '<button class="btn green" onclick="siteLogin()">Войти по коду</button>'
      + '<button class="btn" onclick="siteOpen()">Открыть сайт</button></div>'
      + '<div class="site-hint">Сайт → раздел «Аккаунт» → «Получить код для лаунчера».</div>'
      + '</div>';
  }
}

async function siteOpen() {
  await window.pywebview.api.site_open();
  showToast('Открой сайт, войди и получи код для лаунчера');
}

async function siteLogin() {
  const code = (document.getElementById('site-code')?.value || '').trim();
  if (!code) { showToast('Вставь код с сайта'); return; }
  const res = await window.pywebview.api.site_login(code);
  if (res.ok) {
    showToast(res.muted ? 'Вход выполнен: ' + res.nick + ' (действует мут)' : 'Вход выполнен: ' + res.nick);
    refreshAccount();
    if (document.body.dataset.activePage === 'admin') renderAdminPage();
  } else {
    showToast('Ошибка: ' + res.error);
  }
}

async function siteLogout() {
  await window.pywebview.api.site_logout();
  updateAdminNav(null);
  showToast('Вы вышли из аккаунта');
  if (document.body.dataset.activePage === 'admin') showPage('launch');
  else refreshAccount();
}

function goAdmin() { showPage('admin'); }

async function renderAdminPage() {
  const acc = await window.pywebview.api.get_site_account();
  const content = document.getElementById('content');
  content.style.padding = '28px 32px';
  if (!acc.logged_in || acc.role !== 'admin') {
    content.innerHTML = '<div class="page-title"><span class="grad">Админ-панель</span></div>'
      + '<div class="page-sub">Доступ только для администраторов сайта.</div>';
    return;
  }
  content.innerHTML = `
    <div class="page-title"><span class="grad">Админ-панель</span></div>
    <div class="page-sub">Аккаунт сайта и управление игроками</div>
    <div class="admin-card">
      <div class="admin-row"><span>Ник</span><b>${escapeHtml(acc.nick)}</b></div>
      <div class="admin-row"><span>Роль</span><b>${acc.main ? 'Главный администратор' : 'Администратор'}</b></div>
      <div class="admin-row"><span>Статус</span><b>${acc.muted ? 'Мут' : 'Активен'}</b></div>
      <div class="admin-row"><span>Вход</span><b>${escapeHtml(acc.login_at || '—')}</b></div>
    </div>
    <div class="admin-actions">
      <button class="btn primary" onclick="openSiteAdmin()">Открыть админ-панель на сайте</button>
      <button class="btn" onclick="siteLogout()">Выйти</button>
    </div>
    <div class="page-status">Аккаунты хранятся в браузере на сайте. Управление игроками — там же, в разделе «Аккаунт».</div>`;
}

async function openSiteAdmin() {
  await window.pywebview.api.site_open();
  showToast('Открыл сайт — раздел «Аккаунт»');
}

async function showPage(page) {
  document.body.dataset.activePage = page;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  selectedItem = null;
  selectedType = null;

  const content = document.getElementById('content');
  let iframe = document.getElementById('custom-menu-iframe');
  if (!iframe) {
    iframe = document.createElement('iframe');
    iframe.id = 'custom-menu-iframe';
    content.appendChild(iframe);
  }

  iframe.style.display = 'none';
  iframe.srcdoc = '';

  if (page === 'launch') {
    const menuData = await window.pywebview.api.get_custom_menu_html();
    if (menuData.ok) {
      iframe.srcdoc = menuData.html;
      iframe.style.display = 'block';
      content.style.padding = '0';
      return;
    } else {
      content.style.padding = '28px 32px';
      renderLaunch();
    }
  } else {
    content.style.padding = '28px 32px';
    if (page === 'admin') renderAdminPage();
    else if (page === 'settings') renderSettings();
    else renderSearchPage(page);
  }
}

async function renderLaunch() {
  const cfg = await window.pywebview.api.get_config();
  document.getElementById('content').innerHTML = `
    <div class="hero">
      <div class="hero-title">
        <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:30px;height:30px;"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>
        Готов к игре?
      </div>
      <div class="hero-sub">Настрой параметры и жми «Играть»</div>
      <div id="account-box" class="account-box"><div class="spacer">Проверка аккаунта...</div></div>
      <div class="hero-form">
        <div class="hero-field"><label>Никнейм (офлайн)</label>
          <div class="row">
            <input id="nick" placeholder="Steve" value="${escapeHtml(cfg.nickname || '')}" />
            <button class="btn-icon" onclick="saveNick()" title="Сохранить">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px;height:20px;"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            </button>
          </div>
        </div>
        <div class="hero-field"><label>Версия</label><select id="version"></select></div>
        <div class="hero-field"><label>Модлоадер</label>
          <select id="modloader">
            <option value="Vanilla" ${cfg.modloader==='Vanilla'?'selected':''}>Vanilla</option>
            <option value="Fabric" ${cfg.modloader==='Fabric'?'selected':''}>Fabric</option>
            <option value="Forge" ${cfg.modloader==='Forge'?'selected':''}>Forge</option>
          </select>
        </div>
      </div>
      <button id="play-btn" class="btn-play" onclick="startGame()">
        <svg class="ico" viewBox="0 0 24 24" fill="currentColor" style="width:20px;height:20px;"><polygon points="6 3 20 12 6 21 6 3" stroke="none"/></svg> ИГРАТЬ
      </button>
      <div class="status-box"><div class="status-dot" id="status-dot"></div><span id="status-text">Проверка обновлений...</span></div>
    </div>`;

  const versions = await window.pywebview.api.get_versions();
  const sel = document.getElementById('version');
  sel.innerHTML = '';
  let found = false;
  (versions || []).forEach(v => {
    const o = document.createElement('option');
    o.value = v; o.textContent = v;
    if (v === cfg.version) { o.selected = true; found = true; }
    sel.appendChild(o);
  });
  if (!found && sel.options.length) sel.selectedIndex = 0;
  state.version = sel.value || '1.20.1';

  const loaderSel = document.getElementById('modloader');
  state.loader = loaderSel.value || 'Vanilla';
  sel.addEventListener('change', () => { state.version = sel.value; });
  loaderSel.addEventListener('change', () => { state.loader = loaderSel.value; });

  refreshAccount();

  const up = await window.pywebview.api.check_updates();
  if (up.ok && up.update_available) {
    setStatus('Доступно обновление v' + up.latest, 'var(--orange)', '⏳');
  } else if (up.ok) {
    setStatus('Версия актуальна (v' + (up.current || '') + ')', 'var(--green)', '✅');
  } else {
    setStatus('Проверка обновлений недоступна', 'var(--text-dim)', 'ℹ️');
  }
}

const PAGE_INFO = {
  mods: { title: 'Моды', type: 'mod' },
  resourcepacks: { title: 'Ресурспаки', type: 'resourcepack' },
  shaders: { title: 'Шейдеры', type: 'shader' },
};

function renderSearchPage(page) {
  const info = PAGE_INFO[page];
  selectedType = info.type;
  document.getElementById('content').innerHTML = `
    <div class="page-title"><span class="grad">${info.title}</span></div>
    <div class="page-sub">Поиск и установка через Modrinth · версия ${escapeHtml(state.version)} · ${escapeHtml(state.loader)}</div>
    <div class="search-row">
      <input id="search-input" placeholder="Название..." onkeydown="if(event.key==='Enter')doSearch()" />
      <button class="btn primary" onclick="doSearch()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> Найти
      </button>
    </div>
    <div class="page-status" id="page-status">Введи название</div>
    <div class="results-grid" id="results"></div>
    <button class="btn green full" onclick="downloadSelected()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Скачать выбранное
    </button>`;
}

async function doSearch() {
  const input = document.getElementById('search-input');
  const status = document.getElementById('page-status');
  const q = (input?.value || '').trim();
  if (!q) { status.textContent = 'Введи название'; status.style.color = 'var(--red)'; return; }
  status.textContent = 'Поиск...'; status.style.color = 'var(--orange)';
  const res = await window.pywebview.api.search_modrinth(q, selectedType, state.loader, state.version);
  if (!res.ok) { status.textContent = 'Ошибка: ' + res.error; status.style.color = 'var(--red)'; return; }
  if (!res.hits.length) { status.textContent = 'Ничего не найдено'; status.style.color = 'var(--red)'; return; }
  status.textContent = `Найдено: ${res.hits.length}`; status.style.color = 'var(--green)';
  const box = document.getElementById('results'); box.innerHTML = '';
  res.hits.forEach(h => {
    const el = document.createElement('div');
    el.className = 'result-item';
    const initial = (h.title || '?').charAt(0).toUpperCase();
    el.innerHTML = `<div class="result-icon">${escapeHtml(initial)}</div><div class="result-info"><div class="result-title">${escapeHtml(h.title)}</div><div class="result-meta"><span class="badge">${escapeHtml(h.author)}</span><span class="badge">${(h.downloads||0).toLocaleString()} DL</span></div></div>`;
    el.onclick = () => { document.querySelectorAll('.result-item').forEach(x => x.classList.remove('selected')); el.classList.add('selected'); selectedItem = h; };
    box.appendChild(el);
  });
}

async function downloadSelected() {
  const status = document.getElementById('page-status');
  if (!selectedItem) { status.textContent = 'Выбери проект'; status.style.color = 'var(--red)'; return; }
  status.textContent = `Скачивание ${selectedItem.slug}...`; status.style.color = 'var(--orange)';
  const res = await window.pywebview.api.download_modrinth(selectedItem.slug, selectedType, state.loader, state.version);
  if (res.ok) { status.textContent = `Скачано: ${res.filename}`; status.style.color = 'var(--green)'; showToast('Скачано: ' + res.filename); }
  else { status.textContent = 'Ошибка: ' + res.error; status.style.color = 'var(--red)'; }
}

async function renderSettings() {
  const cfg = await window.pywebview.api.get_config();
  const themes = [
    { id: 'purple', name: 'Purple Night', g1: '#a855f7', g2: '#ec4899' },
    { id: 'ocean', name: 'Ocean', g1: '#06b6d4', g2: '#3b82f6' },
    { id: 'forest', name: 'Forest', g1: '#10b981', g2: '#84cc16' },
    { id: 'redsea', name: 'Red Sea', g1: '#ef4444', g2: '#f97316' },
    { id: 'light', name: 'Light', g1: '#8b5cf6', g2: '#ec4899' },
    { id: 'black', name: 'Black', g1: '#ffffff', g2: '#606060' },
  ];
  const cards = themes.map(t => `<div class="theme-card ${cfg.theme === t.id ? 'active' : ''}" data-theme-id="${t.id}" onclick="pickTheme('${t.id}')"><div class="theme-preview" style="background: linear-gradient(135deg, ${t.g1}, ${t.g2});"></div><div class="theme-name">${t.name}</div><div class="theme-check">✓</div></div>`).join('');

  document.getElementById('content').innerHTML = `
    <div class="page-title"><span class="grad">Настройки</span></div>
    <div class="page-sub">BritonLauncher v3.8.1</div>

    <div class="settings-section" style="margin-bottom:14px;">
      <h3>Тема оформления</h3>
      <div class="theme-grid">${cards}</div>
    </div>

    <div class="settings-grid">
      <div class="settings-section"><h3>Память (4G или 2048M)</h3><input id="ram" value="${escapeHtml(cfg.ram || '4G')}" /></div>
      <div class="settings-section">
        <h3>Консоль</h3>
        <div class="switch-row">
          <span>Отдельное окно</span>
          <div id="console-switch" class="switch ${cfg.show_console ? 'on' : ''}" onclick="this.classList.toggle('on')"></div>
        </div>
      </div>
    </div>

    <div class="settings-section" style="margin-top:14px;">
      <h3>Меню Minecraft (ресурспак)</h3>
      <div class="switch-row">
        <span>Брендовый фон, логотип и сплэши</span>
        <div id="menu-pack-switch" class="switch" onclick="toggleMenuPack(this)"></div>
      </div>
      <div class="page-status" id="menu-pack-status">Проверяю...</div>
      <div class="menu-pack-actions">
        <button class="btn" onclick="installMenuPack()">Установить / обновить</button>
        <button class="btn" onclick="openResourcepacksFolder()">Открыть папку</button>
      </div>
      <div class="page-status">Работает на 1.20.1 и новее. Лаунчер сам включит пак в options.txt; если игра уже запущена — перезапусти её.</div>
    </div>

    <button class="btn primary full" onclick="saveSettings()">Сохранить настройки</button>`;
  refreshMenuPackStatus();
}

function applyMenuPackStatus(st) {
  const sw = document.getElementById('menu-pack-switch');
  const status = document.getElementById('menu-pack-status');
  if (!sw || !status || !st) return;
  sw.classList.toggle('on', !!st.enabled);
  if (st.enabled) {
    status.textContent = 'Включено — меню Minecraft уже брендовое';
    status.style.color = 'var(--green)';
  } else if (st.installed) {
    status.textContent = 'Пак установлен, но выключен';
    status.style.color = 'var(--text-dim)';
  } else {
    status.textContent = 'Не установлено — нажми «Установить / обновить»';
    status.style.color = 'var(--text-dim)';
  }
}

async function refreshMenuPackStatus() {
  const status = document.getElementById('menu-pack-status');
  if (!status) return;
  try {
    const st = await window.pywebview.api.get_menu_pack_status();
    if (!st || st.ok === false) throw new Error((st && st.error) || 'нет ответа');
    applyMenuPackStatus(st);
  } catch (e) {
    status.textContent = 'Не удалось проверить пак: ' + (e && e.message ? e.message : e);
    status.style.color = 'var(--red)';
  }
}

async function toggleMenuPack(el) {
  const want = !el.classList.contains('on');
  el.classList.toggle('on', want);
  const status = document.getElementById('menu-pack-status');
  if (status) { status.textContent = want ? 'Включаю...' : 'Выключаю...'; status.style.color = 'var(--orange)'; }
  try {
    const st = await window.pywebview.api.set_menu_pack_enabled(want);
    if (!st || st.ok === false) throw new Error((st && st.error) || 'нет ответа');
    applyMenuPackStatus(st);
    showToast(st.enabled ? 'Меню Minecraft включено' : 'Меню Minecraft выключено');
  } catch (e) {
    applyMenuPackStatus({ installed: true, enabled: !want });
    if (status) { status.textContent = 'Ошибка: ' + (e && e.message ? e.message : e); status.style.color = 'var(--red)'; }
  }
}

async function installMenuPack() {
  const status = document.getElementById('menu-pack-status');
  if (status) { status.textContent = 'Устанавливаю ресурспак...'; status.style.color = 'var(--orange)'; }
  try {
    const st = await window.pywebview.api.install_menu_pack();
    if (!st || st.ok === false) throw new Error((st && st.error) || 'нет ответа');
    applyMenuPackStatus(st);
    showToast('Ресурспак установлен');
  } catch (e) {
    if (status) { status.textContent = 'Ошибка: ' + (e && e.message ? e.message : e); status.style.color = 'var(--red)'; }
  }
}

async function openResourcepacksFolder() {
  try {
    const res = await window.pywebview.api.open_resourcepacks_folder();
    if (res && res.ok === false) showToast('Ошибка: ' + res.error);
  } catch (e) {
    showToast('Ошибка: ' + (e && e.message ? e.message : e));
  }
}

async function pickTheme(id) {
  applyTheme(id);
  document.querySelectorAll('.theme-card').forEach(c => c.classList.toggle('active', c.dataset.themeId === id));
  await window.pywebview.api.set_theme(id);
}
async function saveSettings() {
  const ram = (document.getElementById('ram')?.value || '4G').trim() || '4G';
  const show_console = document.getElementById('console-switch').classList.contains('on');
  const cfg = await window.pywebview.api.get_config();
  await window.pywebview.api.save_settings({
    theme: cfg.theme || 'redsea',
    ram,
    show_console,
    version: state.version,
    modloader: state.loader
  });
  showToast('Настройки сохранены');
}

window.addEventListener('pywebviewready', async () => {
  try {
    const cfg = await window.pywebview.api.get_config();
    applyTheme(cfg.theme || 'redsea');
    state.version = cfg.version || state.version;
    state.loader = cfg.modloader || state.loader;
  } catch (e) { applyTheme('redsea'); }
  showPage('launch');
  refreshAccount();
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    try:
        add_server_to_list("BritonTime", "f1.rustix.me:38391")
    except Exception:
        pass
    api = Api()
    window = webview.create_window(
        "BritonLauncher v3.8.1",
        html=HTML,
        js_api=api,
        width=1180,
        height=860,
        min_size=(1000, 720),
        frameless=True,
        easy_drag=False,
        background_color="#0b0d12",
    )
    api._window = window
    webview.start(debug=False)
