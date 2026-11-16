# BritonLauncher

Красивый лаунчер Minecraft для Windows на Python (pywebview + `minecraft-launcher-lib`).

> Не связан с Mojang или Microsoft. Minecraft — торговая марка Mojang AB.

## Возможности

- 🔐 **Вход через Microsoft** — официальный OAuth 2.0 (Authorization Code + PKCE), Xbox Live / XSTS, проверка владения игрой.
- 👤 **Офлайн-режим** — можно играть по нику без аккаунта.
- 🧩 **Fabric и Forge** — установка модлоадеров одной кнопкой под выбранную версию.
- 📦 **Modrinth внутри** — поиск и установка модов, ресурспаков и шейдеров.
- 🎚️ **Любая релизная версия** Minecraft и настройка оперативной памяти (`4G`, `2048M`).
- 🎨 **6 тем оформления** и поддержка своего HTML-экрана (`custom_menu/index.html`).
- 🖥️ **Отдельное окно консоли** с логами игры.
- 🔄 **Проверка обновлений** лаунчера через GitHub Releases.

## Скриншоты

Сайт проекта (GitHub Pages) — папка [`docs/`](docs/). Там же мокап интерфейса.

## Установка (для пользователей)

1. Скачай `BritonLauncher.exe` со страницы [Releases](../../releases/latest).
2. Запусти файл.
3. Войди через Microsoft или введи ник и жми «Играть».

Ничего дополнительно ставить не нужно — все зависимости внутри `.exe`.

## Запуск из исходников

```powershell
pip install -r requirements.txt
python main.py
```

Требуется Python 3.10+ (проверено на 3.15) и Windows 10/11 x64.

## Сборка `.exe`

```powershell
build_exe.bat
```

Скрипт создаёт venv, ставит зависимости и собирает `dist\BritonLauncher.exe` через PyInstaller.
Либо вручную:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed ^
  --name BritonLauncher ^
  --collect-all webview ^
  --collect-all minecraft_launcher_lib ^
  main.py
```

## Вход через Microsoft (свой Azure App)

Токен нельзя получить без собственного Azure-приложения — чужой `client_id` использовать нельзя.

1. [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID → App registrations → New registration**.
2. Supported account types: **Personal Microsoft accounts**.
3. **Authentication → Add platform → Mobile and desktop applications**, redirect URI:
   ```
   https://login.microsoftonline.com/common/oauth2/nativeclient
   ```
4. Скопируй **Application (client) ID**.
5. Новым приложениям нужно одобрение доступа к Minecraft API: https://aka.ms/mce-reviewappid
6. Вставь `Client ID` в **Настройках** лаунчера (или запусти `python microsoft_login.py <CLIENT_ID>`).

Redirect URI по умолчанию уже прописан в лаунчере и должен совпадать с настройкой Azure-приложения.

## Где хранятся данные

```
%LOCALAPPDATA%\.britonlauncher\
├── config.json        настройки
├── nickname.txt       сохранённый ник
├── account.json       токены Microsoft (только локально)
├── servers.dat        список серверов
├── mods\
├── resourcepacks\
├── shaderpacks\
└── custom_menu\index.html
```

`account.json` никогда не отправляется наружу и используется только для запуска игры.

## Структура проекта

```
main.py               лаунчер (GUI + логика)
microsoft_login.py    отдельный скрипт получения токена
requirements.txt      зависимости Python
build_exe.bat         сборка .exe
run.bat               быстрый запуск из исходников
docs/                 сайт для GitHub Pages
```

## Сайт (GitHub Pages)

Сайт лежит в `docs/` и публикуется так:

1. Settings → Pages → **Source: Deploy from a branch**.
2. Branch: `main`, folder: **`/docs`**.
3. В `docs/script.js` замени `const REPO = "your-username/britonlauncher";` на свой репозиторий.

## Правовая информация

Лицензия на исходный код не предоставляется: все права сохранены за автором.

- Лаунчер не обходит и не отключает аутентификацию, проверку владения игрой или лицензионные проверки.
- Аккаунты без купленного Minecraft не могут запустить игру в online-режиме.
- Пароль Microsoft никогда не запрашивается и не хранится.

### English summary

BritonLauncher is a free custom Minecraft launcher for Windows. It authenticates users
via the standard Microsoft OAuth 2.0 authorization code flow with PKCE (public client,
no client secret), then Xbox Live / XSTS and the official Minecraft Services API, and
verifies game ownership before allowing launch. It does not bypass authentication,
ownership or license checks. Tokens are stored only locally on the user's machine.
It can also install official game versions, Fabric/Forge loaders, and download
mods/resource packs/shaders from Modrinth.
