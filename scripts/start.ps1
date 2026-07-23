$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "bootstrap.ps1")
docker compose up --build
