# One-line installer for Mac-to-iPhone-HID on Windows (PowerShell):
#   irm https://raw.githubusercontent.com/usernameLoophole/Mac-to-iPhone-HID/main/install.ps1 | iex
# Re-running it is safe: it updates the clone and skips what's already done.
# Env overrides: INSTALL_DIR (default ~\Mac-to-iPhone-HID), REPO_URL, BRANCH, NONINTERACTIVE=1.

function Install-KbmBridge {  # everything in a function: a half-downloaded script runs nothing
  $ErrorActionPreference = "Stop"
  $repo = if ($env:REPO_URL) { $env:REPO_URL } else { "https://github.com/usernameLoophole/Mac-to-iPhone-HID.git" }
  $dir = if ($env:INSTALL_DIR) { $env:INSTALL_DIR } else { Join-Path $HOME "Mac-to-iPhone-HID" }

  function Say($m) { Write-Host "==> $m" -ForegroundColor Blue }
  function Ok($m) { Write-Host " ok $m" -ForegroundColor Green }
  function Ask($q) {
    if ($env:NONINTERACTIVE -eq "1") { return $false }
    return (Read-Host "$q [Y/n]") -notmatch '^[nN]'
  }
  function Refresh-Path {  # pick up programs winget just installed
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
  }
  function Run($exe) {  # run a native command, stop on failure
    & $exe @args
    if ($LASTEXITCODE -ne 0) { throw "failed: $exe $args" }
  }
  function Find-Python {  # first Python >= 3.11, as an array: exe + args
    $ErrorActionPreference = "Continue"  # PS 5.1 turns a native command's stderr into a fatal error under "Stop"
    foreach ($c in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("python"))) {
      if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
      $exe, $rest = $c
      & $exe @rest -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null
      if ($LASTEXITCODE -eq 0) { return , $c }
    }
    return $null
  }
  function Winget-Install($id, $what) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
      throw "$what is missing and winget isn't available. Install $what yourself, then run this again."
    }
    Say "Installing $what"
    Run winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
  }

  Say "Checking dependencies"
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Winget-Install "Git.Git" "Git" }
  Ok "git"
  $py = Find-Python
  if (-not $py) { Winget-Install "Python.Python.3.12" "Python 3.12"; $py = Find-Python }
  if (-not $py) { throw "Python 3.11+ not found. Open a new PowerShell window and run this again." }
  $pyExe, $pyArgs = $py
  Ok "python ($(& $pyExe @pyArgs --version))"

  if (Test-Path (Join-Path $dir ".git")) {
    Say "Updating $dir"
    Run git -C $dir pull --ff-only
  } else {
    Say "Cloning into $dir"
    if ($env:BRANCH) { Run git clone -b $env:BRANCH $repo $dir } else { Run git clone $repo $dir }
  }

  Say "Setting up the Python environment (bridge + PlatformIO)"
  $vpy = Join-Path $dir "host\.venv\Scripts\python.exe"
  if (-not (Test-Path $vpy)) { Run $pyExe @pyArgs -m venv (Join-Path $dir "host\.venv") }
  Run $vpy -m pip install -q --upgrade pip
  Run $vpy -m pip install -q -r (Join-Path $dir "host\requirements.txt") -r (Join-Path $dir "firmware\requirements.txt")
  Run $vpy (Join-Path $dir "host\bridge.py") --selftest

  $pio = Join-Path $dir "host\.venv\Scripts\pio.exe"
  $port = & $vpy -c "from serial.tools import list_ports as l; print(next((p.device for p in l.comports() if p.vid == 0x303A), ''))"
  if ($port -and (Ask "Flash the firmware to the ESP32 on $port now? (first build downloads ~500 MB of tools)")) {
    Run $pio run -d (Join-Path $dir "firmware") -t upload --upload-port $port
    Ok "firmware flashed"
  } else {
    if (-not $port) { Say "No ESP32-S3 found (plug it into the board's USB port)." }
    Say "Flash the firmware later with:"
    Write-Host "    & '$pio' run -d '$(Join-Path $dir "firmware")' -t upload"
  }

  Write-Host ""
  Ok "Installed in $dir"
  Write-Host @"

Next:
  1. iPhone: Settings > Bluetooth > tap "Xbox Wireless Controller" (first time only)
  2. Run:     $(Join-Path $dir "start.bat")
  3. Toggle:  Ctrl+Alt+Shift+K sends keyboard + mouse to the iPhone and back
"@
}

Install-KbmBridge
