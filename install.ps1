# text-to-infographic installer (Windows)
# Usage:
#   irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
#   irm https://gitee.com/destinychen/text-to-infographic/raw/main/install.ps1 | iex     # 国内镜像
#   .\install.ps1 -CheckOnly          # dry run, writes nothing
#   .\install.ps1 -Repo <git url>     # 指定仓库（fork / 私有镜像）
#
# 仓库来源：先探 GitHub，探不通自动走 Gitee 镜像（两边内容同步）。
# 也可以用环境变量 T2I_REPO 指定；克隆失败时会在两个镜像之间自动重试。
#
# 踩过的坑（都在真机上复现过，别再改回去）：
#  1) PS 5.1 里 "$v:" 会被当成「驱动器限定变量引用」直接报**解析错误** —— 不是运行时，
#     是整份脚本一个字都跑不了。必须写 "${v}:"。默认 Win10/11 只有 PS 5.1，影响面 100%。
#  2) 这个文件含中文，**必须存成 UTF-8 with BOM**。PS 5.1 把无 BOM 的文件按 ANSI(GBK) 读，
#     中文注释会被解码成乱码，进而破坏后面的引号/花括号配对，报出一堆莫名其妙的语法错。
#  3) $ErrorActionPreference="Stop" + 原生命令往 stderr 写进度（git clone / pip 都会）
#     → 被包成 NativeCommandError 掀翻脚本。症状是"克隆其实成功了，但脚本提前退出、doctor 没跑"。
#     所以原生命令统一走 Native() 包一层。

param([switch]$CheckOnly, [string]$Repo)

$ErrorActionPreference = "Stop"

$GH = "https://github.com/Chendestiny/text-to-infographic"
$GITEE = "https://gitee.com/destinychen/text-to-infographic"
$GH_PROBE = "https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/SKILL.md"
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

# 选仓库：显式参数 > T2I_REPO 环境变量 > 探 GitHub（3 秒）> Gitee 镜像
function PickRepo {
    if ($Repo) { return $Repo }
    if ($env:T2I_REPO) { return $env:T2I_REPO }
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        Invoke-WebRequest -Uri $GH_PROBE -TimeoutSec 3 -UseBasicParsing | Out-Null
        return $GH
    } catch {
        return $GITEE
    } finally {
        $ErrorActionPreference = $old
    }
}

Say ""
Say "text-to-infographic installer"
Say ""

# ---- 1) locate repo (already cloned? otherwise clone) ----
if (Test-Path (Join-Path $dest "SKILL.md")) {
    Ok "skill already present: $dest"
} elseif ($CheckOnly) {
    Warn "skill not present; would clone to $dest"
    Say "         would use: $(PickRepo)"
} else {
    $primary = PickRepo
    $others = @($GH, $GITEE) | Where-Object { $_ -ne $primary }
    Say "repo: $primary"
    foreach ($r in @($primary) + $others) {
        Say "cloning skill -> $dest"
        Native "git" @("clone", "--depth", "1", $r, $dest) | Out-Null
        if (Test-Path (Join-Path $dest "SKILL.md")) { Ok "cloned from $r"; break }
        Warn "clone failed from $r"
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue }
    }
    if (-not (Test-Path (Join-Path $dest "SKILL.md"))) {
        Fail "clone failed from both mirrors (git missing? network? proxy?)"
        Hint "装 git：winget install Git.Git"
        Hint "或手动下载 zip 解压到 $dest"
        Hint "也可以指定仓库：.\install.ps1 -Repo <git url>"
        exit 1
    }
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