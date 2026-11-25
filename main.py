import webview
import minecraft_launcher_lib
import subprocess
import threading
import os
import sys
import shutil
import json
import re
import time
import requests
import nbtlib
from nbtlib import Compound, List, String, Byte
import webbrowser
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

CURRENT_VERSION = "3.11.0"
GITHUB_REPO = "KostyaProcrom/BritonLauncher"
UPDATE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

SITE_URL = "https://kostyaprocrom.github.io/BritonLauncher/"
SUPABASE_URL = "https://lmjizrowtxuwlovbirge.supabase.co"
SUPABASE_KEY = "sb_publishable_R4FofdxSpJhuzDvahy1gKw_Q1Dfmbob"

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
    return {"theme": "glass", "ram": "4G", "nickname": "", "version": "1.20.1",
            "modloader": "Vanilla", "show_console": False, "use_custom_menu": False,
            "custom_accent": "", "custom_bg": "",
            "client_id": "", "redirect_uri": DEFAULT_REDIRECT, "site_account": {}, "ui": 2}


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


def sanitize_hex(value, fallback=""):
    """Оставляет только корректный цвет #rrggbb, иначе — fallback."""
    value = (value or "").strip()
    if re.match(r"^#[0-9a-fA-F]{6}$", value):
        return value.lower()
    return fallback


# ==================== ВХОД ЧЕРЕЗ САЙТ ====================
def supabase_rpc(name, params=None, timeout=20):
    """Вызывает RPC-функцию Supabase публичным ключом."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase не настроен")
    resp = SESSION.post(
        f"{SUPABASE_URL}/rest/v1/rpc/{name}",
        json=params or {},
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=timeout,
    )
    try:
        data = resp.json()
    except Exception:
        data = None
    if resp.status_code >= 400:
        msg = ""
        if isinstance(data, dict):
            msg = data.get("message") or data.get("hint") or data.get("error") or ""
        raise RuntimeError(msg or f"База ответила {resp.status_code}")
    if not isinstance(data, dict):
        raise RuntimeError("Неожиданный ответ базы")
    return data


def fetch_account_status(nick):
    """Актуальный статус аккаунта из базы или None, если база недоступна."""
    nick = (nick or "").strip()
    if not nick:
        return None
    try:
        res = supabase_rpc("bl_account_status", {"p_nick": nick}, timeout=12)
    except Exception:
        return None
    return res if res.get("ok") else None


_site_status_cache = {"nick": "", "at": 0.0, "data": None}


def cached_account_status(nick, max_age=60):
    """Статус аккаунта с кэшем на минуту, чтобы не дёргать базу на каждый клик."""
    nick = (nick or "").strip()
    if not nick:
        return None
    now = time.time()
    cache = _site_status_cache
    if cache["nick"] == nick and now - cache["at"] < max_age:
        return cache["data"]
    data = fetch_account_status(nick)
    cache.update({"nick": nick, "at": now, "data": data})
    return data


def _account_from_profile(profile, token=""):
    profile = profile or {}
    nick = str(profile.get("nick") or "").strip()
    if not re.match(r"^[A-Za-z0-9_]{3,16}$", nick):
        raise ValueError("База вернула некорректный ник")
    account = {
        "nick": nick,
        "role": "admin" if profile.get("role") == "admin" else "player",
        "main": bool(profile.get("main")),
        "muted": bool(profile.get("muted")),
        "banned": bool(profile.get("banned")),
        "ban_reason": profile.get("banReason") or "",
        "login_at": time.strftime("%d.%m.%Y %H:%M"),
        "source": "supabase",
    }
    if token:
        account["token"] = token
    return account


def redeem_launcher_code(code):
    """Погашает одноразовый код BLS2 из базы и возвращает аккаунт."""
    code = (code or "").strip().replace("\n", "").replace("\r", "")
    if not code.startswith("BLS2."):
        raise ValueError("Неверный формат кода")
    try:
        res = supabase_rpc("bl_redeem_launcher_code", {"p_code": code}, timeout=25)
    except Exception as e:
        raise RuntimeError(f"База недоступна: {e}")

    if not res.get("ok"):
        msg = res.get("error") or "Код не принят"
        if res.get("code") == "banned":
            raise PermissionError(msg)
        raise ValueError(msg)

    return _account_from_profile(res.get("profile"))


def login_site_account(nick, password):
    """Прямой вход по нику и паролю через базу Supabase."""
    nick = (nick or "").strip()
    password = password or ""
    if not nick or not password:
        raise ValueError("Введи ник и пароль")
    try:
        res = supabase_rpc(
            "bl_login", {"p_nick": nick, "p_password": password}, timeout=25
        )
    except Exception as e:
        raise RuntimeError(f"База недоступна: {e}")

    if not res.get("ok"):
        msg = res.get("error") or "Не удалось войти"
        if res.get("code") == "banned":
            raise PermissionError(msg)
        raise ValueError(msg)

    return _account_from_profile(res.get("profile"), res.get("token") or "")


config = load_config()
if "ui" not in config:
    # одноразовый переход на новый интерфейс Launchpad
    config["theme"] = "glass"
    config["ui"] = 2
    save_config(config)
config.setdefault("theme", "glass")
config.setdefault("ui", 2)
config.setdefault("use_custom_menu", False)
config.setdefault("custom_accent", "")
config.setdefault("custom_bg", "")
config.setdefault("client_id", "")
config.setdefault("redirect_uri", DEFAULT_REDIRECT)
config.setdefault("site_account", {})
# старый вход по подписанному коду BLS1 больше не поддерживается — сбрасываем его
_legacy_site_account = config.get("site_account") or {}
if _legacy_site_account and _legacy_site_account.get("source") != "supabase":
    config["site_account"] = {}
    save_config(config)
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
                "theme": data.get("theme", config.get("theme", "glass")),
                "ram": sanitize_ram(data.get("ram", config.get("ram", "4G"))),
                "show_console": bool(data.get("show_console", config.get("show_console", False))),
                "version": data.get("version", config.get("version", "1.20.1")),
                "modloader": data.get("modloader", config.get("modloader", "Vanilla")),
                "use_custom_menu": bool(data.get("use_custom_menu", config.get("use_custom_menu", False))),
                "custom_accent": sanitize_hex(data.get("custom_accent", config.get("custom_accent", "")), ""),
                "custom_bg": sanitize_hex(data.get("custom_bg", config.get("custom_bg", "")), ""),
            })
            save_config(config)
        self._set_status("Настройки сохранены", "#22c55e", "✅")
        return {"ok": True}

    def set_theme(self, theme):
        allowed = {"purple", "ocean", "forest", "light", "redsea", "black", "lunar", "glass"}
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

        status = cached_account_status(acc["nick"])
        if status:
            acc["role"] = "admin" if status.get("role") == "admin" else "player"
            acc["main"] = bool(status.get("main"))
            acc["muted"] = bool(status.get("muted"))
            acc["banned"] = bool(status.get("banned"))
            acc["ban_reason"] = status.get("banReason") or ""
            with _cfg_lock:
                config["site_account"] = dict(acc)
                save_config(config)

        return {
            "logged_in": True,
            "nick": acc.get("nick", ""),
            "role": acc.get("role", "player"),
            "main": bool(acc.get("main")),
            "muted": bool(acc.get("muted")),
            "banned": bool(acc.get("banned")),
            "ban_reason": acc.get("ban_reason", ""),
            "login_at": acc.get("login_at", ""),
            "site_url": SITE_URL,
        }

    def site_open(self):
        try:
            webbrowser.open(SITE_URL + "#account")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _store_site_account(self, acc):
        with _cfg_lock:
            config["site_account"] = acc
            config["nickname"] = acc["nick"]
            save_config(config)
        _site_status_cache.update({"nick": acc["nick"], "at": time.time(), "data": None})
        save_nickname(acc["nick"])
        self._set_status(f"Вход в аккаунт: {acc['nick']}", "#22c55e", "✅")
        return {"ok": True, **acc}

    def site_login(self, code):
        code = (code or "").strip()
        try:
            acc = redeem_launcher_code(code)
        except PermissionError as e:
            return {"ok": False, "error": str(e)}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"Не удалось прочитать код: {e}"}
        return self._store_site_account(acc)

    def site_password_login(self, nick, password):
        try:
            acc = login_site_account(nick, password)
        except PermissionError as e:
            return {"ok": False, "error": str(e)}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"Не удалось войти: {e}"}
        return self._store_site_account(acc)

    def site_logout(self):
        with _cfg_lock:
            token = (config.get("site_account") or {}).get("token") or ""
            config["site_account"] = {}
            save_config(config)
        if token:
            try:
                supabase_rpc("bl_logout", {"p_token": token}, timeout=10)
            except Exception:
                pass
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

            with _cfg_lock:
                site_nick = (config.get("site_account") or {}).get("nick") or ""
            if site_nick:
                status = fetch_account_status(site_nick)
                if status and status.get("banned"):
                    reason = status.get("banReason") or "без причины"
                    self._set_status(f"Аккаунт забанен: {reason}", "#ef4444", "🚫")
                    self._safe_eval("setPlayBusy(false);")
                    return

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
<html lang="ru" data-theme="glass">
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
.brand-logo { width: 34px; height: 34px; border-radius: 10px; background: url("data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTI4IiBoZWlnaHQ9IjEyOCIgdmlld0JveD0iMCAwIDEyOCAxMjgiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CiAgPGRlZnM+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImJnIiB4MT0iMCIgeTE9IjAiIHgyPSIxIiB5Mj0iMSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzFlMjkzYiIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwZjE3MmEiLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImdyYXNzIiB4MT0iMCIgeTE9IjAiIHgyPSIwIiB5Mj0iMSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzVkOWIzZiIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM0YTdlMzIiLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImRpcnQiIHgxPSIwIiB5MT0iMCIgeDI9IjAiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjOGI1YTJiIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzZiM2UxYSIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0iZ29sZCIgeDE9IjAiIHkxPSIwIiB4Mj0iMSIgeTI9IjEiPgogICAgICA8c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNmYmJmMjQiLz4KICAgICAgPHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjZDk3NzA2Ii8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogIDwvZGVmcz4KICA8cmVjdCB4PSI2IiB5PSI2IiB3aWR0aD0iMTE2IiBoZWlnaHQ9IjExNiIgcng9IjI4IiBmaWxsPSJ1cmwoI2JnKSIgc3Ryb2tlPSIjYzVhMDU5IiBzdHJva2Utd2lkdGg9IjMiLz4KICA8Zz4KICAgIDxyZWN0IHg9IjM0IiB5PSIzNCIgd2lkdGg9IjYwIiBoZWlnaHQ9IjYwIiBmaWxsPSJ1cmwoI2RpcnQpIiBzdHJva2U9IiM1ZDQwMzciIHN0cm9rZS13aWR0aD0iMyIvPgogICAgPHJlY3QgeD0iMzQiIHk9IjM0IiB3aWR0aD0iNjAiIGhlaWdodD0iMTQiIGZpbGw9InVybCgjZ3Jhc3MpIiBzdHJva2U9IiMzZTZiMjEiIHN0cm9rZS13aWR0aD0iMyIvPgogICAgPHJlY3QgeD0iNDIiIHk9IjQ4IiB3aWR0aD0iOCIgaGVpZ2h0PSI4IiBmaWxsPSIjM2U2YjIxIi8+CiAgICA8cmVjdCB4PSI1OCIgeT0iNDgiIHdpZHRoPSI4IiBoZWlnaHQ9IjgiIGZpbGw9IiMzZTZiMjEiLz4KICAgIDxyZWN0IHg9Ijc0IiB5PSI0OCIgd2lkdGg9IjgiIGhlaWdodD0iOCIgZmlsbD0iIzNlNmIyMSIvPgogIDwvZz4KICA8ZyBmaWxsPSJ1cmwoI2dvbGQpIiBzdHJva2U9IiNiNDUzMDkiIHN0cm9rZS13aWR0aD0iMi41IiBzdHJva2UtbGluZWpvaW49InJvdW5kIj4KICAgIDxwYXRoIGQ9Ik01MiA2OCBMNjQgNTYgTDcwIDUwIEw3NiA1NiBMODIgNjggTDc5IDgyIEw3MCA5MCBMNTggOTAgTDQ5IDgyIFoiLz4KICAgIDxsaW5lIHgxPSI2NCIgeTE9IjU2IiB4Mj0iNzkiIHkyPSI2OCIgc3Ryb2tlPSIjYjQ1MzA5IiBzdHJva2Utd2lkdGg9IjMiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgogIDwvZz4KPC9zdmc+") center/cover no-repeat; display: grid; place-items: center; box-shadow: 0 6px 22px var(--accent-soft); }
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
.color-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.color-field { display: flex; align-items: center; gap: 10px; background: rgba(128,128,128,0.08); border: 1px solid var(--line); border-radius: 12px; padding: 9px 12px; transition: opacity 0.18s; }
.color-field.off { opacity: 0.45; }
.color-field span { font-size: 12px; color: var(--text-dim); font-weight: 700; }
.color-field input[type="color"] { width: 40px; height: 30px; padding: 0; margin: 0; border: none; background: none; border-radius: 8px; cursor: pointer; flex-shrink: 0; }
.color-field input[type="color"]::-webkit-color-swatch-wrapper { padding: 0; }
.color-field input[type="color"]::-webkit-color-swatch { border: 1px solid rgba(255,255,255,0.28); border-radius: 8px; }
.color-field code { margin-left: auto; font-size: 11px; color: var(--text-mute); font-family: 'Consolas', 'JetBrains Mono', monospace; }
.swatches { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; align-items: center; }
.swatch { width: 28px; height: 28px; padding: 0; border-radius: 9px; border: 1px solid rgba(255,255,255,0.22); cursor: pointer; transition: transform 0.15s, box-shadow 0.15s; }
.swatch:hover { transform: translateY(-2px); box-shadow: 0 6px 14px rgba(0,0,0,0.35); }
.swatch-reset { background: transparent; color: var(--text-dim); font-size: 15px; line-height: 1; }
.swatch-reset:hover { color: var(--text); }
#custom-menu-iframe { width: 100%; height: 100%; border: none; background: transparent; display: none; }

/* ================= Launchpad redesign ================= */
:root[data-theme="lunar"] { --bg:#0a0c11; --bg-soft:#10141b; --glass:#0d1016; --glass-border:#1e242f; --text:#eef2f8; --text-dim:#8b93a3; --text-mute:#5a6272; --grad-1:#22c55e; --grad-2:#16a34a; --accent:#22c55e; --accent-soft:rgba(34,197,94,0.14); --green:#22c55e; --orange:#f59e0b; --red:#ef4444; --body-bg: radial-gradient(circle at 18% -10%, rgba(34,197,94,0.10), transparent 45%), radial-gradient(circle at 100% 0%, rgba(59,130,246,0.07), transparent 42%), #0a0c11; }
:root { --panel:#10141b; --panel-2:#141922; --line:#1e242f; }

#app { display: flex; height: 100vh; overflow: hidden; }
.rail { width: 64px; flex: 0 0 64px; display: flex; flex-direction: column; align-items: center; gap: 5px; padding: 10px 0 10px; background: #0b0e13; border-right: 1px solid var(--line); }
.rail-logo { width: 34px; height: 34px; border-radius: 10px; background: url("data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTI4IiBoZWlnaHQ9IjEyOCIgdmlld0JveD0iMCAwIDEyOCAxMjgiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CiAgPGRlZnM+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImJnIiB4MT0iMCIgeTE9IjAiIHgyPSIxIiB5Mj0iMSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzFlMjkzYiIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwZjE3MmEiLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImdyYXNzIiB4MT0iMCIgeTE9IjAiIHgyPSIwIiB5Mj0iMSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzVkOWIzZiIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM0YTdlMzIiLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImRpcnQiIHgxPSIwIiB5MT0iMCIgeDI9IjAiIHkyPSIxIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjOGI1YTJiIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzZiM2UxYSIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0iZ29sZCIgeDE9IjAiIHkxPSIwIiB4Mj0iMSIgeTI9IjEiPgogICAgICA8c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNmYmJmMjQiLz4KICAgICAgPHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjZDk3NzA2Ii8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogIDwvZGVmcz4KICA8cmVjdCB4PSI2IiB5PSI2IiB3aWR0aD0iMTE2IiBoZWlnaHQ9IjExNiIgcng9IjI4IiBmaWxsPSJ1cmwoI2JnKSIgc3Ryb2tlPSIjYzVhMDU5IiBzdHJva2Utd2lkdGg9IjMiLz4KICA8Zz4KICAgIDxyZWN0IHg9IjM0IiB5PSIzNCIgd2lkdGg9IjYwIiBoZWlnaHQ9IjYwIiBmaWxsPSJ1cmwoI2RpcnQpIiBzdHJva2U9IiM1ZDQwMzciIHN0cm9rZS13aWR0aD0iMyIvPgogICAgPHJlY3QgeD0iMzQiIHk9IjM0IiB3aWR0aD0iNjAiIGhlaWdodD0iMTQiIGZpbGw9InVybCgjZ3Jhc3MpIiBzdHJva2U9IiMzZTZiMjEiIHN0cm9rZS13aWR0aD0iMyIvPgogICAgPHJlY3QgeD0iNDIiIHk9IjQ4IiB3aWR0aD0iOCIgaGVpZ2h0PSI4IiBmaWxsPSIjM2U2YjIxIi8+CiAgICA8cmVjdCB4PSI1OCIgeT0iNDgiIHdpZHRoPSI4IiBoZWlnaHQ9IjgiIGZpbGw9IiMzZTZiMjEiLz4KICAgIDxyZWN0IHg9Ijc0IiB5PSI0OCIgd2lkdGg9IjgiIGhlaWdodD0iOCIgZmlsbD0iIzNlNmIyMSIvPgogIDwvZz4KICA8ZyBmaWxsPSJ1cmwoI2dvbGQpIiBzdHJva2U9IiNiNDUzMDkiIHN0cm9rZS13aWR0aD0iMi41IiBzdHJva2UtbGluZWpvaW49InJvdW5kIj4KICAgIDxwYXRoIGQ9Ik01MiA2OCBMNjQgNTYgTDcwIDUwIEw3NiA1NiBMODIgNjggTDc5IDgyIEw3MCA5MCBMNTggOTAgTDQ5IDgyIFoiLz4KICAgIDxsaW5lIHgxPSI2NCIgeTE9IjU2IiB4Mj0iNzkiIHkyPSI2OCIgc3Ryb2tlPSIjYjQ1MzA5IiBzdHJva2Utd2lkdGg9IjMiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgogIDwvZz4KPC9zdmc+") center/cover no-repeat; display: grid; place-items: center; box-shadow: 0 6px 18px rgba(34,197,94,0.22); margin-bottom: 6px; flex-shrink: 0; }
.rail-sep { width: 26px; height: 1px; background: var(--line); margin: 4px 0; flex-shrink: 0; }
.rail-item { width: 42px; height: 42px; border: none; border-radius: 12px; background: transparent; color: #6e7688; display: grid; place-items: center; cursor: pointer; transition: all 0.15s; position: relative; flex-shrink: 0; }
.rail-item .ico { width: 20px; height: 20px; }
.rail-item:hover { background: #151a22; color: #e6ebf4; }
.rail-item.active { background: var(--accent-soft); color: var(--accent); }
.rail-item.active::before { content: ''; position: absolute; left: -11px; top: 11px; width: 3px; height: 20px; border-radius: 0 3px 3px 0; background: var(--accent); }
.rail-bottom { margin-top: auto; display: flex; flex-direction: column; align-items: center; gap: 5px; }
.rail-ver { font-size: 9px; font-weight: 800; letter-spacing: 0.5px; color: var(--text-mute); margin-top: 4px; }

.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
#titlebar { height: 52px; flex-shrink: 0; padding: 0 6px 0 14px; gap: 8px; background: #0b0e13; border-bottom: 1px solid var(--line); display: flex; align-items: center; }
.tb-brand { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.tb-brand .brand-logo { width: 26px; height: 26px; border-radius: 8px; font-size: 13px; box-shadow: 0 4px 14px rgba(34,197,94,0.25); }
.tb-brand .name { font-weight: 800; font-size: 13.5px; letter-spacing: 0.2px; white-space: nowrap; }
.tb-brand .chev { color: var(--text-mute); width: 13px; height: 13px; }
.tb-sep { width: 1px; height: 20px; background: var(--line); margin: 0 6px; flex-shrink: 0; }
.tb-nav { display: flex; align-items: center; gap: 6px; color: var(--text-dim); font-size: 12.5px; min-width: 0; }
.tb-back { width: 28px; height: 28px; border: none; border-radius: 8px; background: transparent; color: var(--text-mute); font-size: 17px; font-weight: 800; cursor: pointer; display: grid; place-items: center; padding-bottom: 2px; flex-shrink: 0; }
.tb-back:hover { background: #171c25; color: var(--text); }
.tb-crumb { font-weight: 700; color: #cfd6e2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.tb-icon { width: 32px; height: 32px; border: none; border-radius: 9px; background: transparent; color: var(--text-dim); display: grid; place-items: center; cursor: pointer; position: relative; transition: all 0.15s; }
.tb-icon:hover { background: #171c25; color: var(--text); }
.tb-icon .ico { width: 17px; height: 17px; }
.tb-icon .ping { position: absolute; top: 7px; right: 8px; width: 6px; height: 6px; border-radius: 50%; background: var(--orange); box-shadow: 0 0 6px var(--orange); }
.tb-version { font-size: 10px; font-weight: 800; color: var(--text-mute); padding: 3px 7px; border-radius: 999px; background: #141922; border: 1px solid var(--line); margin-right: 2px; }
.title-account { margin: 0 2px 0 4px; display: flex; align-items: center; gap: 7px; padding: 4px 10px 4px 4px; border-radius: 999px; background: #141922; border: 1px solid var(--line); color: var(--text); font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit; transition: all 0.15s; }
.title-account:hover { border-color: #2e3644; background: #171d27; }
.title-account .avatar { width: 24px; height: 24px; border-radius: 50%; background: linear-gradient(135deg, #22c55e, #0f7a3a); display: grid; place-items: center; font-size: 11px; font-weight: 900; color: #fff; flex-shrink: 0; }
.title-account .dot { width: 7px; height: 7px; border-radius: 50%; background: #3a4150; flex-shrink: 0; }
.title-account.logged .dot { background: var(--green); box-shadow: 0 0 7px var(--green); }
.title-account .role { display: none; }
.win-btns { display: flex; gap: 2px; margin-left: 2px; }
.win-btn { width: 36px; height: 32px; border-radius: 8px; font-size: 12px; }
#content { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; padding: 22px 26px 32px; background: transparent; border: none; border-radius: 0; backdrop-filter: none; }
#content::-webkit-scrollbar { width: 10px; }
#content::-webkit-scrollbar-thumb { background: #1e242f; border-radius: 10px; border: 2px solid #0a0c11; }
#content::-webkit-scrollbar-track { background: transparent; }

.lp { max-width: 1440px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; }
.lp-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; animation: fadeUp 0.3s ease both; }
.lp-welcome { font-size: 21px; font-weight: 800; letter-spacing: -0.2px; display: flex; align-items: center; gap: 8px; }
.lp-welcome .nick { color: #fff; }
.lp-welcome .guest { color: var(--text-dim); font-weight: 700; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 8px rgba(34,197,94,0.8); flex-shrink: 0; }
.lp-head-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.online-pill { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 700; color: #b8c0ce; white-space: nowrap; }
.quick-tiles { display: flex; gap: 8px; }
.qtile { width: 42px; height: 42px; border: none; border-radius: 12px; display: grid; place-items: center; color: #fff; cursor: pointer; background: linear-gradient(135deg, var(--q1), var(--q2)); box-shadow: 0 6px 16px rgba(0,0,0,0.35); transition: transform 0.15s, filter 0.15s; }
.qtile:hover { transform: translateY(-2px); filter: brightness(1.08); }
.qtile .ico { width: 19px; height: 19px; }

.lp-grid { display: grid; grid-template-columns: minmax(0, 1fr) 296px; gap: 18px; align-items: start; }
.lp-main { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.lp-side { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.lp-hero { position: relative; height: 300px; border-radius: 18px; overflow: hidden; background: #070a10; border: 1px solid var(--line); box-shadow: 0 18px 40px rgba(0,0,0,0.35); animation: heroIn 0.42s cubic-bezier(0.22, 0.8, 0.3, 1) both; }
.hero-art { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.hero-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; padding: 22px; }
.launch-btn { min-width: 340px; padding: 13px 36px 11px; border: none; border-radius: 12px; background: linear-gradient(180deg, #31e273 0%, #17b457 55%, #0f9d49 100%); color: #fff; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 2px; box-shadow: 0 16px 34px rgba(34,197,94,0.32), inset 0 1px 0 rgba(255,255,255,0.35), inset 0 -2px 0 rgba(0,0,0,0.18); transition: transform 0.15s, filter 0.15s; font-family: inherit; }
.launch-btn:hover { transform: translateY(-2px); filter: brightness(1.05); }
.launch-btn:active { transform: translateY(0); }
.launch-btn:disabled { filter: grayscale(0.45) brightness(0.85); cursor: wait; transform: none; }
.launch-btn.busy:disabled { filter: none; cursor: progress; }
.launch-title { font-size: 23px; font-weight: 900; letter-spacing: 0.7px; text-shadow: 0 2px 4px rgba(0,0,0,0.28); line-height: 1.1; }
.launch-sub { font-size: 11.5px; font-weight: 600; opacity: 0.95; display: flex; align-items: center; gap: 5px; }
.launch-sub b { font-weight: 800; }
.launch-sub .sep { opacity: 0.55; }
.hero-gear { position: absolute; right: 12px; bottom: 12px; width: 34px; height: 34px; border-radius: 10px; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.13); color: #d5dbe6; display: grid; place-items: center; cursor: pointer; transition: all 0.15s; z-index: 2; }
.hero-gear:hover { background: rgba(255,255,255,0.15); color: #fff; }
.hero-gear .ico { width: 17px; height: 17px; }
.hero-note { position: absolute; left: 14px; bottom: 14px; font-size: 10.5px; color: rgba(255,255,255,0.42); z-index: 2; }
.hero-config { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(5,8,12,0.72); backdrop-filter: blur(6px); z-index: 5; opacity: 0; visibility: hidden; pointer-events: none; transition: opacity 0.18s ease, visibility 0.18s ease; }
.hero-config.open { opacity: 1; visibility: visible; pointer-events: auto; }
.hc-panel { width: min(520px, calc(100% - 38px)); background: #0f131a; border: 1px solid #262d3a; border-radius: 16px; padding: 16px; box-shadow: 0 24px 60px rgba(0,0,0,0.55); transform: translateY(10px) scale(0.98); transition: transform 0.2s ease; }
.hero-config.open .hc-panel { transform: translateY(0) scale(1); }
.hc-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 800; margin-bottom: 12px; }
.hc-close { width: 26px; height: 26px; border: none; border-radius: 8px; background: #171c25; color: var(--text-dim); cursor: pointer; font-size: 12px; }
.hc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.hc-field label { display: block; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: var(--text-mute); font-weight: 800; margin-bottom: 5px; }
.hc-field input, .hc-field select { padding: 9px 11px; border-radius: 9px; font-size: 12px; }
.hc-foot { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.hc-foot .btn { padding: 9px 14px; font-size: 11.5px; border-radius: 9px; }
.hc-console { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 11px; background: var(--bg-soft); border: 1px solid var(--glass-border); border-radius: 9px; font-size: 11.5px; }
.hc-console .switch { width: 40px; height: 22px; }
.hc-console .switch::after { width: 16px; height: 16px; }
.hc-console .switch.on::after { left: 21px; }
.launch-status { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--text-dim); padding: 0 2px; min-height: 18px; }
.launch-status .status-dot { width: 7px; height: 7px; }
#status-text { flex: 0 1 auto; }

.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 14px; animation: fadeUp 0.32s ease both; }
.lp-side .panel:nth-child(2) { animation-delay: 0.05s; }
.lp-side .panel:nth-child(3) { animation-delay: 0.1s; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; font-weight: 800; letter-spacing: 0.2px; margin-bottom: 11px; }
.panel-head .muted { font-size: 10.5px; color: var(--text-mute); font-weight: 600; }
.panel-head .link { font-size: 10.5px; color: var(--text-dim); background: none; border: none; cursor: pointer; font-family: inherit; font-weight: 700; }
.panel-head .link:hover { color: var(--text); }
.account-body { display: flex; flex-direction: column; gap: 10px; }
.acct-row { display: flex; align-items: center; gap: 10px; }
.acct-ava { width: 38px; height: 38px; border-radius: 10px; background: linear-gradient(135deg, #22c55e, #0f7a3a); display: grid; place-items: center; font-weight: 900; font-size: 16px; color: #fff; flex-shrink: 0; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.12); }
.acct-name { font-size: 13.5px; font-weight: 800; display: flex; align-items: center; gap: 6px; }
.acct-meta { font-size: 10.5px; color: var(--text-dim); margin-top: 2px; }
.badge { display: inline-block; padding: 1px 6px; border-radius: 999px; font-size: 8.5px; font-weight: 900; letter-spacing: 0.5px; text-transform: uppercase; }
.badge.role { background: rgba(34,197,94,0.14); color: #4ade80; }
.badge.mute { background: rgba(250,204,21,0.14); color: #facc15; }
.acct-actions { display: flex; gap: 7px; flex-wrap: wrap; }
.acct-actions .btn { flex: 1 1 auto; padding: 8px 10px; font-size: 11px; border-radius: 9px; }
.site-login-row { display: flex; flex-direction: column; gap: 7px; }
.site-login-row input { padding: 9px 10px; border-radius: 9px; font-size: 11px; }
.site-login-row .btn { padding: 9px 10px; font-size: 11px; border-radius: 9px; }
.site-hint { color: var(--text-mute); font-size: 10px; line-height: 1.45; }
.server-name { font-size: 13px; font-weight: 800; display: flex; align-items: center; gap: 7px; }
.server-desc { font-size: 10.5px; color: var(--text-dim); margin: 4px 0 9px; }
.server-ip { font-family: Consolas, 'Courier New', monospace; font-size: 11px; color: var(--text-dim); background: #0b0e13; border: 1px solid var(--line); padding: 7px 9px; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
.server-ip button { background: none; border: none; color: var(--text-mute); cursor: pointer; display: grid; place-items: center; padding: 2px; }
.server-ip button:hover { color: var(--text); }
.server-ip .ico { width: 14px; height: 14px; }
.server-panel .btn { width: 100%; padding: 9px 12px; font-size: 11.5px; border-radius: 9px; }
.status-panel { display: flex; flex-direction: column; gap: 6px; }
.status-panel .status-line { display: flex; align-items: flex-start; gap: 8px; font-size: 10.5px; line-height: 1.45; }
.status-panel .status-dot { margin-top: 3px; }

.lp-news-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 2px; }
.lp-news-head h2 { font-size: 15px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
.lp-news-head .count { font-size: 10px; font-weight: 800; color: var(--text-mute); background: #141922; border: 1px solid var(--line); border-radius: 999px; padding: 1px 7px; }
.lp-news-head .link { background: none; border: none; color: var(--text-dim); font-size: 10.5px; font-weight: 700; cursor: pointer; font-family: inherit; }
.lp-news-head .link:hover { color: var(--text); }
.news-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.lp-footer { margin-top: 4px; padding: 10px 0 2px; text-align: center; font-size: 10.5px; font-weight: 700; letter-spacing: 0.3px; color: var(--text-mute); }
.news-card { position: relative; height: 168px; border-radius: 15px; overflow: hidden; border: 1px solid var(--line); cursor: pointer; background: #0d1017; text-align: left; font-family: inherit; color: #fff; transition: transform 0.15s, border-color 0.15s; padding: 0; animation: fadeUp 0.34s ease both; }
.news-card:nth-child(2) { animation-delay: 0.06s; }
.news-card:hover { transform: translateY(-2px); border-color: #2b3340; }
.news-cover { position: absolute; inset: 0; padding: 16px; display: flex; flex-direction: column; justify-content: flex-end; gap: 3px; }
.news-card.green .news-cover { background: radial-gradient(circle at 85% 15%, rgba(34,197,94,0.35), transparent 55%), linear-gradient(135deg, #0c2b1c 0%, #08130e 70%); }
.news-card.red .news-cover { background: radial-gradient(circle at 85% 15%, rgba(239,68,68,0.32), transparent 55%), linear-gradient(135deg, #2b0c12 0%, #120609 70%); }
.news-card.blue .news-cover { background: radial-gradient(circle at 85% 15%, rgba(59,130,246,0.32), transparent 55%), linear-gradient(135deg, #0c162b 0%, #070b13 70%); }
.news-tag { font-size: 9px; letter-spacing: 1.2px; text-transform: uppercase; color: rgba(255,255,255,0.5); font-weight: 800; }
.news-title { font-size: 17px; font-weight: 800; line-height: 1.15; max-width: 95%; }
.news-desc { font-size: 10.5px; color: rgba(255,255,255,0.62); max-width: 92%; }
.news-arrow { position: absolute; right: 12px; bottom: 12px; width: 26px; height: 26px; border-radius: 50%; background: rgba(255,255,255,0.12); display: grid; place-items: center; color: #fff; }
.news-arrow .ico { width: 13px; height: 13px; }
.news-big { position: absolute; right: 18px; top: 12px; font-size: 34px; font-weight: 900; letter-spacing: -1px; color: rgba(255,255,255,0.10); }
.news-card:hover .news-arrow { background: rgba(255,255,255,0.2); }

.page-title { font-size: 22px; }
.page-sub { font-size: 12px; margin-bottom: 18px; }
.settings-section, .admin-card, .result-item { background: var(--panel); border-color: var(--line); }
.result-item:hover { border-color: var(--accent); }
.btn { border-radius: 10px; padding: 11px 18px; font-size: 12px; }
.btn-play { border-radius: 12px; }
.theme-card { background: #0c0f15; }
input, select { background: #0c0f15; border-color: var(--line); border-radius: 10px; }
.page-status { padding: 8px 0; }
@media (max-width: 900px) { .lp-grid { grid-template-columns: 1fr; } .lp-side { display: grid; grid-template-columns: 1fr 1fr; } .news-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .lp-side { grid-template-columns: 1fr; } .tb-version, .online-pill { display: none; } .launch-btn { min-width: 260px; } }

.page-anim { animation: pageIn 0.26s ease both; }
@keyframes pageIn { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: none; } }
@keyframes fadeUp { from { opacity: 0; translate: 0 10px; } to { opacity: 1; translate: 0 0; } }
@keyframes heroIn { from { opacity: 0; transform: translateY(14px) scale(0.992); } to { opacity: 1; transform: none; } }
.launch-btn.busy { animation: launchPulse 1.4s ease-in-out infinite; }
@keyframes launchPulse { 0%, 100% { box-shadow: 0 16px 34px rgba(34,197,94,0.32), inset 0 1px 0 rgba(255,255,255,0.35); } 50% { box-shadow: 0 16px 44px rgba(34,197,94,0.55), inset 0 1px 0 rgba(255,255,255,0.35); } }
.rail-item, .tb-icon, .qtile, .news-card, .launch-btn, .btn, .switch, .theme-card { will-change: transform; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; scroll-behavior: auto !important; }
}

/* ================= Obsidian Gold — визуал сайта ================= */
:root[data-theme="lunar"] {
  --bg: #06080c;
  --bg-soft: #0a0f16;
  --glass: rgba(9, 13, 19, 0.92);
  --glass-border: rgba(255, 255, 255, 0.075);
  --panel: #0b1017;
  --panel-2: #0f1620;
  --line: rgba(255, 255, 255, 0.075);
  --text: #f3f6fa;
  --text-dim: #9ba7b8;
  --text-mute: #68758a;
  --gold: #e6b45c;
  --gold-hi: #f8dda0;
  --grad-1: #f8dda0;
  --grad-2: #e6b45c;
  --accent: #e6b45c;
  --accent-soft: rgba(230, 180, 92, 0.12);
  --green: #3ddc84;
  --orange: #e6b45c;
  --red: #f87171;
  --on-accent: #1b1305;
  --body-bg:
    radial-gradient(1000px 620px at 6% -12%, rgba(230, 180, 92, 0.12), transparent 62%),
    radial-gradient(820px 520px at 100% 0%, rgba(61, 220, 132, 0.055), transparent 58%),
    radial-gradient(900px 700px at 50% 115%, rgba(230, 180, 92, 0.045), transparent 60%),
    #06080c;
}

:root[data-theme="lunar"] body {
  font-family: 'Inter', 'Segoe UI Variable Display', 'Segoe UI', system-ui, -apple-system, sans-serif;
}
:root[data-theme="lunar"] body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.022) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.022) 1px, transparent 1px);
  background-size: 64px 64px;
  -webkit-mask-image: radial-gradient(ellipse 85% 60% at 50% 0%, #000 18%, transparent 76%);
  mask-image: radial-gradient(ellipse 85% 60% at 50% 0%, #000 18%, transparent 76%);
}
:root[data-theme="lunar"] #app { position: relative; z-index: 1; }

/* Каркас */
:root[data-theme="lunar"] .rail,
:root[data-theme="lunar"] #titlebar {
  background: rgba(6, 8, 12, 0.88);
  border-color: var(--line);
}
:root[data-theme="lunar"] #titlebar { border-bottom: 1px solid var(--line); position: relative; }
:root[data-theme="lunar"] #titlebar::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(230, 180, 92, 0.35), transparent);
  pointer-events: none;
}
:root[data-theme="lunar"] .rail { border-right: 1px solid var(--line); }
:root[data-theme="lunar"] .rail-logo,
:root[data-theme="lunar"] .tb-brand .brand-logo {
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(230, 180, 92, 0.3), 0 10px 26px -12px rgba(230, 180, 92, 0.55);
}
:root[data-theme="lunar"] .tb-brand .name b { color: var(--accent); font-weight: 800; }
:root[data-theme="lunar"] .rail-item:hover,
:root[data-theme="lunar"] .tb-icon:hover,
:root[data-theme="lunar"] .tb-back:hover { background: rgba(255, 255, 255, 0.05); color: var(--text); }
:root[data-theme="lunar"] .rail-item.active { background: rgba(230, 180, 92, 0.13); color: var(--gold-hi); }
:root[data-theme="lunar"] .rail-item.active::before {
  background: linear-gradient(180deg, var(--gold-hi), #c08c33);
}
:root[data-theme="lunar"] .tb-version {
  background: var(--panel-2);
  border-color: var(--line);
  color: var(--text-mute);
}
:root[data-theme="lunar"] .tb-sep { background: var(--line); }

/* Аккаунт в шапке */
:root[data-theme="lunar"] .title-account {
  background: rgba(255, 255, 255, 0.035);
  border-color: var(--line);
}
:root[data-theme="lunar"] .title-account:hover {
  border-color: rgba(230, 180, 92, 0.5);
  background: rgba(230, 180, 92, 0.08);
}
:root[data-theme="lunar"] .title-account.logged .dot {
  background: var(--green);
  box-shadow: 0 0 8px rgba(61, 220, 132, 0.8);
}
:root[data-theme="lunar"] .title-account .avatar,
:root[data-theme="lunar"] .acct-ava {
  background: linear-gradient(135deg, var(--gold-hi), #c9973f);
  color: #1b1305;
  box-shadow: 0 8px 18px -8px rgba(230, 180, 92, 0.6), inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}

/* Launchpad */
:root[data-theme="lunar"] .lp-welcome { letter-spacing: -0.3px; }
:root[data-theme="lunar"] .lp-welcome .nick { color: var(--gold-hi); }
:root[data-theme="lunar"] .live-dot {
  background: var(--green);
  box-shadow: 0 0 10px rgba(61, 220, 132, 0.8);
}
:root[data-theme="lunar"] .online-pill { color: var(--text-dim); }
:root[data-theme="lunar"] .qtile {
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid var(--line);
  color: var(--gold);
  box-shadow: none;
}
:root[data-theme="lunar"] .qtile:hover {
  background: rgba(230, 180, 92, 0.12);
  border-color: rgba(230, 180, 92, 0.45);
  color: var(--gold-hi);
}
:root[data-theme="lunar"] .lp-hero {
  border-color: rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  box-shadow: 0 30px 70px -40px rgba(0, 0, 0, 0.95), 0 0 90px -46px rgba(230, 180, 92, 0.55);
}
:root[data-theme="lunar"] .lp-hero::after {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(230, 180, 92, 0.55), transparent);
  z-index: 3;
  pointer-events: none;
}
:root[data-theme="lunar"] .launch-btn {
  background: linear-gradient(165deg, var(--gold-hi) 0%, var(--gold) 52%, #c08c33 100%);
  color: #1b1305;
  border-radius: 13px;
  box-shadow: 0 18px 40px -16px rgba(230, 180, 92, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.55), inset 0 -2px 0 rgba(0, 0, 0, 0.16);
}
:root[data-theme="lunar"] .launch-btn:hover { filter: brightness(1.05); }
:root[data-theme="lunar"] .launch-btn:disabled {
  background: #141a23;
  color: var(--text-mute);
  box-shadow: none;
  filter: none;
}
:root[data-theme="lunar"] .launch-btn.busy { animation: launchPulseGold 1.5s ease-in-out infinite; }
@keyframes launchPulseGold {
  0%, 100% { box-shadow: 0 16px 34px -14px rgba(230, 180, 92, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.5); }
  50% { box-shadow: 0 18px 50px -12px rgba(230, 180, 92, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.5); }
}
:root[data-theme="lunar"] .launch-title { letter-spacing: 1px; text-shadow: 0 1px 0 rgba(255, 255, 255, 0.3); }
:root[data-theme="lunar"] .launch-sub { opacity: 0.82; }
:root[data-theme="lunar"] .hero-note { color: rgba(255, 255, 255, 0.4); }
:root[data-theme="lunar"] .hero-gear {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.14);
  color: var(--gold-hi);
}
:root[data-theme="lunar"] .hero-gear:hover { background: rgba(230, 180, 92, 0.18); color: #fff; }
:root[data-theme="lunar"] .hc-panel {
  background: var(--panel);
  border-color: rgba(255, 255, 255, 0.12);
  border-radius: 18px;
}
:root[data-theme="lunar"] .hc-close { background: rgba(255, 255, 255, 0.06); }
:root[data-theme="lunar"] .hc-close:hover { background: rgba(230, 180, 92, 0.15); color: var(--gold-hi); }
:root[data-theme="lunar"] .launch-status { color: var(--text-dim); }

/* Панели справа */
:root[data-theme="lunar"] .panel {
  background:
    linear-gradient(155deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.006) 60%),
    var(--panel);
  border-color: var(--line);
  border-radius: 16px;
}
:root[data-theme="lunar"] .panel-head .link:hover,
:root[data-theme="lunar"] .lp-news-head .link:hover { color: var(--gold); }
:root[data-theme="lunar"] .acct-name .badge.role,
:root[data-theme="lunar"] .badge.role { background: rgba(230, 180, 92, 0.14); color: var(--gold-hi); }
:root[data-theme="lunar"] .server-ip {
  background: #070b11;
  border-color: var(--line);
  border-radius: 9px;
}
:root[data-theme="lunar"] .server-ip button:hover { color: var(--gold); }

/* Новости */
:root[data-theme="lunar"] .news-card {
  background: var(--panel);
  border-color: var(--line);
  border-radius: 16px;
}
:root[data-theme="lunar"] .news-card:hover { border-color: rgba(230, 180, 92, 0.4); }
:root[data-theme="lunar"] .news-card.green .news-cover {
  background:
    radial-gradient(circle at 85% 15%, rgba(230, 180, 92, 0.34), transparent 55%),
    linear-gradient(135deg, #221908 0%, #0a0803 74%);
}
:root[data-theme="lunar"] .news-card.red .news-cover {
  background:
    radial-gradient(circle at 85% 15%, rgba(61, 220, 132, 0.18), transparent 55%),
    linear-gradient(135deg, #0a1a14 0%, #050b09 74%);
}
:root[data-theme="lunar"] .news-card.blue .news-cover {
  background:
    radial-gradient(circle at 85% 15%, rgba(230, 180, 92, 0.22), transparent 55%),
    linear-gradient(135deg, #131722 0%, #070a10 74%);
}
:root[data-theme="lunar"] .news-tag { color: rgba(248, 221, 160, 0.62); }
:root[data-theme="lunar"] .news-big { color: rgba(255, 255, 255, 0.085); }
:root[data-theme="lunar"] .news-arrow { background: rgba(255, 255, 255, 0.1); }
:root[data-theme="lunar"] .news-card:hover .news-arrow { background: rgba(230, 180, 92, 0.28); }

/* Кнопки, поля, страницы */
:root[data-theme="lunar"] .btn {
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--line);
  color: var(--text);
  border-radius: 11px;
}
:root[data-theme="lunar"] .btn:hover {
  background: rgba(230, 180, 92, 0.12);
  border-color: rgba(230, 180, 92, 0.5);
  color: var(--gold-hi);
}
:root[data-theme="lunar"] .btn.primary {
  background: linear-gradient(135deg, var(--gold-hi), var(--gold));
  color: #1b1305;
  border: none;
  box-shadow: 0 18px 40px -22px rgba(230, 180, 92, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.5);
}
:root[data-theme="lunar"] .btn.primary:hover { filter: brightness(1.04); color: #1b1305; }
:root[data-theme="lunar"] .btn.green {
  background: rgba(61, 220, 132, 0.1);
  border-color: rgba(61, 220, 132, 0.28);
  color: #6ee7a8;
}
:root[data-theme="lunar"] .btn.green:hover { background: rgba(61, 220, 132, 0.18); color: #a7f3c8; }
:root[data-theme="lunar"] input,
:root[data-theme="lunar"] select {
  background: #070b11;
  border-color: rgba(255, 255, 255, 0.09);
  border-radius: 11px;
}
:root[data-theme="lunar"] input:focus,
:root[data-theme="lunar"] select:focus {
  border-color: rgba(230, 180, 92, 0.65);
  box-shadow: 0 0 0 3px rgba(230, 180, 92, 0.12);
}
:root[data-theme="lunar"] input::placeholder { color: #4d596b; }
:root[data-theme="lunar"] .settings-section,
:root[data-theme="lunar"] .admin-card,
:root[data-theme="lunar"] .result-item {
  background: var(--panel);
  border-color: var(--line);
  border-radius: 16px;
}
:root[data-theme="lunar"] .page-title .grad {
  background: linear-gradient(115deg, var(--gold-hi) 5%, var(--gold) 50%, #c08c33 100%);
  -webkit-background-clip: text;
  background-clip: text;
}
:root[data-theme="lunar"] .page-title svg { stroke: var(--gold); }
:root[data-theme="lunar"] .theme-card { background: var(--panel); border-radius: 14px; }
:root[data-theme="lunar"] .theme-card.active {
  border-color: rgba(230, 180, 92, 0.75);
  box-shadow: 0 0 0 3px rgba(230, 180, 92, 0.12), 0 18px 34px -26px rgba(230, 180, 92, 0.7);
}
:root[data-theme="lunar"] .switch.on { background: linear-gradient(135deg, var(--gold-hi), var(--gold)); }
:root[data-theme="lunar"] .switch.on::after { box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35); }
:root[data-theme="lunar"] .result-item.selected {
  border-color: rgba(230, 180, 92, 0.75);
  background: linear-gradient(135deg, rgba(230, 180, 92, 0.1), transparent);
  box-shadow: 0 0 0 1px rgba(230, 180, 92, 0.4);
}
:root[data-theme="lunar"] .result-icon { color: var(--gold); background: rgba(230, 180, 92, 0.1); }
:root[data-theme="lunar"] .result-meta .badge { background: rgba(255, 255, 255, 0.06); }
:root[data-theme="lunar"] .settings-section h3 { color: var(--text-mute); }

/* Скроллбар */
:root[data-theme="lunar"] #content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border: 2px solid #06080c;
}
:root[data-theme="lunar"] #content::-webkit-scrollbar-thumb:hover { background: rgba(230, 180, 92, 0.35); }

/* ================= Liquid Glass — холодное стекло ================= */
:root[data-theme="glass"] {
  --bg: #05080f;
  --bg-soft: #0a1220;
  --glass: rgba(11, 18, 30, 0.55);
  --glass-border: rgba(255, 255, 255, 0.12);
  --panel: rgba(14, 23, 38, 0.55);
  --panel-2: rgba(20, 31, 50, 0.66);
  --line: rgba(255, 255, 255, 0.1);
  --text: #eff6ff;
  --text-dim: #a4b4c9;
  --text-mute: #6b7d93;
  --gold: #a9cfff;
  --gold-hi: #eef7ff;
  --grad-1: #eef7ff;
  --grad-2: #8fbcff;
  --accent: #b9d6ff;
  --accent-soft: rgba(160, 200, 255, 0.14);
  --green: #4ade9b;
  --orange: #9ec9ff;
  --red: #fb7185;
  --on-accent: #08121f;
  --ice: #b9d6ff;
  --ice-hi: #eef7ff;
  --body-bg:
    radial-gradient(1000px 640px at 8% -12%, rgba(160, 200, 255, 0.18), transparent 62%),
    radial-gradient(820px 540px at 100% 0%, rgba(110, 220, 220, 0.1), transparent 58%),
    radial-gradient(900px 700px at 50% 115%, rgba(140, 175, 255, 0.07), transparent 60%),
    #05080f;
}

:root[data-theme="glass"] body {
  font-family: 'Inter', 'Segoe UI Variable Display', 'Segoe UI', system-ui, -apple-system, sans-serif;
}
:root[data-theme="glass"] body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.024) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.024) 1px, transparent 1px);
  background-size: 64px 64px;
  -webkit-mask-image: radial-gradient(ellipse 85% 60% at 50% 0%, #000 18%, transparent 76%);
  mask-image: radial-gradient(ellipse 85% 60% at 50% 0%, #000 18%, transparent 76%);
}
:root[data-theme="glass"] body::after {
  content: '';
  position: fixed;
  z-index: 0;
  left: -12vw;
  bottom: -26vw;
  width: 68vw;
  height: 68vw;
  border-radius: 50%;
  pointer-events: none;
  background:
    radial-gradient(circle at 38% 38%, rgba(160, 200, 255, 0.2), transparent 58%),
    radial-gradient(circle at 72% 70%, rgba(110, 220, 220, 0.13), transparent 55%);
  filter: blur(46px);
}
:root[data-theme="glass"] #app { position: relative; z-index: 1; }

/* Каркас */
:root[data-theme="glass"] .rail,
:root[data-theme="glass"] #titlebar {
  background: rgba(7, 12, 21, 0.6);
  backdrop-filter: blur(22px) saturate(150%);
  -webkit-backdrop-filter: blur(22px) saturate(150%);
  border-color: var(--line);
}
:root[data-theme="glass"] #titlebar { border-bottom: 1px solid var(--line); position: relative; }
:root[data-theme="glass"] #titlebar::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(200, 230, 255, 0.45), transparent);
  pointer-events: none;
}
:root[data-theme="glass"] .rail { border-right: 1px solid var(--line); }
:root[data-theme="glass"] .rail-logo,
:root[data-theme="glass"] .tb-brand .brand-logo {
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(190, 222, 255, 0.35), 0 10px 26px -12px rgba(150, 195, 255, 0.5);
}
:root[data-theme="glass"] .tb-brand .name b { color: var(--ice); font-weight: 800; }
:root[data-theme="glass"] .rail-item:hover,
:root[data-theme="glass"] .tb-icon:hover,
:root[data-theme="glass"] .tb-back:hover { background: rgba(255, 255, 255, 0.07); color: var(--text); }
:root[data-theme="glass"] .rail-item.active {
  background: rgba(255, 255, 255, 0.09);
  color: var(--ice-hi);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}
:root[data-theme="glass"] .rail-item.active::before {
  background: linear-gradient(180deg, var(--ice-hi), var(--ice-lo, #6d9fd8));
}
:root[data-theme="glass"] .tb-version {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--line);
  color: var(--text-dim);
}
:root[data-theme="glass"] .tb-sep { background: var(--line); }

/* Аккаунт в шапке */
:root[data-theme="glass"] .title-account {
  background: rgba(255, 255, 255, 0.055);
  border-color: var(--line-strong, rgba(255, 255, 255, 0.17));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
  backdrop-filter: blur(14px);
}
:root[data-theme="glass"] .title-account:hover {
  border-color: rgba(190, 222, 255, 0.55);
  background: rgba(190, 222, 255, 0.1);
}
:root[data-theme="glass"] .title-account.logged .dot {
  background: var(--green);
  box-shadow: 0 0 8px rgba(74, 222, 155, 0.8);
}
:root[data-theme="glass"] .title-account .avatar,
:root[data-theme="glass"] .acct-ava {
  background: linear-gradient(135deg, #f4faff, #b9d6ff 60%, #8fbbec);
  color: #08121f;
  box-shadow: 0 8px 18px -8px rgba(150, 195, 255, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

/* Launchpad */
:root[data-theme="glass"] .lp-welcome { letter-spacing: -0.3px; }
:root[data-theme="glass"] .lp-welcome .nick { color: var(--ice-hi); }
:root[data-theme="glass"] .live-dot {
  background: var(--green);
  box-shadow: 0 0 10px rgba(74, 222, 155, 0.8);
}
:root[data-theme="glass"] .online-pill { color: var(--text-dim); }
:root[data-theme="glass"] .qtile {
  background: linear-gradient(160deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.16);
  color: var(--ice);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), 0 10px 22px -16px rgba(0, 0, 0, 0.9);
  backdrop-filter: blur(14px);
}
:root[data-theme="glass"] .qtile:hover {
  background: linear-gradient(160deg, rgba(255, 255, 255, 0.24), rgba(255, 255, 255, 0.06));
  border-color: rgba(190, 222, 255, 0.5);
  color: #fff;
}
:root[data-theme="glass"] .lp-hero {
  border-color: rgba(255, 255, 255, 0.16);
  border-radius: 20px;
  box-shadow: 0 30px 70px -40px rgba(0, 0, 0, 0.95), inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 0 90px -46px rgba(160, 200, 255, 0.5);
}
:root[data-theme="glass"] .lp-hero::after {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(220, 240, 255, 0.75), transparent);
  z-index: 3;
  pointer-events: none;
}
:root[data-theme="glass"] .launch-btn {
  background: linear-gradient(165deg, #f7fbff 0%, #c9e0ff 52%, #93bfee 100%);
  color: #08121f;
  border-radius: 13px;
  box-shadow: 0 18px 40px -16px rgba(150, 195, 255, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.85), inset 0 -2px 0 rgba(6, 18, 32, 0.12);
}
:root[data-theme="glass"] .launch-btn:hover { filter: brightness(1.05); }
:root[data-theme="glass"] .launch-btn:disabled {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-mute);
  box-shadow: none;
  filter: none;
}
:root[data-theme="glass"] .launch-btn.busy { animation: launchPulseIce 1.5s ease-in-out infinite; }
@keyframes launchPulseIce {
  0%, 100% { box-shadow: 0 16px 34px -14px rgba(150, 195, 255, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.8); }
  50% { box-shadow: 0 18px 50px -12px rgba(150, 195, 255, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.85); }
}
:root[data-theme="glass"] .launch-title { letter-spacing: 1px; text-shadow: 0 1px 0 rgba(255, 255, 255, 0.35); }
:root[data-theme="glass"] .launch-sub { opacity: 0.8; }
:root[data-theme="glass"] .hero-note { color: rgba(255, 255, 255, 0.42); }
:root[data-theme="glass"] .hero-gear {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--ice-hi);
  backdrop-filter: blur(12px);
}
:root[data-theme="glass"] .hero-gear:hover { background: rgba(255, 255, 255, 0.18); color: #fff; }
:root[data-theme="glass"] .hc-panel {
  background: rgba(10, 17, 28, 0.82);
  border-color: rgba(255, 255, 255, 0.16);
  border-radius: 18px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(22px);
}
:root[data-theme="glass"] .hc-close { background: rgba(255, 255, 255, 0.07); }
:root[data-theme="glass"] .hc-close:hover { background: rgba(255, 255, 255, 0.16); color: #fff; }
:root[data-theme="glass"] .launch-status { color: var(--text-dim); }

/* Панели справа */
:root[data-theme="glass"] .panel {
  background:
    linear-gradient(160deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.02) 52%),
    rgba(12, 20, 33, 0.5);
  border-color: var(--line);
  border-radius: 16px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.24), 0 20px 44px -34px rgba(0, 0, 0, 0.9);
  backdrop-filter: blur(18px) saturate(140%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
}
:root[data-theme="glass"] .panel-head .link:hover,
:root[data-theme="glass"] .lp-news-head .link:hover { color: var(--ice); }
:root[data-theme="glass"] .acct-name .badge.role,
:root[data-theme="glass"] .badge.role { background: rgba(160, 200, 255, 0.16); color: var(--ice-hi); }
:root[data-theme="glass"] .server-ip {
  background: rgba(5, 10, 18, 0.6);
  border-color: var(--line);
  border-radius: 9px;
}
:root[data-theme="glass"] .server-ip button:hover { color: var(--ice); }

/* Новости */
:root[data-theme="glass"] .news-card {
  background:
    linear-gradient(160deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.015) 52%),
    rgba(12, 20, 33, 0.5);
  border-color: var(--line);
  border-radius: 16px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
}
:root[data-theme="glass"] .news-card:hover { border-color: rgba(190, 222, 255, 0.42); }
:root[data-theme="glass"] .news-card.green .news-cover {
  background:
    radial-gradient(circle at 85% 15%, rgba(160, 200, 255, 0.32), transparent 55%),
    linear-gradient(135deg, #0f1d30 0%, #070b13 74%);
}
:root[data-theme="glass"] .news-card.red .news-cover {
  background:
    radial-gradient(circle at 85% 15%, rgba(74, 222, 155, 0.2), transparent 55%),
    linear-gradient(135deg, #0a1a18 0%, #050b0a 74%);
}
:root[data-theme="glass"] .news-card.blue .news-cover {
  background:
    radial-gradient(circle at 85% 15%, rgba(160, 200, 255, 0.24), transparent 55%),
    linear-gradient(135deg, #101827 0%, #070a11 74%);
}
:root[data-theme="glass"] .news-tag { color: rgba(220, 238, 255, 0.62); }
:root[data-theme="glass"] .news-big { color: rgba(255, 255, 255, 0.09); }
:root[data-theme="glass"] .news-arrow { background: rgba(255, 255, 255, 0.12); }
:root[data-theme="glass"] .news-card:hover .news-arrow { background: rgba(255, 255, 255, 0.24); }

/* Кнопки, поля, страницы */
:root[data-theme="glass"] .btn {
  background: rgba(255, 255, 255, 0.055);
  border-color: var(--line);
  color: var(--text);
  border-radius: 11px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(12px);
}
:root[data-theme="glass"] .btn:hover {
  background: rgba(190, 222, 255, 0.12);
  border-color: rgba(190, 222, 255, 0.5);
  color: var(--ice-hi);
}
:root[data-theme="glass"] .btn.primary {
  background: linear-gradient(135deg, #f7fbff, #bcd9ff 60%, #93bfee);
  color: #08121f;
  border: none;
  box-shadow: 0 18px 40px -22px rgba(150, 195, 255, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.85);
}
:root[data-theme="glass"] .btn.primary:hover { filter: brightness(1.04); color: #08121f; }
:root[data-theme="glass"] .btn.green {
  background: rgba(74, 222, 155, 0.1);
  border-color: rgba(74, 222, 155, 0.28);
  color: #86efac;
}
:root[data-theme="glass"] .btn.green:hover { background: rgba(74, 222, 155, 0.18); color: #b6f7d3; }
:root[data-theme="glass"] input,
:root[data-theme="glass"] select {
  background: rgba(5, 10, 18, 0.62);
  border-color: rgba(255, 255, 255, 0.12);
  border-radius: 11px;
}
:root[data-theme="glass"] input:focus,
:root[data-theme="glass"] select:focus {
  border-color: rgba(190, 222, 255, 0.65);
  box-shadow: 0 0 0 3px rgba(160, 200, 255, 0.14);
}
:root[data-theme="glass"] input::placeholder { color: #4d5c70; }
:root[data-theme="glass"] .settings-section,
:root[data-theme="glass"] .admin-card,
:root[data-theme="glass"] .result-item {
  background:
    linear-gradient(160deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.015) 55%),
    rgba(12, 20, 33, 0.5);
  border-color: var(--line);
  border-radius: 16px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2);
}
:root[data-theme="glass"] .page-title .grad {
  background: linear-gradient(115deg, var(--ice-hi) 5%, var(--ice) 50%, #7fb0e8 100%);
  -webkit-background-clip: text;
  background-clip: text;
}
:root[data-theme="glass"] .page-title svg { stroke: var(--ice); }
:root[data-theme="glass"] .theme-card {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 14px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.16);
}
:root[data-theme="glass"] .theme-card.active {
  border-color: rgba(190, 222, 255, 0.75);
  box-shadow: 0 0 0 3px rgba(160, 200, 255, 0.14), 0 18px 34px -26px rgba(150, 195, 255, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.26);
}
:root[data-theme="glass"] .switch.on { background: linear-gradient(135deg, #eef7ff, #8fbcff); }
:root[data-theme="glass"] .switch.on::after { box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35); }
:root[data-theme="glass"] .result-item.selected {
  border-color: rgba(190, 222, 255, 0.75);
  background: linear-gradient(135deg, rgba(160, 200, 255, 0.12), transparent);
  box-shadow: 0 0 0 1px rgba(160, 200, 255, 0.4);
}
:root[data-theme="glass"] .result-icon { color: var(--ice); background: rgba(160, 200, 255, 0.1); }
:root[data-theme="glass"] .result-meta .badge { background: rgba(255, 255, 255, 0.07); }
:root[data-theme="glass"] .settings-section h3 { color: var(--text-mute); }

/* Скроллбар */
:root[data-theme="glass"] #content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border: 2px solid #05080f;
}
:root[data-theme="glass"] #content::-webkit-scrollbar-thumb:hover { background: rgba(190, 222, 255, 0.4); }
</style>
</head>
<body>

<div id="app">
  <aside class="rail">
    <div class="rail-logo" role="img" aria-label="BritonLauncher"></div>
    <button class="rail-item active" data-page="launch" onclick="showPage('launch')" title="Launchpad">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>
    </button>
    <button class="rail-item" data-page="mods" onclick="showPage('mods')" title="Моды">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
    </button>
    <button class="rail-item" data-page="resourcepacks" onclick="showPage('resourcepacks')" title="Ресурспаки">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/></svg>
    </button>
    <button class="rail-item" data-page="shaders" onclick="showPage('shaders')" title="Шейдеры">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
    </button>
    <div class="rail-sep"></div>
    <button class="rail-item" data-page="admin" id="nav-admin" style="display:none" onclick="showPage('admin')" title="Админка">
      <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
    </button>
    <div class="rail-bottom">
      <button class="rail-item" onclick="siteOpen()" title="Сайт BritonLauncher">
        <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
      </button>
      <button class="rail-item" data-page="settings" onclick="showPage('settings')" title="Настройки">
        <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      </button>
      <div class="rail-ver">v3.11.0</div>
    </div>
  </aside>

  <div class="main">
    <div id="titlebar" class="pywebview-drag-region">
      <div class="tb-brand">
        <div class="brand-logo" role="img" aria-label="BritonLauncher"></div>
        <span class="name">Briton<b>Launcher</b></span>
        <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="tb-sep"></div>
      <div class="tb-nav">
        <button class="tb-back" onclick="showPage('launch')" title="На главную">‹</button>
        <span class="tb-crumb" id="tb-crumb">Launchpad</span>
      </div>
      <div class="tb-right">
        <span class="tb-version">v3.11.0</span>
        <button class="tb-icon" onclick="focusSearch()" title="Поиск модов">
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </button>
        <button class="tb-icon" id="tb-update" onclick="openUpdate()" title="Обновления">
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          <span class="ping" id="tb-update-dot" style="display:none"></span>
        </button>
        <button class="tb-icon" onclick="showPage('settings')" title="Настройки">
          <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
        <button class="title-account" id="title-account" onclick="titleAccountClick()" title="Войти через сайт">
          <span class="avatar">?</span><span class="ta-nick">Войти</span><span class="dot"></span>
        </button>
        <div class="win-btns">
          <button class="win-btn" onclick="pywebview.api.minimize()">—</button>
          <button class="win-btn" onclick="pywebview.api.maximize()">□</button>
          <button class="win-btn close" onclick="pywebview.api.close()">✕</button>
        </div>
      </div>
    </div>

    <div class="content" id="content">
      <iframe id="custom-menu-iframe"></iframe>
    </div>
  </div>
</div>

<script>
let selectedItem = null;
let selectedType = null;
const state = { version: '1.20.1', loader: 'Vanilla' };
let launchGen = 0;

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function showToast(msg) {
  const d = document.createElement('div');
  d.textContent = msg;
  d.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--accent);color:var(--on-accent,#fff);padding:10px 18px;border-radius:12px;font-size:13px;font-weight:700;z-index:9999;box-shadow:0 8px 24px rgba(0,0,0,.4);transition:opacity .3s;max-width:80vw;';
  document.body.appendChild(d);
  setTimeout(() => { d.style.opacity = '0'; setTimeout(() => d.remove(), 300); }, 2600);
}

function applyTheme(id) { document.documentElement.setAttribute('data-theme', id); }

/* ---------- Свои цвета (акцент + фон) ---------- */
const CUSTOM_VARS = ['--bg', '--bg-soft', '--body-bg', '--panel', '--panel-2', '--glass',
  '--accent', '--accent-soft', '--gold', '--gold-hi', '--ice', '--ice-hi', '--ice-lo',
  '--grad-1', '--grad-2'];

function _hexToRgb(hex) {
  hex = String(hex || '').replace('#', '').trim();
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  if (!/^[0-9a-fA-F]{6}$/.test(hex)) return null;
  return { r: parseInt(hex.slice(0, 2), 16), g: parseInt(hex.slice(2, 4), 16), b: parseInt(hex.slice(4, 6), 16) };
}
function _rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
}
function _mixHex(a, b, t) {
  const A = _hexToRgb(a), B = _hexToRgb(b);
  if (!A || !B) return a;
  return _rgbToHex(A.r + (B.r - A.r) * t, A.g + (B.g - A.g) * t, A.b + (B.b - A.b) * t);
}
function _rgba(hex, a) {
  const c = _hexToRgb(hex);
  return c ? `rgba(${c.r}, ${c.g}, ${c.b}, ${a})` : hex;
}
function _luma(hex) {
  const c = _hexToRgb(hex);
  return c ? (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255 : 0;
}

function applyCustomColors(accent, bg) {
  const root = document.documentElement;
  CUSTOM_VARS.forEach(v => root.style.removeProperty(v));
  const old = document.getElementById('custom-colors-style');
  if (old) old.remove();
  if (!_hexToRgb(accent) && !_hexToRgb(bg)) return;
  accent = _hexToRgb(accent) ? accent : '#a9cfff';
  bg = _hexToRgb(bg) ? bg : '#05080f';
  const accentHi = _mixHex(accent, '#ffffff', 0.72);
  const accentMid = _mixHex(accent, '#ffffff', 0.42);
  const accentLo = _mixHex(accent, '#000000', 0.24);
  const onAccent = _luma(accentHi) > 0.62 ? '#08121f' : '#ffffff';
  const set = (k, v) => root.style.setProperty(k, v);
  set('--accent', accent);
  set('--accent-soft', _rgba(accent, 0.16));
  set('--gold', accent);
  set('--gold-hi', accentHi);
  set('--ice', accent);
  set('--ice-hi', accentHi);
  set('--ice-lo', accentLo);
  set('--grad-1', accentHi);
  set('--grad-2', accent);
  set('--bg', bg);
  set('--bg-soft', _mixHex(bg, '#ffffff', 0.045));
  set('--panel', _mixHex(bg, '#ffffff', 0.05));
  set('--panel-2', _mixHex(bg, '#ffffff', 0.08));
  set('--glass', _rgba(bg, 0.72));
  set('--body-bg', `radial-gradient(1000px 640px at 8% -12%, ${_rgba(accent, 0.16)}, transparent 62%), radial-gradient(820px 540px at 100% 0%, ${_rgba(accent, 0.09)}, transparent 58%), ${bg}`);
  const css = `
    :root #titlebar { background: ${_rgba(bg, 0.7)} !important; }
    :root .rail { background: ${_rgba(bg, 0.94)} !important; }
    :root .panel, :root .news-card, :root .settings-section, :root .admin-card,
    :root .result-item, :root .theme-card, :root .hc-panel {
      background: linear-gradient(160deg, rgba(255,255,255,0.09), rgba(255,255,255,0.015) 52%), ${_rgba(bg, 0.66)} !important;
    }
    :root .lp-hero { background: ${bg} !important; }
    :root body::after {
      background: radial-gradient(circle at 38% 38%, ${_rgba(accent, 0.2)}, transparent 58%),
                  radial-gradient(circle at 72% 70%, ${_rgba(accent, 0.13)}, transparent 55%) !important;
    }
    :root .news-card .news-cover {
      background: radial-gradient(circle at 85% 15%, ${_rgba(accent, 0.26)}, transparent 55%),
                  linear-gradient(135deg, ${_mixHex(bg, '#ffffff', 0.05)} 0%, ${bg} 74%) !important;
    }
    :root .rail-item.active { background: ${_rgba(accent, 0.15)} !important; color: ${accentHi} !important; }
    :root .rail-item.active::before { background: linear-gradient(180deg, ${accentHi}, ${accentLo}) !important; }
    :root .qtile { color: ${accent} !important; }
    :root .launch-btn, :root .btn.primary, :root .step-num {
      background: linear-gradient(165deg, ${accentHi} 0%, ${accentMid} 52%, ${accent} 100%) !important;
      color: ${onAccent} !important;
    }
    :root .btn:hover { border-color: ${_rgba(accent, 0.55)} !important; color: ${accentHi} !important; }
    :root input:focus, :root select:focus { border-color: ${_rgba(accent, 0.7)} !important; box-shadow: 0 0 0 3px ${_rgba(accent, 0.16)} !important; }
    :root .switch.on { background: linear-gradient(135deg, ${accentHi}, ${accent}) !important; }
    :root .theme-card.active { border-color: ${accent} !important; box-shadow: 0 0 0 3px ${_rgba(accent, 0.2)} !important; }
    :root .theme-check { background: ${accent} !important; color: ${onAccent} !important; }
    :root .title-account:hover { border-color: ${_rgba(accent, 0.55)} !important; }
    :root .server-ip button:hover, :root .panel-head .link:hover, :root .lp-news-head .link:hover { color: ${accent} !important; }
    :root .news-card:hover { border-color: ${_rgba(accent, 0.45)} !important; }
    :root .result-item.selected { border-color: ${_rgba(accent, 0.8)} !important; background: ${_rgba(accent, 0.1)} !important; }
    :root .page-title .grad { background: linear-gradient(115deg, ${accentHi} 5%, ${accent} 50%, ${accentLo} 100%) !important; -webkit-background-clip: text !important; background-clip: text !important; }
    :root .badge.role { background: ${_rgba(accent, 0.16)} !important; color: ${accentHi} !important; }
    :root ::selection { background: ${_rgba(accent, 0.3)} !important; }
  `;
  const style = document.createElement('style');
  style.id = 'custom-colors-style';
  style.textContent = css;
  document.head.appendChild(style);
}
function currentThemeColor(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return _hexToRgb(v) ? v : fallback;
}
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
  btn.classList.toggle('busy', b);
  const t = btn.querySelector('.launch-title');
  const s = btn.querySelector('.launch-sub');
  if (t) t.textContent = b ? 'ЗАПУСК...' : 'ИГРАТЬ';
  if (s) s.style.opacity = b ? '0.55' : '0.95';
}

async function saveNick() {
  const nick = (document.getElementById('nick')?.value || '').trim();
  if (!nick) { setStatus('Ник пустой', 'var(--red)', '❌'); showToast('Введите ник'); return; }
  const res = await window.pywebview.api.save_nickname(nick);
  if (res && res.ok) showToast('Ник сохранён');
}
async function startGame(serverIp = null) {
  const nickInput = document.getElementById('nick');
  const nick = (nickInput?.value || window.__savedNick || '').trim();
  const cfg = await window.pywebview.api.get_config();
  const res = await window.pywebview.api.launch_game(nick, state.version, state.loader, cfg.ram, cfg.show_console, serverIp);
  if (res && res.ok === false) {
    setStatus(res.error || 'Не удалось запустить игру', 'var(--red)', '❌');
    setPlayBusy(false);
  }
}

function updateAdminNav(acc) {
  const nav = document.getElementById('nav-admin');
  if (nav) nav.style.display = acc && acc.logged_in && acc.role === 'admin' ? 'grid' : 'none';
}

function updateTitleAccount(acc) {
  const el = document.getElementById('title-account');
  if (!el) return;
  window.__titleAcc = acc || null;
  const logged = !!(acc && acc.logged_in);
  const nick = logged ? acc.nick : 'Войти';
  const initial = logged ? String(acc.nick || '?').charAt(0).toUpperCase() : '?';
  el.classList.toggle('logged', logged);
  el.classList.toggle('admin', logged && acc.role === 'admin');
  el.innerHTML = '<span class="avatar">' + escapeHtml(initial) + '</span>'
    + '<span class="ta-nick">' + escapeHtml(nick) + '</span>'
    + '<span class="dot"></span>';
  el.title = logged
    ? (acc.role === 'admin' ? 'Открыть админ-панель' : 'Аккаунт сайта')
    : 'Войти через сайт';
}

function titleAccountClick() {
  const acc = window.__titleAcc;
  if (acc && acc.logged_in && acc.role === 'admin') { showPage('admin'); return; }
  if (acc && acc.logged_in) { siteOpen(); return; }
  if (document.body.dataset.activePage !== 'launch') {
    showPage('launch').then(() => setTimeout(focusSiteLogin, 280));
  } else {
    focusSiteLogin();
  }
}

function focusSiteLogin() {
  const input = document.getElementById('site-nick') || document.getElementById('site-code');
  if (input) {
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
    input.focus();
  }
}

function roleLabel(acc) {
  if (!acc || !acc.logged_in || acc.role !== 'admin') return 'ИГРОК';
  return acc.main ? 'ГЛАВНЫЙ АДМИН' : 'АДМИН';
}

async function refreshAccount() {
  const acc = await window.pywebview.api.get_site_account();
  updateAdminNav(acc);
  updateTitleAccount(acc);

  const welcome = document.getElementById('welcome-nick');
  if (welcome) {
    welcome.textContent = acc.logged_in ? acc.nick : (window.__savedNick || 'Гость');
    welcome.classList.toggle('guest', !acc.logged_in);
  }

  const box = document.getElementById('account-box');
  if (!box) return;
  if (acc.logged_in) {
    box.innerHTML = '<div class="acct-row">'
      + '<div class="acct-ava">' + escapeHtml(acc.nick.charAt(0).toUpperCase()) + '</div>'
      + '<div><div class="acct-name">' + escapeHtml(acc.nick)
      + '<span class="badge role">' + roleLabel(acc) + '</span>'
      + (acc.banned ? '<span class="badge mute">БАН</span>' : (acc.muted ? '<span class="badge mute">МУТ</span>' : '')) + '</div>'
      + '<div class="acct-meta">' + (acc.banned
          ? 'Забанен: ' + escapeHtml(acc.ban_reason || 'без причины')
          : 'Аккаунт BritonLauncher · ' + escapeHtml(acc.login_at || '—')) + '</div></div>'
      + '</div>'
      + '<div class="acct-actions">'
      + (acc.role === 'admin' ? '<button class="btn" onclick="goAdmin()">Админка</button>' : '')
      + '<button class="btn" onclick="siteOpen()">Сайт</button>'
      + '<button class="btn" onclick="siteLogout()">Выйти</button>'
      + '</div>';
  } else {
    box.innerHTML = '<div class="acct-row">'
      + '<div class="acct-ava">?</div>'
      + '<div><div class="acct-name">Гость</div>'
      + '<div class="acct-meta">Вход в аккаунт BritonLauncher</div></div></div>'
      + '<div class="site-login-row">'
      + '<input id="site-nick" placeholder="Ник" spellcheck="false" autocomplete="username" onkeydown="sitePasswordLoginKey(event)" />'
      + '<input id="site-pass" type="password" placeholder="Пароль" autocomplete="current-password" onkeydown="sitePasswordLoginKey(event)" />'
      + '<button class="btn green" onclick="sitePasswordLogin()">Войти</button>'
      + '</div>'
      + '<div class="site-hint" style="margin:0">Или по одноразовому коду с сайта:</div>'
      + '<div class="site-login-row"><input id="site-code" placeholder="Вставь код с сайта" spellcheck="false" onkeydown="siteLoginKey(event)" />'
      + '<button class="btn" onclick="siteLogin()">Войти по коду</button></div>'
      + '<button class="btn" onclick="siteOpen()">Открыть сайт</button>'
      + '<div class="site-hint">Нет аккаунта? Зарегистрируйся на сайте — он общий для сайта и лаунчера.</div>';
  }
}

async function siteOpen() {
  await window.pywebview.api.site_open();
  showToast('Открой сайт, чтобы зарегистрироваться или получить код');
}

function sitePasswordLoginKey(event) {
  if (event.key === 'Enter') sitePasswordLogin();
}

function siteLoginKey(event) {
  if (event.key === 'Enter') siteLogin();
}

function applySiteLogin(res) {
  if (res.ok) {
    showToast(res.muted ? 'Вход выполнен: ' + res.nick + ' (действует мут)' : 'Вход выполнен: ' + res.nick);
    refreshAccount();
    if (document.body.dataset.activePage === 'admin') renderAdminPage();
  } else {
    showToast('Ошибка: ' + res.error);
  }
}

async function sitePasswordLogin() {
  const nick = (document.getElementById('site-nick')?.value || '').trim();
  const password = document.getElementById('site-pass')?.value || '';
  if (!nick || !password) { showToast('Введи ник и пароль'); return; }
  const res = await window.pywebview.api.site_password_login(nick, password);
  applySiteLogin(res);
}

async function siteLogin() {
  const code = (document.getElementById('site-code')?.value || '').trim();
  if (!code) { showToast('Вставь код с сайта'); return; }
  const res = await window.pywebview.api.site_login(code);
  applySiteLogin(res);
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
  content.style.padding = '';
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
      <div class="admin-row"><span>Статус</span><b>${acc.banned ? 'Забанен: ' + escapeHtml(acc.ban_reason || 'без причины') : (acc.muted ? 'Мут' : 'Активен')}</b></div>
      <div class="admin-row"><span>Вход</span><b>${escapeHtml(acc.login_at || '—')}</b></div>
    </div>
    <div class="admin-actions">
      <button class="btn primary" onclick="openSiteAdmin()">Открыть админ-панель на сайте</button>
      <button class="btn" onclick="siteLogout()">Выйти</button>
    </div>
    <div class="page-status">Аккаунты хранятся в общей базе и действуют на сайте и в лаунчере. Управление игроками — на сайте, в разделе «Аккаунт».</div>`;
}

async function openSiteAdmin() {
  await window.pywebview.api.site_open();
  showToast('Открыл сайт — раздел «Аккаунт»');
}

async function showPage(page) {
  document.body.dataset.activePage = page;
  document.querySelectorAll('.rail-item[data-page]').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  const PAGE_NAMES = { launch: 'Launchpad', mods: 'Моды', resourcepacks: 'Ресурспаки', shaders: 'Шейдеры', settings: 'Настройки', admin: 'Админка' };
  const crumb = document.getElementById('tb-crumb');
  if (crumb) crumb.textContent = PAGE_NAMES[page] || 'Launchpad';
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
      content.classList.remove('page-anim');
      return;
    }
    content.style.padding = '';
    await renderLaunch();
  } else {
    content.style.padding = '';
    if (page === 'admin') await renderAdminPage();
    else if (page === 'settings') await renderSettings();
    else renderSearchPage(page);
  }
  content.classList.remove('page-anim');
  void content.offsetWidth;
  content.classList.add('page-anim');
}

function seeded(seed) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

function heroStars() {
  const rnd = seeded(429);
  let out = '';
  for (let i = 0; i < 90; i++) {
    const x = (rnd() * 900).toFixed(0);
    const y = (rnd() * 300).toFixed(0);
    const r = (rnd() * 1.2 + 0.3).toFixed(2);
    const o = (rnd() * 0.55 + 0.12).toFixed(2);
    out += `<circle cx="${x}" cy="${y}" r="${r}" fill="#dbe6ff" opacity="${o}"/>`;
  }
  return out;
}

function isoCube(x, y, s, top, left, right, stroke) {
  const w = (s * 0.87).toFixed(1);
  const h = (s * 0.5).toFixed(1);
  return `<g transform="translate(${x} ${y})">`
    + `<polygon points="0,${-s} ${w},${-h} 0,0 ${-w},${-h}" fill="${top}" stroke="${stroke}" stroke-width="1"/>`
    + `<polygon points="${-w},${-h} 0,0 0,${s} ${-w},${h}" fill="${left}" stroke="${stroke}" stroke-width="1"/>`
    + `<polygon points="${w},${-h} 0,0 0,${s} ${w},${h}" fill="${right}" stroke="${stroke}" stroke-width="1"/>`
    + `</g>`;
}

function updateLaunchSub() {
  const v = document.getElementById('launch-version');
  const l = document.getElementById('launch-loader');
  if (v) v.textContent = state.version;
  if (l) l.textContent = state.loader;
}

function toggleLaunchConfig(force) {
  const el = document.getElementById('hero-config');
  if (!el) return;
  const open = typeof force === 'boolean' ? force : !el.classList.contains('open');
  el.classList.toggle('open', open);
  if (open) {
    setTimeout(() => document.getElementById('nick')?.focus(), 180);
  }
}

async function saveLaunchConfig() {
  const nick = (document.getElementById('nick')?.value || '').trim();
  const ram = (document.getElementById('ram')?.value || '4G').trim() || '4G';
  const show_console = document.getElementById('console-switch')?.classList.contains('on') || false;
  const loaderSel = document.getElementById('modloader');
  const verSel = document.getElementById('version');
  if (verSel) state.version = verSel.value || state.version;
  if (loaderSel) state.loader = loaderSel.value || state.loader;
  if (nick) {
    const res = await window.pywebview.api.save_nickname(nick);
    if (!res || !res.ok) { showToast('Ник не сохранён'); return; }
    window.__savedNick = nick;
  }
  const cfg = await window.pywebview.api.get_config();
  await window.pywebview.api.save_settings({
    theme: cfg.theme || 'glass',
    ram,
    show_console,
    version: state.version,
    modloader: state.loader
  });
  updateLaunchSub();
  toggleLaunchConfig(false);
  refreshAccount();
  showToast('Настройки запуска сохранены');
}

async function copyServerIp() {
  const ip = 'f1.rustix.me:38391';
  try {
    await navigator.clipboard.writeText(ip);
  } catch (e) {
    const t = document.createElement('textarea');
    t.value = ip;
    document.body.appendChild(t);
    t.select();
    try { document.execCommand('copy'); } catch (_) {}
    t.remove();
  }
  showToast('IP сервера скопирован');
}

function focusSearch() {
  showPage('mods').then(() => {
    setTimeout(() => document.getElementById('search-input')?.focus(), 260);
  });
}

function openUpdate() {
  const up = window.__update;
  if (up && up.ok && up.update_available) {
    window.pywebview.api.open_url('https://github.com/KostyaProcrom/BritonLauncher/releases/latest');
  } else {
    showToast('Обновлений нет — версия актуальна');
  }
}

function openReleases() {
  window.pywebview.api.open_url('https://github.com/KostyaProcrom/BritonLauncher/releases/latest');
}

async function renderLaunch() {
  const gen = ++launchGen;
  const cfg = await window.pywebview.api.get_config();
  if (document.body.dataset.activePage !== 'launch') return;
  window.__savedNick = cfg.nickname || '';
  window.__savedTheme = cfg.theme || 'glass';
  applyCustomColors(cfg.custom_accent, cfg.custom_bg);
  state.version = cfg.version || state.version;
  state.loader = cfg.modloader || state.loader;

  const stars = heroStars();
  const isGlass = (cfg.theme || 'glass') === 'glass';
  const customAccent = _hexToRgb(cfg.custom_accent) ? cfg.custom_accent : '';
  const customBg = _hexToRgb(cfg.custom_bg) ? cfg.custom_bg : '';
  let artBg = isGlass ? '#060b13' : '#070a10';
  let blobA = isGlass ? '#2a5a8f' : '#6b4a12';
  let blobB = isGlass ? '#12595c' : '#0d4a30';
  let blobC = isGlass ? '#1b3050' : '#2a1d06';
  let cubeLeft = isGlass
    ? isoCube(150, 148, 38, '#dcecff', '#16273c', '#4d6d92', 'rgba(190,220,255,0.4)')
      + isoCube(202, 194, 20, '#8fb6e0', '#12202f', '#3f5a77', 'rgba(160,200,255,0.28)')
      + isoCube(118, 196, 14, '#b9d6ff', '#16273c', '#3f5a77', 'rgba(160,200,255,0.25)')
    : isoCube(150, 148, 38, '#f3cf86', '#3a2a0c', '#7a5a1f', 'rgba(255,214,140,0.35)')
      + isoCube(202, 194, 20, '#c99a45', '#2a1e08', '#6b4e1a', 'rgba(255,205,120,0.25)')
      + isoCube(118, 196, 14, '#e6b45c', '#2e2109', '#5e4415', 'rgba(255,205,120,0.2)');
  let cubeRight = isGlass
    ? isoCube(750, 146, 34, '#dbe9f7', '#3c4b5e', '#6d8199', 'rgba(255,255,255,0.24)')
      + isoCube(696, 190, 18, '#9fb2c6', '#2c3744', '#55677c', 'rgba(255,255,255,0.16)')
      + isoCube(618, 78, 11, '#7fe3ff', '#0b2b3a', '#1f6079', 'rgba(127,227,255,0.32)')
    : isoCube(750, 146, 34, '#c7d2e2', '#4d5563', '#7b8698', 'rgba(255,255,255,0.22)')
      + isoCube(696, 190, 18, '#8e99aa', '#363c47', '#5c6575', 'rgba(255,255,255,0.16)')
      + isoCube(618, 78, 11, '#3ddc84', '#0a2e1b', '#12603a', 'rgba(61,220,132,0.3)');
  if (customBg || customAccent) {
    if (customBg) artBg = customBg;
    if (customAccent) {
      const hi = _mixHex(customAccent, '#ffffff', 0.7);
      const mid = _mixHex(customAccent, '#ffffff', 0.35);
      const lo = _mixHex(customAccent, '#000000', 0.3);
      blobA = customAccent;
      blobB = _mixHex(customAccent, customBg || '#05080f', 0.35);
      blobC = _mixHex(customAccent, customBg || '#05080f', 0.6);
      cubeLeft = isoCube(150, 148, 38, hi, lo, mid, _rgba(customAccent, 0.4))
        + isoCube(202, 194, 20, mid, lo, _mixHex(customAccent, '#000000', 0.15), _rgba(customAccent, 0.28))
        + isoCube(118, 196, 14, hi, lo, mid, _rgba(customAccent, 0.25));
      cubeRight = isoCube(750, 146, 34, _mixHex(customAccent, '#ffffff', 0.85), lo, mid, _rgba(customAccent, 0.24))
        + isoCube(696, 190, 18, mid, lo, _mixHex(customAccent, '#000000', 0.2), _rgba(customAccent, 0.16))
        + isoCube(618, 78, 11, hi, lo, mid, _rgba(customAccent, 0.32));
    }
  }

  document.getElementById('content').innerHTML = `
  <div class="lp">
    <div class="lp-head">
      <div class="lp-welcome">С возвращением, <span class="nick" id="welcome-nick">Гость</span><span class="live-dot"></span></div>
      <div class="lp-head-right">
        <div class="online-pill"><span class="live-dot"></span> Онлайн</div>
        <div class="quick-tiles">
          <button class="qtile" style="--q1:#8b5cf6;--q2:#6d28d9" onclick="showPage('mods')" title="Моды">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
          </button>
          <button class="qtile" style="--q1:#f59e0b;--q2:#dc2626" onclick="showPage('resourcepacks')" title="Ресурспаки">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.9 0 1.6-.7 1.6-1.7 0-.4-.2-.8-.4-1.1-.3-.3-.4-.7-.4-1.1a1.6 1.6 0 0 1 1.7-1.7h2c3 0 5.5-2.5 5.5-5.5C22 6 17.5 2 12 2z"/><circle cx="13.5" cy="6.5" r=".6" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".6" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".6" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".6" fill="currentColor"/></svg>
          </button>
          <button class="qtile" style="--q1:#06b6d4;--q2:#2563eb" onclick="showPage('shaders')" title="Шейдеры">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
          </button>
          <button class="qtile" style="--q1:#22c55e;--q2:#0f9d49" onclick="siteOpen()" title="Сайт">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          </button>
          <button class="qtile" style="--q1:#ec4899;--q2:#a855f7" onclick="showPage('settings')" title="Настройки">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </button>
        </div>
      </div>
    </div>

    <div class="lp-grid">
      <div class="lp-main">
        <div class="lp-hero">
          <svg class="hero-art" viewBox="0 0 900 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
            <defs>
              <filter id="heroBlur" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="38"/>
              </filter>
            </defs>
            <rect width="900" height="300" fill="${artBg}"/>
            <ellipse cx="150" cy="150" rx="220" ry="130" fill="${blobA}" opacity="0.5" filter="url(#heroBlur)"/>
            <ellipse cx="770" cy="180" rx="180" ry="115" fill="${blobB}" opacity="0.38" filter="url(#heroBlur)"/>
            <ellipse cx="450" cy="330" rx="340" ry="125" fill="${blobC}" opacity="0.5" filter="url(#heroBlur)"/>
            ${stars}
            ${cubeLeft}
            ${cubeRight}
          </svg>
          <div class="hero-center">
            <button id="play-btn" class="launch-btn" onclick="startGame()">
              <span class="launch-title">ИГРАТЬ</span>
              <span class="launch-sub">BritonLauncher <b id="launch-version">${escapeHtml(state.version)}</b><span class="sep">•</span><span id="launch-loader">${escapeHtml(state.loader)}</span></span>
            </button>
          </div>
          <div class="hero-note">v3.11.0 · BritonLauncher</div>
          <button class="hero-gear" onclick="toggleLaunchConfig()" title="Настройки запуска">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </button>
          <div class="hero-config" id="hero-config" onclick="if(event.target===this)toggleLaunchConfig(false)">
            <div class="hc-panel">
              <div class="hc-head"><span>Настройки запуска</span><button class="hc-close" onclick="toggleLaunchConfig(false)">✕</button></div>
              <div class="hc-grid">
                <div class="hc-field"><label>Ник</label><input id="nick" maxlength="16" placeholder="Steve" value="${escapeHtml(cfg.nickname || '')}" /></div>
                <div class="hc-field"><label>Память</label><input id="ram" placeholder="4G" value="${escapeHtml(cfg.ram || '4G')}" /></div>
              </div>
              <div class="hc-grid">
                <div class="hc-field"><label>Версия</label><select id="version"></select></div>
                <div class="hc-field"><label>Модлоадер</label>
                  <select id="modloader">
                    <option value="Vanilla" ${cfg.modloader === 'Vanilla' ? 'selected' : ''}>Vanilla</option>
                    <option value="Fabric" ${cfg.modloader === 'Fabric' ? 'selected' : ''}>Fabric</option>
                    <option value="Forge" ${cfg.modloader === 'Forge' ? 'selected' : ''}>Forge</option>
                  </select>
                </div>
              </div>
              <div class="hc-foot">
                <div class="hc-console"><span>Окно консоли</span><div id="console-switch" class="switch ${cfg.show_console ? 'on' : ''}" onclick="this.classList.toggle('on')"></div></div>
                <button class="btn green" onclick="saveLaunchConfig()">Сохранить</button>
                <button class="btn" onclick="showPage('settings')">Все настройки</button>
              </div>
            </div>
          </div>
        </div>

        <div class="lp-news-head">
          <h2>Новости <span class="count">2</span></h2>
          <button class="link" onclick="openReleases()">Все обновления ↗</button>
        </div>
        <div class="news-grid">
          <button class="news-card green" onclick="openReleases()">
            <div class="news-cover">
              <span class="news-big">3.11</span>
              <span class="news-tag">Обновление лаунчера</span>
              <span class="news-title">Liquid Glass</span>
              <span class="news-desc">Новый интерфейс в стиле сайта: холодное стекло, ледяные блики и прозрачные панели.</span>
              <span class="news-arrow"><svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><polyline points="9 18 15 12 9 6"/></svg></span>
            </div>
          </button>
          <button class="news-card red" onclick="showPage('settings')">
            <div class="news-cover">
              <span class="news-big">RP</span>
              <span class="news-tag">Ресурспак</span>
              <span class="news-title">BRITON Menu</span>
              <span class="news-desc">Брендовое меню Minecraft — установка в один клик.</span>
              <span class="news-arrow"><svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><polyline points="9 18 15 12 9 6"/></svg></span>
            </div>
          </button>
        </div>
        <div class="lp-footer">© KosmosStudio - 2026</div>
      </div>

      <div class="lp-side">
        <div class="panel account-panel">
          <div class="panel-head"><span>Аккаунт</span><span class="live-dot"></span></div>
          <div id="account-box" class="account-body"><div class="site-hint">Проверка аккаунта...</div></div>
        </div>
        <div class="panel server-panel">
          <div class="panel-head"><span>Сервер</span><span class="muted">BritonTime</span></div>
          <div class="server-name"><span class="live-dot"></span> BritonTime</div>
          <div class="server-desc">Выживание и мини-игры · 1.20.1–1.21.11</div>
          <div class="server-ip"><span>f1.rustix.me:38391</span>
            <button onclick="copyServerIp()" title="Скопировать IP"><svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>
          </div>
          <button class="btn green" onclick="startGame('f1.rustix.me:38391')">Зайти на сервер</button>
        </div>
        <div class="panel status-panel">
          <div class="panel-head"><span>Состояние</span></div>
          <div class="status-line"><div class="status-dot" id="status-dot"></div><span id="status-text">Проверка обновлений...</span></div>
        </div>
      </div>
    </div>
  </div>`;

  const loaderSel = document.getElementById('modloader');
  if (loaderSel) {
    state.loader = loaderSel.value || state.loader;
    loaderSel.addEventListener('change', () => { state.loader = loaderSel.value; updateLaunchSub(); });
  }
  updateLaunchSub();
  refreshAccount();
  loadVersionOptions(cfg.version, gen);

  window.pywebview.api.check_updates().then(up => {
    if (launchGen !== gen) return;
    window.__update = up;
    const dot = document.getElementById('tb-update-dot');
    if (dot) dot.style.display = up.ok && up.update_available ? 'block' : 'none';
    if (up.ok && up.update_available) {
      setStatus('Доступно обновление v' + up.latest, 'var(--orange)', '⏳');
    } else if (up.ok) {
      setStatus('Версия актуальна (v' + (up.current || '') + ')', 'var(--green)', '✅');
    } else {
      setStatus('Проверка обновлений недоступна', 'var(--text-dim)', 'ℹ️');
    }
  });
}

async function loadVersionOptions(currentVersion, gen) {
  const versions = await window.pywebview.api.get_versions();
  if (gen !== launchGen) return;
  const sel = document.getElementById('version');
  if (!sel) return;
  sel.innerHTML = '';
  let found = false;
  (versions || []).forEach(v => {
    const o = document.createElement('option');
    o.value = v;
    o.textContent = v;
    if (v === currentVersion) { o.selected = true; found = true; }
    sel.appendChild(o);
  });
  if (!found && sel.options.length) sel.selectedIndex = 0;
  state.version = sel.value || state.version;
  sel.addEventListener('change', () => { state.version = sel.value; updateLaunchSub(); });
  updateLaunchSub();
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
  applyCustomColors(cfg.custom_accent, cfg.custom_bg);
  const themes = [
    { id: 'glass', name: 'Liquid Glass', g1: '#eef7ff', g2: '#8fbcff' },
    { id: 'lunar', name: 'Obsidian Gold', g1: '#f8dda0', g2: '#a9772e' },
    { id: 'purple', name: 'Purple Night', g1: '#a855f7', g2: '#ec4899' },
    { id: 'ocean', name: 'Ocean', g1: '#06b6d4', g2: '#3b82f6' },
    { id: 'forest', name: 'Forest', g1: '#10b981', g2: '#84cc16' },
    { id: 'redsea', name: 'Red Sea', g1: '#ef4444', g2: '#f97316' },
    { id: 'light', name: 'Light', g1: '#8b5cf6', g2: '#ec4899' },
    { id: 'black', name: 'Black', g1: '#ffffff', g2: '#606060' },
  ];
  const cards = themes.map(t => `<div class="theme-card ${cfg.theme === t.id ? 'active' : ''}" data-theme-id="${t.id}" onclick="pickTheme('${t.id}')"><div class="theme-preview" style="background: linear-gradient(135deg, ${t.g1}, ${t.g2});"></div><div class="theme-name">${t.name}</div><div class="theme-check">✓</div></div>`).join('');

  const customOn = !!(_hexToRgb(cfg.custom_accent) || _hexToRgb(cfg.custom_bg));
  const accentVal = _hexToRgb(cfg.custom_accent) ? cfg.custom_accent : currentThemeColor('--accent', '#a9cfff');
  const bgVal = _hexToRgb(cfg.custom_bg) ? cfg.custom_bg : currentThemeColor('--bg', '#05080f');
  const swatches = ['#a9cfff', '#e6b45c', '#a855f7', '#34d399', '#f87171', '#f472b6']
    .map(c => `<button type="button" class="swatch" style="background:${c}" title="${c}" onclick="pickCustomAccent('${c}')"></button>`).join('');

  document.getElementById('content').innerHTML = `
    <div class="page-title"><span class="grad">Настройки</span></div>
    <div class="page-sub">BritonLauncher v3.11.0</div>

    <div class="settings-section" style="margin-bottom:14px;">
      <h3>Тема оформления</h3>
      <div class="theme-grid">${cards}</div>
    </div>

    <div class="settings-section" style="margin-bottom:14px;">
      <div class="switch-row">
        <h3 style="margin:0;">Свои цвета</h3>
        <div id="custom-colors-switch" class="switch ${customOn ? 'on' : ''}" onclick="toggleCustomColors(this)"></div>
      </div>
      <div class="color-grid" id="custom-color-fields">
        <label class="color-field ${customOn ? '' : 'off'}">
          <span>Акцент</span>
          <input type="color" id="custom-accent" value="${accentVal}" ${customOn ? '' : 'disabled'} oninput="previewCustomColors()" />
          <code id="custom-accent-hex">${accentVal}</code>
        </label>
        <label class="color-field ${customOn ? '' : 'off'}">
          <span>Фон</span>
          <input type="color" id="custom-bg" value="${bgVal}" ${customOn ? '' : 'disabled'} oninput="previewCustomColors()" />
          <code id="custom-bg-hex">${bgVal}</code>
        </label>
      </div>
      <div class="swatches">
        ${swatches}
        <button type="button" class="swatch swatch-reset" title="Как в теме" onclick="resetCustomColors()">⟲</button>
      </div>
      <div class="page-status" id="custom-color-status">${customOn ? 'Свои цвета включены' : 'Используются цвета выбранной темы'}</div>
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

/* ---------- Свои цвета ---------- */
function toggleCustomColors(sw) {
  sw.classList.toggle('on');
  previewCustomColors();
}
function previewCustomColors() {
  const sw = document.getElementById('custom-colors-switch');
  const on = !!(sw && sw.classList.contains('on'));
  const a = document.getElementById('custom-accent');
  const b = document.getElementById('custom-bg');
  document.querySelectorAll('#custom-color-fields .color-field').forEach(el => el.classList.toggle('off', !on));
  if (a) a.disabled = !on;
  if (b) b.disabled = !on;
  const accent = a ? a.value : '';
  const bg = b ? b.value : '';
  const ah = document.getElementById('custom-accent-hex');
  const bh = document.getElementById('custom-bg-hex');
  if (ah) ah.textContent = accent;
  if (bh) bh.textContent = bg;
  applyCustomColors(on ? accent : '', on ? bg : '');
  const status = document.getElementById('custom-color-status');
  if (status) {
    status.textContent = on ? 'Свои цвета включены — не забудь сохранить настройки' : 'Используются цвета выбранной темы';
    status.style.color = 'var(--text-mute)';
  }
}
function pickCustomAccent(hex) {
  const sw = document.getElementById('custom-colors-switch');
  const a = document.getElementById('custom-accent');
  if (!sw || !a) return;
  if (!sw.classList.contains('on')) sw.classList.add('on');
  a.value = hex;
  previewCustomColors();
}
function resetCustomColors() {
  const sw = document.getElementById('custom-colors-switch');
  if (sw) sw.classList.remove('on');
  previewCustomColors();
}

async function saveSettings() {
  const ram = (document.getElementById('ram')?.value || '4G').trim() || '4G';
  const show_console = document.getElementById('console-switch').classList.contains('on');
  const customOn = !!document.getElementById('custom-colors-switch')?.classList.contains('on');
  const custom_accent = customOn ? (document.getElementById('custom-accent')?.value || '') : '';
  const custom_bg = customOn ? (document.getElementById('custom-bg')?.value || '') : '';
  const cfg = await window.pywebview.api.get_config();
  await window.pywebview.api.save_settings({
    theme: cfg.theme || 'glass',
    ram,
    show_console,
    version: state.version,
    modloader: state.loader,
    custom_accent,
    custom_bg
  });
  applyCustomColors(custom_accent, custom_bg);
  showToast('Настройки сохранены');
}

window.addEventListener('pywebviewready', async () => {
  try {
    const cfg = await window.pywebview.api.get_config();
    applyTheme(cfg.theme || 'glass');
    applyCustomColors(cfg.custom_accent, cfg.custom_bg);
    state.version = cfg.version || state.version;
    state.loader = cfg.modloader || state.loader;
  } catch (e) { applyTheme('glass'); }
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
        "BritonLauncher v3.11.0",
        html=HTML,
        js_api=api,
        width=1280,
        height=820,
        min_size=(1100, 720),
        frameless=True,
        easy_drag=False,
        background_color="#06080c",
    )
    api._window = window
    webview.start(debug=False)
