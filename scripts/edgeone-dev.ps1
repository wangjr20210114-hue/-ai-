$ErrorActionPreference = 'Stop'

$command = Get-Command edgeone.cmd -ErrorAction SilentlyContinue
$cli = if ($command) {
    $command.Source
} else {
    Join-Path $env:APPDATA 'npm\edgeone.cmd'
}

if (-not (Test-Path -LiteralPath $cli)) {
    throw 'EdgeOne CLI is not installed. Install the pinned local version with: npm install -g edgeone@1.6.13'
}

& $cli makers dev @args
exit $LASTEXITCODE
