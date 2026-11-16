"""
Получить токен Microsoft/Minecraft (online-mode).

Запуск:
    python microsoft_login.py <CLIENT_ID> [REDIRECT_URI]

Или задай переменные окружения MS_CLIENT_ID / MS_REDIRECT_URI.
Токен сохраняется в %LOCALAPPDATA%\\.britonlauncher\\account.json

ВАЖНО:
- Нужен Azure App (Client ID) с платформой "Mobile and desktop applications".
- Redirect URI должен быть добавлен в этом Azure App.
- Новым приложениям нужно одобрение доступа к Minecraft API:
  https://aka.ms/mce-reviewappid
"""
import os
import sys
import json
import webbrowser

import minecraft_launcher_lib


DEFAULT_REDIRECT = "https://login.microsoftonline.com/common/oauth2/nativeclient"


def get_client_id():
    if os.environ.get("MS_CLIENT_ID"):
        return os.environ["MS_CLIENT_ID"].strip()
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    return ""


def get_redirect_uri():
    if os.environ.get("MS_REDIRECT_URI"):
        return os.environ["MS_REDIRECT_URI"].strip()
    if len(sys.argv) > 2:
        return sys.argv[2].strip()
    return DEFAULT_REDIRECT


def account_path():
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(base, ".britonlauncher", "account.json")


def main():
    client_id = get_client_id()
    redirect_uri = get_redirect_uri()

    if not client_id:
        print("Укажи Client ID:")
        print("  python microsoft_login.py <CLIENT_ID> [REDIRECT_URI]")
        print("  или переменная окружения MS_CLIENT_ID")
        return 1

    print("Client ID     :", client_id)
    print("Redirect URI  :", redirect_uri)
    print()

    try:
        url, state, verifier = minecraft_launcher_lib.microsoft_account.get_secure_login_data(
            client_id, redirect_uri
        )
    except Exception as e:
        print("Не удалось создать ссылку логина:", e)
        return 1

    print("1) Открываю браузер (если не открылся — открой ссылку вручную):")
    print()
    print(url)
    print()
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("2) Войди в аккаунт Microsoft.")
    print("3) После входа тебя перебросит на redirect-URL. Скопируй ВСЮ строку")
    print("   адреса (там есть ?code=...) и вставь сюда.")
    print()

    try:
        redirected = input("Redirect URL: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nОтменено.")
        return 1

    if not redirected:
        print("Пустой URL.")
        return 1

    try:
        auth_code = minecraft_launcher_lib.microsoft_account.parse_auth_code_url(
            redirected, state
        )
    except AssertionError:
        print("Ошибка: state не совпал. Запусти заново.")
        return 1
    except KeyError:
        print("Ошибка: в URL нет параметра code.")
        return 1
    except Exception as e:
        print("Ошибка разбора URL:", e)
        return 1

    print("\nОбмениваю код на токен...")
    try:
        data = minecraft_launcher_lib.microsoft_account.complete_login(
            client_id, None, redirect_uri, auth_code, verifier
        )
    except Exception as e:
        name = type(e).__name__
        print("\nОшибка авторизации:", name, "-", e)
        if name == "AzureAppNotPermitted":
            print("→ Твоему Azure App не дали доступ к Minecraft API:")
            print("  https://aka.ms/mce-reviewappid")
        if name == "AccountNotOwnMinecraft":
            print("→ У аккаунта нет купленного Minecraft.")
        return 1

    print("\n=== ТОКЕН ПОЛУЧЕН ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    path = account_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\nСохранено в:", path)
    except Exception as e:
        print("\nНе удалось сохранить account.json:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
