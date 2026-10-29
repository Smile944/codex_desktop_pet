#!/bin/bash
# Finder and Terminal entry point. No downloads or system changes here.
set -u
ROOT="$(cd -- "$(/usr/bin/dirname -- "$0")" && pwd)" || exit 1

usable_python() {
    [ -x "$1" ] && "$1" -c 'import sys, argparse, json, pathlib, plistlib, sqlite3; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

PYTHON=""
# Codex may already have downloaded its shared runtime; do not depend on a chat ID.
for candidate in \
    "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" \
    "$HOME"/.cache/codex-runtimes/*/dependencies/python/bin/python3 \
    /Applications/Codex.app/Contents/Resources/python/bin/python3; do
    if usable_python "$candidate"; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    for candidate in "$(command -v python3 || true)" /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
        if usable_python "$candidate"; then
            PYTHON="$candidate"
            break
        fi
    done
fi
if [ -z "$PYTHON" ]; then
    echo '无法找到可用的 Python 3.9 或更新版本。' >&2
    echo '请先准备 Python 3，或在 Codex 中初始化其自带的 Python 运行环境，然后重新运行 Install.command。' >&2
    echo '安装器不会下载依赖或安装系统工具。' >&2
    exit 1
fi
exec "$PYTHON" -B "$ROOT/codex/setup.py" "$@"
