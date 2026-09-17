#!/usr/bin/env bash
# text-to-infographic installer (macOS / Linux)
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.sh | bash
#   ./install.sh --check-only     # dry run, writes nothing

set -u
repo="https://github.com/Chendestiny/text-to-infographic"
dest="$HOME/.agents/skills/text-to-infographic"
check_only=0
[ "${1:-}" = "--check-only" ] && check_only=1

say()  { echo "$m" >/dev/null; echo "$1"; }
ok()   { echo "  [ok]   $1"; }
warn() { echo "  [warn] $1"; }
fail() { echo "  [FAIL] $1"; }
hint() { echo "         -> $1"; }

echo ""
say "text-to-infographic installer"
say "repo: $repo"
echo ""

# ---- 1) locate repo ----
if [ -f "$dest/SKILL.md" ]; then
    ok "skill already present: $dest"
elif [ "$check_only" = "1" ]; then
    warn "skill not present; would clone to $dest"
else
    say "cloning skill -> $dest"
    git clone --depth 1 "$repo" "$dest" || { fail "clone failed (git missing?)"; exit 1; }
    ok "cloned"
fi

# ---- 2) python ----
py=""
for c in python3 python; do
    command -v "$c" >/dev/null 2>&1 && { py="$(command -v "$c")"; break; }
done
if [ -n "$py" ]; then
    v=$("$py" -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>/dev/null)
    ok "python $v: $py"
else
    fail "python3 not found"
    hint "macOS: brew install python3   |   Debian/Ubuntu: sudo apt install python3"
    exit 1
fi

# ---- 3) yaml support (optional) ----
if "$py" -c "import yaml" >/dev/null 2>&1; then
    ok "pyyaml present (.yaml specs available)"
else
    warn "pyyaml missing: .yaml specs need it; .json specs need nothing"
    hint "pip install pyyaml"
    if [ "$check_only" != "1" ]; then
        "$py" -m pip install --quiet pyyaml && ok "pyyaml installed" \
            || warn "auto-install failed; use .json specs or install manually"
    fi
fi

# ---- 4) chromium browser ----
browser=""
for c in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge; do
    command -v "$c" >/dev/null 2>&1 && { browser="$(command -v "$c")"; break; }
done
[ -z "$browser" ] && [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] \
    && browser="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -n "$browser" ]; then
    ok "browser: $browser"
else
    warn "no Chrome/Chromium/Edge found"
    hint "install one, or export T2I_BROWSER=/path/to/chrome"
fi

# ---- 5) font integrity ----
font="$dest/assets/fonts/ZCOOLKuaiLe-Regular.ttf"
if [ -f "$font" ]; then
    ok "bundled font present ($(( $(stat -c%s "$font" 2>/dev/null || stat -f%z "$font") / 1048576 )) MB)"
else
    warn "font missing (will degrade to system fonts)"
fi

# ---- 6) doctor ----
if [ "$check_only" != "1" ]; then
    echo ""
    say "running doctor..."
    "$py" "$dest/scripts/doctor.py"
fi

echo ""
say "next:"
say "  cd $dest"
say "  python3 scripts/build.py examples/agent-roadmap.json -o build/"
say "  python3 scripts/render.py build/ -o out/"
echo ""
say 'agent users: just say  "turn this article into a carousel"  and follow SKILL.md'
echo ""
