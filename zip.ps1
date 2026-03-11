$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$zip = Join-Path $root 'KajovoPhotoSelector.zip'
$exclude = @('.git', 'venv', '.venv', 'env', 'LOG', 'LOGS', 'OUT', 'OUTPUT', 'IN', '__pycache__', 'build', 'dist')
$excludeFiles = @('KajovoPhotoSelector.log', 'Kaja_session.json', 'KajovoPhotoSelector.zip')

$files = Get-ChildItem -LiteralPath $root -Recurse -Force | Where-Object {
    if ($_.PSIsContainer) { return $false }
    if ($excludeFiles -contains $_.Name) { return $false }
    $parts = ($_.FullName.Substring($root.Length)).TrimStart('\', '/') -split '[\\/]'
    return -not ($parts | Where-Object { $exclude -contains $_ })
}

if (Test-Path $zip) {
    Remove-Item $zip -Force
}

Compress-Archive -Path $files.FullName -DestinationPath $zip -Force -CompressionLevel Optimal
