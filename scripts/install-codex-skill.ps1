[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $projectRoot 'skills\crear-tutorial-visual'
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$skillsRoot = Join-Path $codexRoot 'skills'
$target = Join-Path $skillsRoot 'crear-tutorial-visual'

if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md'))) {
    throw 'No se encontró la skill versionada en el repositorio.'
}

$resolvedSkillsRoot = [System.IO.Path]::GetFullPath($skillsRoot)
$resolvedTarget = [System.IO.Path]::GetFullPath($target)
if (-not $resolvedTarget.StartsWith(
    $resolvedSkillsRoot + [System.IO.Path]::DirectorySeparatorChar,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'La ruta de instalación calculada no es segura.'
}

New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
$staging = Join-Path $skillsRoot ".crear-tutorial-visual-$([guid]::NewGuid().ToString('N'))"
try {
    Copy-Item -LiteralPath $source -Destination $staging -Recurse
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
    Move-Item -LiteralPath $staging -Destination $target
} finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

Write-Host "Skill instalada en: $target"
