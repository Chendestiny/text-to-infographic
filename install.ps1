# text-to-infographic installer (Windows)
# Usage:
#   irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
#   .\install.ps1 -CheckOnly     # dry run, writes nothing
#
# 踩过的坑（都在真机上复现过，别再改回去）：
#  1) PS 5.1 里 "$v:" 会被当成「驱动器限定变量引用」直接报错，必须写 "${v}:"。
#     影响面极大：默认 Win10/11 只有 Windows PowerShell 5.1，一行安装会必挂。
#  2) $ErrorActionPreference="Stop" + 原生命令把进度写到 stderr（git clone / pip 都会）
#     → PowerShell 包成 NativeCommandError 并终止脚本。症状是"克隆其实成功了，但脚本
#     提前退出、doctor 没跑"。所以原生命令统一走 Native() 包一层。

param([switch]$CheckOnly)

$ErrorActionPreference = "Stop"

$repo = "https://github.com/Chendestiny/text-to-infographic"
$dest = Join-Path $env:USERPROFILE ".agents\skills\text-to-infographic"

function Say($m)  { Write-Host $m }
function Ok($m)   { Write-Host "  [ok]   $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [warn] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red }
function Hint($m) { Write-Host "         -> $m" -ForegroundColor DarkGray }

# 跑原生命令：临时放宽 ErrorActionPreference，免得 stderr 的一行进度把整个脚本掀翻。
# 返回 @{code=退出码; out=标准输出}
function Native($exe, [string[]]$exeArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $exe @exeArgs 2>&1 | ForEach-Object { "$_" }
        return @{ code = $LASTEXITCODE; out = ($out -join "`n") }
    } finally {
        $ErrorActionPreference = $old
    }
}

Say ""
Say "text-to-infographic installer"
Say "repo: $repo"
Say ""

# ---- 1) locate repo (already cloned? otherwise clone) ----
if (Test-Path (Join-Path $dest "SKILL.md")) {
    Ok "skill already present: $dest"
} elseif ($CheckOnly) {
    Warn "skill not present; would clone to $dest"
} else {
    Say "cloning skill -> $dest"
    $r = Native "git" @("clone", "--depth", "1", $repo, $dest)
    if (-not (Test-Path (Join-Path $dest "SKILL.md"))) {
        Fail "clone failed (git missing? no network? proxy?)"
        Hint "装 git：winget install Git.Git"
        Hint "或手动下载 zip 解压到 $dest"
        exit 1
    }
    Ok "cloned"
}

# ---- 2) python ----
$py = $null
foreach ($c in @("python", "python3", "py")) {
    $found = Get-Command $c -ErrorAction SilentlyContinue
    if ($found) { $py = $found.Source; break }
}
if ($py) {
    $r = Native $py @("-c", "import sys;print('%d.%d' % sys.version_info[:2])")
    # ★ 必须 ${v}: 而不是 $v: —— 见文件头坑 1
    Ok "python $($r.out.Trim()): $py"
    & $py -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,8) else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) { Warn "python 低于 3.8；脚本用的是标准库，3.8+ 才保证可用" }
} else {
    Fail "python not found"
    Hint "winget install Python.Python.3.12   (then reopen the terminal)"
    exit 1
}

# ---- 3) yaml support (optional; .json specs need nothing) ----
$r = Native $py @("-c", "import yaml")
if ($r.code -eq 0) {
    Ok "pyyaml present (.yaml specs available)"
} else {
    Warn "pyyaml missing: .yaml specs need it; .json specs need nothing"
    Hint "pip install pyyaml"
    if (-not $CheckOnly) {
        $r2 = Native $py @("-m", "pip", "install", "--quiet", "pyyaml")
        if ($r2.code -eq 0) { Ok "pyyaml installed" }
        else { Warn "auto-install failed; use .json specs or install manually" }
    }
}

# ---- 4) chromium browser ----
$browsers = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
)
$browser = $browsers | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($browser) { Ok "browser: $browser" }
else {
    Warn "no Chrome/Edge found"
    Hint "install one, or set T2I_BROWSER=C:\path\to\chrome.exe"
}

# ---- 5) font integrity ----
$font = Join-Path $dest "assets\fonts\ZCOOLKuaiLe-Regular.ttf"
if (Test-Path $font) { Ok "bundled font present ($([math]::Round((Get-Item $font).Length/1MB,1)) MB)" }
else { Warn "font missing (will degrade to system fonts)" }

# ---- 6) doctor ----
if (-not $CheckOnly) {
    Say ""
    Say "running doctor..."
    $r = Native $py @((Join-Path $dest "scripts\doctor.py"))
    Say $r.out
    Hint "doctor 若提示「只有 CDP 后端可用」，渲染前请设：`$env:T2I_BACKEND='cdp'"
}

Say ""
Say "next:"
Say "  把这句话发给你的 Agent（不要自己去敲命令）："
Say "    用 text-to-infographic（$dest）"
Say "    把 <你的文章路径> 转成小红书图文，输出到桌面"
Say ""
Say "  Agent 会按 SKILL.md 走五步：读文章 → 写规格 → 过规格门 → 跑流水线 → 逐张自检后交付。"
Say ""