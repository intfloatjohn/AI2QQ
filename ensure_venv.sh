# Shared by setup.sh, start.sh and deploy_debian.sh (sourced, not run directly).
#
# Makes sure ./venv is a working virtual environment for THIS machine and THIS folder.
# A venv copied from another computer or folder (or built with a different Python version)
# looks fine but its scripts point at the old paths, so pip silently falls back to the system
# pip and Debian/Ubuntu refuse with "externally-managed-environment". Such a venv is rebuilt.
#
# After this runs, VENV_PY is the venv's python. Always install with "$VENV_PY" -m pip,
# never a bare "pip", so the system Python is never touched.

venv_problem() {
    local dir="$1/venv"
    local py="$dir/bin/python"
    [ -x "$py" ] || { echo "no venv/bin/python"; return; }
    "$py" -c "import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)" 2>/dev/null \
        || { echo "venv/bin/python does not run (built on another machine?)"; return; }
    local want have
    want=$(python3 -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>/dev/null)
    have=$("$py" -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>/dev/null)
    [ -z "$want" ] || [ "$want" = "$have" ] \
        || { echo "built with Python $have, this system has Python $want"; return; }
    local real_here real_prefix
    real_here=$(cd "$dir" && pwd -P)
    real_prefix=$("$py" -c "import os, sys; print(os.path.realpath(sys.prefix))" 2>/dev/null)
    [ "$real_here" = "$real_prefix" ] \
        || { echo "it belongs to another folder ($real_prefix)"; return; }
    if [ -f "$dir/bin/pip" ]; then
        local shebang
        shebang=$(head -n 1 "$dir/bin/pip")
        case "$shebang" in
            *"$dir/bin/python"*|*"$real_here/bin/python"*) ;;
            *) echo "its scripts point to another location (${shebang#\#!})"; return ;;
        esac
    fi
    "$py" -m pip --version >/dev/null 2>&1 || { echo "pip is missing inside the venv"; return; }
}

ensure_venv() {
    local base="$1"
    local problem
    if [ -e "$base/venv" ]; then
        problem=$(venv_problem "$base")
        if [ -n "$problem" ]; then
            echo "[!] The existing venv/ can't be used: $problem."
            echo "[*] Rebuilding it for this machine..."
            rm -rf "$base/venv"
        fi
    fi
    if [ ! -d "$base/venv" ]; then
        echo "[*] Creating Python virtual environment (venv)..."
        if ! python3 -m venv "$base/venv"; then
            echo "[x] Could not create the venv. On Debian/Ubuntu install it with:"
            echo "      sudo apt-get install python3-venv"
            return 1
        fi
        "$base/venv/bin/python" -m pip install -q --upgrade pip || return 1
    fi
    VENV_PY="$base/venv/bin/python"
    export VENV_PY
}
