$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$mappedDrive = $null
$composeRoot = $root

if ($root -match '[^\x00-\x7F]') {
  $driveLetter = @("X", "W", "V", "U", "T", "S", "R") | Where-Object { -not (Get-PSDrive -Name $_ -ErrorAction SilentlyContinue) } | Select-Object -First 1
  if (-not $driveLetter) {
    throw "Docker BuildKit requires an ASCII-only workspace path and no temporary drive is available. Move this repository to an ASCII path, then run .\scripts\start.ps1 again. Current path: $root"
  }
  $mappedDrive = "${driveLetter}:"
  & subst $mappedDrive $root
  if ($LASTEXITCODE -ne 0) { throw "Could not create temporary ASCII drive $mappedDrive for Docker BuildKit." }
  $composeRoot = "$mappedDrive\"
  Write-Output "Using temporary ASCII Docker path: $composeRoot"
}

Push-Location $composeRoot
$exitCode = 0
try {
  & (Join-Path $PSScriptRoot "bootstrap.ps1")
  docker compose -p modeldock up --build
  $exitCode = $LASTEXITCODE
} finally {
  Pop-Location
  if ($mappedDrive) { & subst $mappedDrive /d | Out-Null }
}
exit $exitCode