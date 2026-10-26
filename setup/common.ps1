$ErrorActionPreference = 'Stop'
$KitRoot = Split-Path -Parent $PSScriptRoot
function Refresh-KitPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
}
function Get-KitPython {
    $candidates = @()
    foreach ($name in @('python.exe','python3.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
    }
    $pythonBase = Join-Path $env:LOCALAPPDATA 'Programs/Python'
    if (Test-Path -LiteralPath $pythonBase) {
        $candidates += Get-ChildItem -LiteralPath $pythonBase -Directory | ForEach-Object { Join-Path $_.FullName 'python.exe' }
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (!(Test-Path -LiteralPath $candidate)) { continue }
        & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    throw 'Python 3.11+ not found. Run setup/setup.ps1, then reopen the terminal.'
}
function Invoke-KitChecked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Executable (exit $LASTEXITCODE)" }
}
Refresh-KitPath
