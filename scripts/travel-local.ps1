param(
    [switch]$KeepPlaceService
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$placeDirectory = Join-Path $root 'place-service'
$placeEnv = Join-Path $placeDirectory '.env'
$composeFile = Join-Path $placeDirectory 'compose.yml'
$setupScript = Join-Path $PSScriptRoot 'travel-local-setup.ps1'
$edgeOneScript = Join-Path $PSScriptRoot 'edgeone-dev.ps1'

if (-not (Test-Path -LiteralPath (Join-Path $root '.env')) -or -not (Test-Path -LiteralPath $placeEnv)) {
    & $setupScript
}

$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if (-not $docker) {
    throw 'Docker Desktop is required for the local PostGIS place service. Install it, start it, then run this command again.'
}

& $docker.Source info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker is installed but its engine is not running. Start Docker Desktop and retry.'
}

$composeArgs = @('compose', '--env-file', $placeEnv, '-f', $composeFile)
$placeStarted = $false
try {
    & $docker.Source @composeArgs up -d --build db api
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to start the local PostGIS place service.'
    }
    $placeStarted = $true

    $deadline = (Get-Date).AddSeconds(120)
    $health = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8091/healthz' -TimeoutSec 3
            if ($health.ok) { break }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $health -or -not $health.ok) {
        & $docker.Source @composeArgs logs --tail 80 api db
        throw 'The local place service did not become healthy within 120 seconds.'
    }

    Write-Host "Local place service is ready (places=$($health.places))."
    Write-Host 'Starting the EdgeOne Makers development runtime...'
    Write-Host 'Open the URL printed by the CLI (normally http://127.0.0.1:8088/).'
    & $edgeOneScript
    exit $LASTEXITCODE
} finally {
    if ($placeStarted -and -not $KeepPlaceService) {
        Write-Host 'Stopping local place API and PostGIS containers...'
        & $docker.Source @composeArgs stop api db | Out-Host
    }
}
