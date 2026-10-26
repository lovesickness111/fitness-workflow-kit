param([Parameter(Mandatory=$true,Position=0)][string]$Helper,
      [Parameter(ValueFromRemainingArguments=$true)][string[]]$HelperArguments)
. "$PSScriptRoot/common.ps1"
$python = Join-Path $KitRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run setup/setup.ps1 first.' }
Invoke-KitChecked $python (@((Join-Path $KitRoot 'tools/run_video_use.py'),$Helper) + $HelperArguments)
