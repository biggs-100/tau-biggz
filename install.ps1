# tau-biggz installer for Windows
# Run: powershell -c "irm https://tau-biggz.dev/install.ps1 | iex"

$Package = "tau-biggz"
$Version = "0.1.7"

Write-Host ""
Write-Host "  tau-biggz installer for Windows" -ForegroundColor Cyan
Write-Host ""

# Check Python
$python = $null
foreach ($cmd in @("python3", "python")) {
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
    Write-Host "  Python 3.12+ required. Download from: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "  Python found" -ForegroundColor Green

# Clean previous installations
Write-Host "  Cleaning previous installations..." -ForegroundColor Yellow
& $python -m pip uninstall -y $Package 2>$null
& $python -m pip cache remove $Package 2>$null

# Install
Write-Host "  Installing $Package $Version..." -ForegroundColor Yellow
& $python -m pip install --force-reinstall --no-cache-dir "$Package==$Version" 2>&1 | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "  tau-biggz $Version installed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Run: tau"
} else {
    Write-Host "  Installation failed" -ForegroundColor Red
    exit 1
}
