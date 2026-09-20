#!/usr/bin/env bash
# text-to-infographic installer (macOS / Linux)
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.sh | bash
#   curl -fsSL https://gitee.com/destinychen/text-to-infographic/raw/main/install.sh | bash   # 国内镜像
#   ./install.sh --check-only        # dry run, writes nothing
#   ./install.sh --repo <git url>    # 指定仓库（fork / 私有镜像）
#
# 仓库来源：先探 GitHub，探不通自动走 Gitee 镜像（两边内容同步）。
# 也可以直接用环境变量 T2I_REPO 指定；克隆失败时会在两个镜像间自动重试。

set -u
GH="https://github.com/Chendestiny/text-to-infographic"
GITEE="https://gitee.com/destinychen/text-to-infographic"
GH_PROBE="https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/SKILL.md"
dest="$HOME/.agents/skills/text-to-infographic"

check_only=0
repo_override=""
while [ $# -gt 0 ]; do
    case "$1" in
        --check-only) check_only=1 ;;
        --repo) shift; repo_override="${1:-}" ;;
        --repo=*) repo_override="${1#--repo=}" ;;
        *) echo "unknown argument: $1"; exit 2 ;;
    esac
    shift
done

ok()   { echo "  [ok]   $1"; }
warn() { echo "  [warn] $1"; }
fail() { echo "  [FAIL] $1"; }
hint() { echo "         -> $1"; }

# 选仓库：显式参数 > T2I_REPO 环境变量 > 探 GitHub（3 秒）> Gitee 镜像
pick_repo() {
    if [ -n "$repo_override" ]; then echo "$repo_override"; return; fi
    if [ -n "${T2I_REPO:-}" ]; then echo "$T2I_REPO"; return; fi
    if curl -fsS --max-time 3 -o /dev/null "$GH_PROBE" 2>/dev/null; then
        echo "$GH"
    else
        echo "$GITEE"
    fi
}

echo ""
echo "text-to-infographic installer"
echo ""

# ---- 1) locate repo ----
if [ -f "$dest/SKILL.md" ]; then
    ok "skill already present: $dest"
elif [ "$check_only" = "1" ]; then
    warn "skill not present; would clone to $dest"
    echo "         would use: $(pick_repo)"
else
    primary="$(pick_repo)"
    if [ "$primary" = "$GH" ]; then others="$GITEE"; else others="$GH"; fi
    echo "repo: $primary"
    cloned=0
    for r in "$primary" "$others"; do
        echo "cloning skill -> $dest"
        if git clone --depth 1 "$r" "$dest" >/dev/null 2>&1 && [ -f "$dest/SKILL.md" ]; then
            ok "cloned from $r"; cloned=1; break
        fi
        warn "clone failed from $r"
        rm -rf "$dest"
    done
    if [ "$cloned" != "1" ]; then
        fail "clone failed from both mirrors (git missing? network?)"
        hint "装 git；或手动下载 zip 解压到 $dest"
        hint "也可以指定仓库：./install.sh --repo <git url>"
        exit 1
    fi
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

# ---- 3) yaml support (the spec gate needs it) ----
# NOTE: contracts.yaml (the contract itself) is YAML, so validate.py cannot run
# without pyyaml even when the spec is .json. Saying "json needs nothing" here
# used to make the spec gate skip silently: validate.py SystemExit'd, and
# run.py still reported exit=0.
if "$py" -c "import yaml" >/dev/null 2>&1; then
    ok "pyyaml present (spec gate + .yaml specs available)"
else
    warn "pyyaml missing: the spec gate cannot run (contracts.yaml is YAML)"
    hint "pip install pyyaml"
    if [ "$check_only" != "1" ]; then
        "$py" -m pip install --quiet pyyaml && ok "pyyaml installed" \
            || warn "auto-install failed; the spec gate will be skipped, install it manually"
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
    echo "running doctor..."
    "$py" "$dest/scripts/doctor.py"
    hint "doctor 若提示「只有 CDP 后端可用」，渲染前请设：export T2I_BACKEND=cdp"
fi

echo ""
echo "next:"
echo "  把这句话发给你的 Agent（不要自己去敲命令）："
echo "    用 text-to-infographic（$dest）"
echo "    把 <你的文章路径> 转成小红书图文，输出到桌面"
echo ""
echo "  Agent 会按 SKILL.md 走五步：读文章 → 写规格 → 过规格门 → 跑流水线 → 逐张自检后交付。"
echo ""