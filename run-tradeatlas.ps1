$ErrorActionPreference = 'Stop'
$pythonArguments = $args
if ($pythonArguments.Count -eq 0) {
    $pythonArguments = @('-m', 'marimo', 'edit', '--no-sandbox', 'groundnut_lab.py')
}

$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'TradeAtlas dependencies are missing. Run uv sync --locked from the project directory.'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    & $python -B @pythonArguments
    $pythonExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $pythonExitCode
