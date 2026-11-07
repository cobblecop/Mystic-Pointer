# Uninstall Mystic Pointer for the current Windows user.
#
#   .\scripts\uninstall.ps1
#   irm https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.ps1 | iex
#
# By default the configuration and API keys are preserved.  Set
# MYSTIC_POINTER_PURGE=1 before running to remove them as well:
#
#   $env:MYSTIC_POINTER_PURGE="1"; irm https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.ps1 | iex
#
# Saved screenshots are never deleted.

#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$AppId = "mystic-pointer"
$AppName = "Mystic Pointer"
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE "AppData\Local" }
$InstallDir = if ($env:MYSTIC_POINTER_HOME) { $env:MYSTIC_POINTER_HOME } else { Join-Path $LocalAppData "Programs\Mystic Pointer" }
$ShimDir = Join-Path $InstallDir "bin"
$Purge = ($env:MYSTIC_POINTER_PURGE -eq "1")

function Say([string]$Message) {
    Write-Host "  $Message"
}

# Stop a running tray process launched from this installation.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.ExecutablePath -and
        $_.ExecutablePath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Get-Process -Name $AppId -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

$StartMenu = [Environment]::GetFolderPath("Programs")
Remove-Item -LiteralPath (Join-Path $StartMenu "$AppName.lnk") -Force -ErrorAction SilentlyContinue

# Remove the launcher folder from the user PATH.
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath) {
    $PathParts = @($UserPath -split ";" | Where-Object { $_ })
    $NormalizedShim = $ShimDir.TrimEnd("\")
    $Filtered = @($PathParts | Where-Object { $_.TrimEnd("\") -ine $NormalizedShim })
    if ($Filtered.Count -ne $PathParts.Count) {
        [Environment]::SetEnvironmentVariable("Path", ($Filtered -join ";"), "User")
    }
}

Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue

if ($Purge) {
    Remove-Item -LiteralPath (Join-Path $env:APPDATA "mystic_pointer") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $LocalAppData "mystic_pointer") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $env:TEMP "mystic_pointer_clipboard") -Recurse -Force -ErrorAction SilentlyContinue
    Say "Removed configuration, API keys, and caches."
} else {
    Say "Configuration and API keys were kept."
    Say "Set MYSTIC_POINTER_PURGE=1 to remove them too."
}

Say "$AppName has been uninstalled."
