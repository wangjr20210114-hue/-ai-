$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$placeDirectory = Join-Path $root 'place-service'
$placeEnv = Join-Path $placeDirectory '.env'
$composeFile = Join-Path $placeDirectory 'compose.yml'

$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if (-not $docker) {
    throw 'Docker Desktop is required.'
}
if (-not (Test-Path -LiteralPath $placeEnv)) {
    throw 'place-service/.env does not exist. Run: npm run setup:travel-local'
}

$values = @{}
Get-Content -LiteralPath $placeEnv -Encoding utf8 | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        $values[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$database = $values['POSTGRES_DB']
$user = $values['POSTGRES_USER']
if (-not $database -or -not $user) {
    throw 'POSTGRES_DB or POSTGRES_USER is missing from place-service/.env.'
}

$sql = @'
SELECT count(*) AS place_rows,
       pg_size_pretty(pg_database_size(current_database())) AS database_size,
       pg_size_pretty(pg_total_relation_size('places')) AS places_with_indexes
FROM places;
'@

& $docker.Source compose --env-file $placeEnv -f $composeFile exec -T db `
    psql -U $user -d $database -c $sql
exit $LASTEXITCODE
