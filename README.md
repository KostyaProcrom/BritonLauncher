# BritonLauncher

Красивый лаунчер Minecraft для Windows на Python (pywebview + `minecraft-launcher-lib`).

> Не связан с Mojang или Microsoft. Minecraft — торговая марка Mojang AB.

## Возможности

- 👤 **Аккаунты сайта** — регистрация и вход на сайте проекта, вход в лаунчер по коду с сайта.
- 🛡️ **Роли и админ-панель** — главный админ `KostyaKosmos`, админ `BritonLauncher`; панель управления аккаунтами на сайте и раздел «Админка» в лаунчере.
- 🎮 **Офлайн-режим** — можно играть по нику без аккаунта.
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
3. Введи ник и жми «Играть». Для аккаунта сайта: сайт → «Аккаунт» → «Получить код для лаунчера», затем в лаунчере «Войти по коду».

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

## Вход через сайт

Аккаунты создаются на сайте BritonLauncher (раздел «Аккаунт»). Пароли хранятся в браузере
в виде соли и SHA-256, на сервер ничего не отправляется — это клиентские аккаунты сайта.

1. Открой сайт → «Аккаунт» → зарегистрируйся или войди.
2. Нажми **«Получить код для лаунчера»** и скопируй код.
3. В лаунчере нажми **«Войти по коду»**, вставь код и войди.

Код подписан HMAC-SHA256 и действует 7 дней. Роль (игрок / админ / главный админ)
определяется по нику и подписи. Управление аккаунтами доступно администраторам
в разделе «Админка» лаунчера (открывает админ-панель сайта).

> Важно: это клиентская схема без сервера. Секрет подписи и база аккаунтов находятся
> в браузере/исходниках, поэтому защита рассчитана на честных пользователей, а не на
> злоумышленника с доступом к файлам. Для настоящей авторизации нужен сервер (Supabase и т.п.).

## Где хранятся данные

```
%LOCALAPPDATA%\.britonlauncher\
├── config.json        настройки + аккаунт сайта
├── nickname.txt       сохранённый ник
├── account.json       старые токены Microsoft (если остались)
├── servers.dat        список серверов
├── mods\
├── resourcepacks\
├── shaderpacks\
└── custom_menu\index.html
```

Аккаунты сайта хранятся в браузере (`localStorage`), а в лаунчере — только ник и роль
в `config.json`. Пароли на сайт не передаются: хранится соль и SHA-256.

## Структура проекта

```
main.py               лаунчер (GUI + логика + вход по коду с сайта)
microsoft_login.py    старый отдельный скрипт токена (не используется интерфейсом)
requirements.txt      зависимости Python
build_exe.bat         сборка .exe
run.bat               быстрый запуск из исходников
docs/                 сайт для GitHub Pages
```

## Сайт (GitHub Pages)

Сайт лежит в `docs/` и публикуется через GitHub Actions (`.github/workflows/pages.yml`):
каждый пуш в `main` пересобирает страницу. Адрес:
`https://kostyaprocrom.github.io/BritonLauncher/`.

## Правовая информация

Лицензия на исходный код не предоставляется: все права сохранены за автором.

- Лаунчер не обходит и не отключает аутентификацию, проверку владения игрой или лицензионные проверки.
- Для игры в online-режиме нужен официальный аккаунт Minecraft.
- Пароли сайта не передаются в лаунчер: он получает только ник и роль по подписанному коду.

### English summary

BritonLauncher is a free custom Minecraft launcher for Windows. Accounts are created on the
project website (browser-local, salted SHA-256 passwords). The launcher accepts a signed
HMAC code from the website to learn the nickname and role (player/admin), then launches the
game offline by nickname. It can also install official game versions, Fabric/Forge loaders,
and download mods/resource packs/shaders from Modrinth. It does not bypass authentication,
ownership or license checks.
