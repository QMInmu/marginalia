param([switch]$Check)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$OutputEncoding = [Console]::OutputEncoding
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = $null
$pythonPrefix = @()
$exitCode = 1

try {
    $candidates = @(
        (Join-Path $repoRoot '.venv\Scripts\python.exe'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            & $candidate -c 'import sys; sys.exit(sys.version_info < (3, 11))'
            if ($LASTEXITCODE -eq 0) { $pythonExe = $candidate; break }
        }
    }
    if (-not $pythonExe) {
        foreach ($name in @('py', 'python', 'python3')) {
            $command = Get-Command $name -ErrorAction SilentlyContinue
            if ($command -and $command.Source -notlike '*\WindowsApps\*') {
                $prefix = @()
                if ($name -eq 'py') { $prefix = @('-3') }
                & $command.Source @prefix -c 'import sys; sys.exit(sys.version_info < (3, 11))'
                if ($LASTEXITCODE -eq 0) {
                    $pythonExe = $command.Source
                    $pythonPrefix = $prefix
                    break
                }
            }
        }
    }
    if (-not $pythonExe) {
        throw 'Python 3.11+ is required. Install Python, then run this launcher again.'
    }
    & $pythonExe @pythonPrefix -c "import importlib.util,sys; sys.exit(importlib.util.find_spec('pypdf') is None)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Preparing a local Python environment...'
        $venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $venvPython)) {
            & $pythonExe @pythonPrefix -m venv (Join-Path $repoRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
        }
        & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Could not install pypdf. Check your connection and try again.' }
        $pythonExe = $venvPython
        $pythonPrefix = @()
    }
    Push-Location -LiteralPath $repoRoot
    try {
        if ($Check) {
            & $pythonExe @pythonPrefix (Join-Path $PSScriptRoot 'update_library.py') sync --check
        } else {
            & $pythonExe @pythonPrefix (Join-Path $PSScriptRoot 'update_library.py')
        }
        $exitCode = $LASTEXITCODE
    } finally { Pop-Location }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
}
exit $exitCode
