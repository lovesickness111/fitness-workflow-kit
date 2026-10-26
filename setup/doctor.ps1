. "$PSScriptRoot/common.ps1"
$python = Get-KitPython
Invoke-KitChecked $python @((Join-Path $KitRoot 'tools/manage.py'),'doctor')
