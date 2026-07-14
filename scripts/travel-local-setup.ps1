param(
    [string]$TencentMapServerKey = $env:TENCENT_MAP_SERVER_KEY
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$rootEnv = Join-Path $root '.env'
$rootEnvExample = Join-Path $root '.env.example'
$placeEnv = Join-Path $root 'place-service\.env'

function New-RandomUrlSafeValue([int]$ByteCount = 32) {
    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Set-DotEnvValue([string]$Path, [string]$Name, [string]$Value) {
    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
            $lines.Add([string]$line)
        }
    }

    $replacement = "$Name=$Value"
    $found = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^\s*$([regex]::Escape($Name))\s*=") {
            $lines[$index] = $replacement
            $found = $true
            break
        }
    }
    if (-not $found) {
        if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -ne '') {
            $lines.Add('')
        }
        $lines.Add($replacement)
    }
    [System.IO.File]::WriteAllLines($Path, $lines, [System.Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path -LiteralPath $rootEnv)) {
    Copy-Item -LiteralPath $rootEnvExample -Destination $rootEnv
    Write-Host 'Created root .env from .env.example.'
}

if (-not (Test-Path -LiteralPath $placeEnv)) {
    $databasePassword = New-RandomUrlSafeValue
    $placeToken = New-RandomUrlSafeValue
    $content = @(
        'POSTGRES_DB=places'
        'POSTGRES_USER=places_app'
        "POSTGRES_PASSWORD=$databasePassword"
        "PLACE_API_TOKEN=$placeToken"
        ''
    )
    [System.IO.File]::WriteAllLines($placeEnv, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host 'Created place-service/.env with random local-only credentials.'
}

$placeTokenLine = Get-Content -LiteralPath $placeEnv -Encoding utf8 |
    Where-Object { $_ -match '^PLACE_API_TOKEN=' } |
    Select-Object -First 1
if (-not $placeTokenLine) {
    throw 'PLACE_API_TOKEN is missing from place-service/.env.'
}
$placeToken = $placeTokenLine.Substring($placeTokenLine.IndexOf('=') + 1).Trim()
if (-not $placeToken) {
    throw 'PLACE_API_TOKEN is empty in place-service/.env.'
}

Set-DotEnvValue -Path $rootEnv -Name 'PLACE_API_BASE_URL' -Value 'http://127.0.0.1:8091'
Set-DotEnvValue -Path $rootEnv -Name 'PLACE_API_TOKEN' -Value $placeToken
if ($TencentMapServerKey.Trim()) {
    Set-DotEnvValue -Path $rootEnv -Name 'TENCENT_MAP_SERVER_KEY' -Value $TencentMapServerKey.Trim()
}

$required = @('HUNYUAN_API_KEY', 'TENCENT_MAP_SERVER_KEY', 'VITE_TENCENT_MAP_KEY')
$missing = @()
$rootLines = Get-Content -LiteralPath $rootEnv -Encoding utf8
foreach ($name in $required) {
    $line = $rootLines | Where-Object { $_ -match "^\s*$([regex]::Escape($name))\s*=" } | Select-Object -First 1
    $value = if ($line) { $line.Substring($line.IndexOf('=') + 1).Trim() } else { '' }
    if (-not $value) {
        $missing += $name
    }
}

Write-Host 'Local place-service settings are synchronized to the root .env.'
if ($missing.Count -gt 0) {
    Write-Warning ('Fill these values in .env before full end-to-end testing: ' + ($missing -join ', '))
}
Write-Host 'Setup complete. Run: npm run dev:travel-local'
