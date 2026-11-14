# Launcher for prose_check.py, run by hooks.json as `sh run.sh`.
#
# The hook is stdlib-only Python, so any working python3 runs it; uv is the
# fallback for machines that have uv but no usable Python. With neither, it
# says nothing. A missing or broken interpreter costs a reminder, never an
# error on every edit, so this script always exits 0.
hook="${0%/*}/prose_check.py"

usable_python3() {
    command -v python3 >/dev/null 2>&1 || return 1
    # On macOS without the command line tools, /usr/bin/python3 is a stub that
    # fails and can open an install dialog when run. Don't run it to find out.
    if [ "$(command -v python3)" = /usr/bin/python3 ] && command -v xcode-select >/dev/null 2>&1; then
        xcode-select -p >/dev/null 2>&1 || return 1
    fi
    python3 -c '' >/dev/null 2>&1
}

if usable_python3; then
    python3 "$hook"
elif command -v uv >/dev/null 2>&1; then
    uv run --quiet --script "$hook" 2>/dev/null
fi
exit 0
