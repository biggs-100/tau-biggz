# tau-biggz installer for Windows
# Run: irm https://raw.githubusercontent.com/biggs-100/tau-biggz/main/install.ps1 | iex

$Package = "tau-biggz"
$Version = "0.1.7"

Write-Host ""
Write-Host "  tau-biggz installer for Windows" -ForegroundColor Cyan
Write-Host ""

# Check Python (Windows uses 'python', not 'python3')
$python = $null
foreach ($cmd in @("python", "python3")) {
    $ver = & $cmd --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $ver -match "(\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -ge 3 -and $minor -ge 12) {
            $python = $cmd
            break
        }
    }
}

if (-not $python) {
    Write-Host "  Python 3.12+ required." -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "  Python found" -ForegroundColor Green

# Find the Scripts directory
$scriptsDir = & $python -c "import sys; from pathlib import Path; p = Path(sys.executable).parent / 'Scripts'; print(p)" 2>$null
if (-not (Test-Path $scriptsDir)) {
    # Fallback: user site-packages scripts
    $scriptsDir = & $python -c "import site; print(site.USER_BASE)" 2>$null
    if ($scriptsDir) { $scriptsDir = Join-Path $scriptsDir "Scripts" }
}
if (-not (Test-Path $scriptsDir)) {
    $scriptsDir = "$env:APPDATA\Python\Python312\Scripts"
}

# Clean
Write-Host "  Cleaning..." -ForegroundColor Yellow
& $python -m pip uninstall -y $Package 2>$null
& $python -m pip cache remove $Package 2>$null
Remove-Item "$scriptsDir\tau.exe" -Force -ErrorAction SilentlyContinue
Remove-Item "$scriptsDir\tau-script.py" -Force -ErrorAction SilentlyContinue

# Install
Write-Host "  Installing $Package $Version..." -ForegroundColor Yellow
& $python -m pip install --force-reinstall --no-cache-dir "$Package==$Version"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installation failed" -ForegroundColor Red
    exit 1
}

# Show where tau was installed
$tauExe = "$scriptsDir\tau.exe"
if (Test-Path $tauExe) {
    Write-Host "  Installed at: $tauExe" -ForegroundColor Green
} else {
    # Search
    $tauExe = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter "tau.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tauExe) {
        $scriptsDir = $tauExe.Directory.FullName
        $tauExe = $tauExe.FullName
        Write-Host "  Installed at: $tauExe" -ForegroundColor Green
    } else {
        Write-Host "  tau.exe not found! Try running as Administrator:" -ForegroundColor Yellow
        Write-Host "  pip install --force-reinstall tau-biggz" -ForegroundColor Yellow
    }
}

# Add to USER PATH
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$scriptsDir*") {
    Write-Host "  Adding to PATH..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$scriptsDir", "User")
    $env:Path = "$env:Path;$scriptsDir"
    Write-Host "  PATH updated!" -ForegroundColor Green
} else {
    Write-Host "  Already in PATH" -ForegroundColor Green
}

Write-Host ""
Write-Host "  tau-biggz $Version installed!" -ForegroundColor Green
Write-Host ""

if (Test-Path $tauExe) {
    Write-Host "  Run: $tauExe --version"
    Write-Host "  Or close and reopen PowerShell, then: tau --version"
} else {
    Write-Host "  Try: python -m tau_coding.cli --version"
}
