param([Parameter(Mandatory=$true)][ValidateSet('video-use','publisher','workflow','motion-broll')][string]$Component,
      [string]$Version,[string]$Source,[switch]$Rollback)
. "$PSScriptRoot/common.ps1"
$python = Get-KitPython
$arguments = @((Join-Path $KitRoot 'tools/manage.py'),'update','--component',$Component)
if ($Rollback) { $arguments += '--rollback' }
if ($Version) { $arguments += @('--version',$Version) }
if ($Source) { $arguments += @('--source',$Source) }
Invoke-KitChecked $python $arguments
