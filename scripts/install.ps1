# Install Mystic Pointer for the current Windows user.
#
#   .\scripts\install.ps1
#   irm https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/install.ps1 | iex
#
# Environment overrides:
#   MYSTIC_POINTER_SOURCE   Local checkout, archive URL, or git URL to install
#   MYSTIC_POINTER_REPO     GitHub owner/repository (default: your-username/mystic-pointer)
#   MYSTIC_POINTER_REF      Git ref used for the archive download (default: main)
#   MYSTIC_POINTER_PYTHON   Python executable to use (default: py -3, then python)
#   MYSTIC_POINTER_HOME     Installation directory (default: %LOCALAPPDATA%\Programs\Mystic Pointer)

#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$AppId = "mystic-pointer"
$AppName = "Mystic Pointer"
$DefaultRepo = "your-username/mystic-pointer"

$Repo = if ($env:MYSTIC_POINTER_REPO) { $env:MYSTIC_POINTER_REPO } else { $DefaultRepo }
$Ref = if ($env:MYSTIC_POINTER_REF) { $env:MYSTIC_POINTER_REF } else { "main" }
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE "AppData\Local" }
$InstallDir = if ($env:MYSTIC_POINTER_HOME) { $env:MYSTIC_POINTER_HOME } else { Join-Path $LocalAppData "Programs\Mystic Pointer" }
$VenvDir = Join-Path $InstallDir "venv"
$ShimDir = Join-Path $InstallDir "bin"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Say([string]$Message) {
    Write-Host "  $Message"
}

function Fail([string]$Message) {
    throw "Error: $Message"
}

# Prefer the checkout that contains this script.  When the script is piped from
# irm there is no checkout, so pip downloads the release archive instead.
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { "" }
$RepoRoot = if ($ScriptDir) { Split-Path $ScriptDir -Parent } else { "" }

if ($env:MYSTIC_POINTER_SOURCE) {
    $Source = $env:MYSTIC_POINTER_SOURCE
} elseif ($RepoRoot -and (Test-Path -LiteralPath (Join-Path $RepoRoot "pyproject.toml"))) {
    $Source = $RepoRoot
} else {
    $Source = "https://github.com/$Repo/archive/refs/heads/$Ref.zip"
}

$PythonExe = $null
$PythonPrefix = @()
if ($env:MYSTIC_POINTER_PYTHON) {
    $PythonExe = $env:MYSTIC_POINTER_PYTHON
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonExe = "py"
    $PythonPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
} else {
    Fail "Python 3.10+ was not found. Install Python from python.org and try again."
}

& $PythonExe @PythonPrefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Fail "Python 3.10+ is required."
}

Say "Installing $AppName into $InstallDir"

if (Test-Path -LiteralPath $VenvDir) {
    Remove-Item -LiteralPath $VenvDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $InstallDir, $ShimDir | Out-Null

& $PythonExe @PythonPrefix -m venv $VenvDir
if ($LASTEXITCODE -ne 0) {
    Fail "Could not create the virtual environment."
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Fail "Could not update pip."
}

& $VenvPython -m pip install $Source
if ($LASTEXITCODE -ne 0) {
    Fail "Could not install Mystic Pointer."
}

$Launcher = Join-Path $ShimDir "$AppId.cmd"
@"
@echo off
"$VenvPython" -m mystic_pointer.app %*
"@ | Set-Content -LiteralPath $Launcher -Encoding ASCII

# Add the launcher folder to the user PATH so ``mystic-pointer`` works from a
# new terminal.  The current session is updated as well.
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$PathParts = @()
if ($UserPath) {
    $PathParts = @($UserPath -split ";" | Where-Object { $_ })
}
$NormalizedShim = $ShimDir.TrimEnd("\")
$HasShim = $false
foreach ($Part in $PathParts) {
    if ($Part.TrimEnd("\") -ieq $NormalizedShim) {
        $HasShim = $true
        break
    }
}
if (-not $HasShim) {
    $NewPath = (@($PathParts) + $ShimDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
}
$env:Path = "$ShimDir;$env:Path"

# Generate a branded shortcut icon from the app's own pointer mark.
$IconPath = Join-Path $InstallDir "$AppId.ico"
$IconScript = @'
import sys

from PySide6.QtWidgets import QApplication

from mystic_pointer.ui.icons import make_pointer_pixmap
from mystic_pointer.ui.style import ACCENT

app = QApplication([])
pixmap = make_pointer_pixmap(256, color="#ffffff", background=ACCENT, radius=56)
raise SystemExit(0 if pixmap.save(sys.argv[1], "ICO") else 1)
'@
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = "offscreen"
$IconScript | & $VenvPython - $IconPath
$IconReady = ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $IconPath))
if ($null -eq $PreviousQtPlatform) {
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
} else {
    $env:QT_QPA_PLATFORM = $PreviousQtPlatform
}

$StartMenu = [Environment]::GetFolderPath("Programs")
$ShortcutPath = Join-Path $StartMenu "$AppName.lnk"
$Pythonw = Join-Path $VenvDir "Scripts\pythonw.exe"
$Target = if (Test-Path -LiteralPath $Pythonw) { $Pythonw } else { $VenvPython }

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.Arguments = "-m mystic_pointer.app"
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "Screen-aware AI assistant"
if ($IconReady) {
    $Shortcut.IconLocation = "$IconPath,0"
}
$Shortcut.Save()

Say "Installed."
Say "Launch Mystic Pointer from the Start menu or run: $AppId"
Say "The terminal PATH update applies to new windows."
