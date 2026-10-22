param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$taskEnv = Join-Path (Split-Path $PSScriptRoot -Parent) '.resume-platform-local\.env'
if (!(Test-Path -LiteralPath $taskPython)) { throw '请先创建 .venv 并安装项目依赖，详见 docs/稳定版使用说明.md' }
Push-Location $PSScriptRoot
try { & $taskPython -m agent.launcher --env-file $taskEnv --port $Port }
finally { Pop-Location }
