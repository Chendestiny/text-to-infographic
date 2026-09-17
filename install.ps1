# text-to-infographic installer (Windows)
# Usage:
#   irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
#   .\install.ps1 -CheckOnly     # dry run, writes nothing

param([switch]$CheckOnly)

$ErrorActionPreference = "Stop"
$repo = "https://github.com/Chendestiny/text-to-infographic"
$dest = Join-Path $env:USERPROFILE ".agents\skills\text-to-infographic"

function Say($m)  { Write-Host $m }
function Ok($m)   { Write-Host "  [ok]   $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [warn] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red }
function Hint($m) { Write-Host "         -> $m" -ForegroundColor DarkGray }

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
    git clone --depth 1 $repo $dest 2>$null
    if (-not (Test-Path (Join-Path $dest "SKILL.md"))) { Fail "clone failed (git missing?)"; exit 1 }
    Ok "cloned"
}

# ---- 2) python ----
$py = $null
foreach ($c in @("python", "python3", "py")) {
    $found = Get-Command $c -ErrorAction SilentlyContinue
    if ($found) { $py = $found.Source; break }
}
if ($py) {
    $v = & $py -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
    Ok "python $v: $py"
} else {
    Fail "python not found"
    Hint "winget install Python.Python.3.12   (then reopen the terminal)"
    if ($CheckOnly) { exit 1 } else { exit 1 }
}

# ---- 3) yaml support (optional; .json specs need nothing) ----
& $py -c "import yaml" 2>$null
if ($LASTEXITCODE -eq 0) {
    Ok "pyyaml present (.yaml specs available)"
} else {
    Warn "pyyaml missing: .yaml specs need it; .json specs need nothing"
    Hint "pip install pyyaml"
    if (-not $CheckOnly) {
        & $py -m pip install --quiet pyyaml
        if ($LASTEXITCODE -eq 0) { Ok "pyyaml installed" } else { Warn "auto-install failed; use .json specs or install manually" }
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
    & $py (Join-Path $dest "scripts\doctor.py")
}

Say ""
Say "next:"
Say '  cd ' + $dest
Say "  python scripts\build.py examples\agent-roadmap.json -o build\"
Say "  python scripts\render.py build\ -o out\"
Say ""
Say "agent users: just say  \"turn this article into a carousel\"  and follow SKILL.md"
Say ""
