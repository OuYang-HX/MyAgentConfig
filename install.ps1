<#
.SYNOPSIS
  MyAgentConfig 通用安装器（Windows PowerShell）
.DESCRIPTION
  具体装哪些东西由 components/*/manifest.json 决定，本脚本只负责转发。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  powershell -ExecutionPolicy Bypass -File .\install.ps1 --list
  powershell -ExecutionPolicy Bypass -File .\install.ps1 --only gwf
#>
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $Repo "tools\install.py"

$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { $python = (Get-Command python3 -ErrorAction SilentlyContinue) }
if (-not $python) {
    Write-Host "需要 Python 3（安装器与 gwf 引擎都是纯 Python 实现）" -ForegroundColor Red
    Write-Host "安装时请勾选 'Add Python to PATH'" -ForegroundColor Red
    exit 1
}

& $python.Source $Installer @args
exit $LASTEXITCODE
