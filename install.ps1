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

# Determine Python Scripts directory
$pyBase = Split-Path -Parent (& $python -c "import sys; print(sys.executable)")
$scriptsDir = Split-Path -Parent $pyBase
$scriptsDir = Join-Path $scriptsDir "Scripts"
if (-not (Test-Path $scriptsDir)) {
    $scriptsDir = Join-Path $env:APPDATA "Python\Python312\Scripts"
}

# Clean previous installations
Write-Host "  Cleaning previous installations..." -ForegroundColor Yellow
& $python -m pip uninstall -y $Package 2>$null
& $python -m pip cache remove $Package 2>$null

# Remove stale launcher from common locations
$tauPaths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts\tau.exe",
    "$env:APPDATA\Python\Python312\Scripts\tau.exe",
    "$env:USERPROFILE\.local\bin\tau.exe",
    "$scriptsDir\tau.exe"
)
foreach ($p in $tauPaths) { if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue } }

# Install
Write-Host "  Installing $Package $Version..." -ForegroundColor Yellow
& $python -m pip install --force-reinstall --no-cache-dir "$Package==$Version"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installation failed" -ForegroundColor Red
    exit 1
}

# Add Scripts directory to PATH if not already there
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$scriptsDir*") {
    Write-Host "  Adding $scriptsDir to PATH..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$scriptsDir", "User")
    # Update current session
    $env:Path = "$env:Path;$scriptsDir"
    Write-Host "  PATH updated (log out/in or restart terminal to make permanent)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  tau-biggz $Version installed!" -ForegroundColor Green
Write-Host ""
Write-Host "  Run: tau --version"
Write-Host "  Or: python -m tau_coding.cli --version"
