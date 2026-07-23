$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root ".env"

function New-Base64Secret([int]$bytes = 32, [bool]$keepPadding = $false) {
  $buffer = New-Object byte[] $bytes
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
  $value = [Convert]::ToBase64String($buffer).Replace("+", "-").Replace("/", "_")
  if (-not $keepPadding) { $value = $value.TrimEnd("=") }
  return $value
}

if (-not (Test-Path $envPath)) {
  $bootstrapPassword = New-Base64Secret -bytes 24
  @("APP_ENV=development", "ADMIN_API_KEY=$(New-Base64Secret)", "API_KEY_HASH_SECRET=$(New-Base64Secret)", "CREDENTIAL_ENCRYPTION_KEY=$(New-Base64Secret -keepPadding $true)", "ADMIN_SESSION_SECRET=$(New-Base64Secret)", "BOOTSTRAP_ADMIN_EMAIL=admin@example.com", "BOOTSTRAP_ADMIN_PASSWORD=$bootstrapPassword", "REQUEST_RETENTION_DAYS=30") | Set-Content -LiteralPath $envPath -Encoding utf8
  Write-Output "Created .env"
  Write-Output "BOOTSTRAP_ADMIN_EMAIL=admin@example.com"
  Write-Output "BOOTSTRAP_ADMIN_PASSWORD=$bootstrapPassword"
} else {
  Write-Output ".env exists; leaving it unchanged"
}
Write-Output "Run: docker compose up --build"
