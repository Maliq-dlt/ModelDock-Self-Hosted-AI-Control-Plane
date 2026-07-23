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
  $lines = @("APP_ENV=development", "ADMIN_API_KEY=$(New-Base64Secret)", "API_KEY_HASH_SECRET=$(New-Base64Secret)", "CREDENTIAL_ENCRYPTION_KEY=$(New-Base64Secret -keepPadding $true)", "ADMIN_SESSION_SECRET=$(New-Base64Secret)", "BOOTSTRAP_ADMIN_EMAIL=admin@example.com", "BOOTSTRAP_ADMIN_PASSWORD=$bootstrapPassword", "REQUEST_RETENTION_DAYS=30")
  [IO.File]::WriteAllText($envPath, ($lines -join [Environment]::NewLine) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
  Write-Output "Created .env"
  Write-Output "BOOTSTRAP_ADMIN_EMAIL=admin@example.com"
  Write-Output "BOOTSTRAP_ADMIN_PASSWORD=$bootstrapPassword"
} else {
  $bytes = [IO.File]::ReadAllBytes($envPath)
  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    $content = [Text.Encoding]::UTF8.GetString($bytes, 3, $bytes.Length - 3)
    [IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
    Write-Output ".env BOM removed"
  }
  Write-Output ".env exists; leaving it unchanged"
}
Write-Output "Run: docker compose -p modeldock up --build"