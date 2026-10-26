param([switch]$SkipPrerequisites,[switch]$NoDoctor)
. "$PSScriptRoot/common.ps1"

function Install-KitPrerequisite {
    param([string]$Command,[string]$Package)
    if (Get-Command $Command -ErrorAction SilentlyContinue) { return }
    if ($SkipPrerequisites -or !(Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Missing $Command. Install $Package and rerun setup."
    }
    Invoke-KitChecked 'winget.exe' @('install','--id',$Package,'--exact','--silent','--accept-source-agreements','--accept-package-agreements')
    Refresh-KitPath
}
try { $python = Get-KitPython } catch {
    if ($SkipPrerequisites -or !(Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw }
    Invoke-KitChecked 'winget.exe' @('install','--id','Python.Python.3.12','--exact','--silent','--accept-source-agreements','--accept-package-agreements')
    Refresh-KitPath
    $python = Get-KitPython
}
Install-KitPrerequisite 'node.exe' 'OpenJS.NodeJS.LTS'
Install-KitPrerequisite 'git.exe' 'Git.Git'
Install-KitPrerequisite 'ffmpeg.exe' 'Gyan.FFmpeg.Shared'
$python = Get-KitPython
# Optional: Codex CLI draws fitness images with the user's ChatGPT plan; Gemini is the backup, so a failure only warns.
if (!(Get-Command codex -ErrorAction SilentlyContinue) -and !$SkipPrerequisites -and (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
    & winget.exe install --id OpenAI.Codex --exact --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Codex CLI was not installed; fitness images will use the Gemini backup.' }
    Refresh-KitPath
}
# Windows PowerShell 5.1 strips inner double quotes from native arguments; keep this expression quote-free.
$nodeMajor = [int](((& node.exe -p 'process.versions.node') -split '\.')[0])
if ($nodeMajor -lt 22) { throw 'Node.js 22+ required. Update Node.js LTS, reopen the terminal and rerun.' }
$venvPython = Join-Path $KitRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $venvPython)) {
    Invoke-KitChecked $python @('-m','venv',(Join-Path $KitRoot '.venv'))
}
Invoke-KitChecked $venvPython @('-m','pip','install','--requirement',(Join-Path $KitRoot 'config/python-requirements.txt'))
Push-Location (Join-Path $KitRoot 'tools/publisher')
try {
    Invoke-KitChecked 'npm.cmd' @('ci','--ignore-scripts')
    Invoke-KitChecked 'npm.cmd' @('run','build')
} finally { Pop-Location }
# Fitness render runtime (Playwright Chromium, image libraries) runs here so it sees the refreshed PATH of fresh installs.
Invoke-KitChecked $venvPython @((Join-Path $KitRoot 'tools/fitness_video.py'),'setup')
New-Item -ItemType Directory -Path (Join-Path $KitRoot 'local') -Force | Out-Null
$accounts = Join-Path $KitRoot 'local/accounts.json'
if (!(Test-Path -LiteralPath $accounts)) { Copy-Item -LiteralPath (Join-Path $KitRoot 'config/accounts.example.json') -Destination $accounts }
Write-Host 'Installed locally. No transcription or posting was performed.'
if (!$NoDoctor) { & "$PSScriptRoot/doctor.ps1" }
