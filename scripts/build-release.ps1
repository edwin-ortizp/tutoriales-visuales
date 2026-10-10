[CmdletBinding()]
param(
    [switch]$BootstrapTools
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectPrefix = $projectRoot.TrimEnd('\') + '\'
$venvPath = Join-Path $projectRoot '.release-venv'
$buildPath = Join-Path $projectRoot 'build'
$distPath = Join-Path $projectRoot 'dist'
$releasePath = Join-Path $projectRoot 'release'

function Assert-ProjectChild {
    param([Parameter(Mandatory)][string]$Path)
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($projectPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta fuera del proyecto rechazada: $resolved"
    }
    return $resolved
}

function Reset-ProjectDirectory {
    param([Parameter(Mandatory)][string]$Path)
    $resolved = Assert-ProjectChild $Path
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    New-Item -ItemType Directory -Path $resolved | Out-Null
}

function Find-InnoCompiler {
    $command = Get-Command iscc -ErrorAction SilentlyContinue
    $candidates = @()
    if ($command) { $candidates += $command.Source }
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe')
    }
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    }
    return $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}

if (-not $IsWindows -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'La publicación debe ejecutarse en Windows de 64 bits.'
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw 'No se encontró Python en PATH.'
}
$pythonBits = & $pythonCommand.Source -c "import struct; print(struct.calcsize('P') * 8)"
if ($LASTEXITCODE -ne 0 -or $pythonBits -ne '64') {
    throw 'Se requiere una instalación de Python de 64 bits.'
}

$innoCompiler = Find-InnoCompiler
if (-not $innoCompiler -and $BootstrapTools) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'Inno Setup no está instalado y winget no está disponible.'
    }
    Write-Host 'Instalando Inno Setup 6 mediante winget...'
    $install = Start-Process -FilePath $winget.Source -ArgumentList @(
        'install', '--id', 'JRSoftware.InnoSetup', '--exact', '--silent',
        '--accept-package-agreements', '--accept-source-agreements'
    ) -Wait -PassThru -WindowStyle Hidden
    if ($install.ExitCode -ne 0) {
        throw "winget no pudo instalar Inno Setup (código $($install.ExitCode))."
    }
    $innoCompiler = Find-InnoCompiler
}
if (-not $innoCompiler) {
    throw 'No se encontró ISCC.exe. Ejecuta de nuevo con -BootstrapTools.'
}

Push-Location $projectRoot
try {
    $version = (& $pythonCommand.Source -c "from tutorial_app import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo leer tutorial_app.__version__.'
    }
    & $pythonCommand.Source scripts\check_release_version.py
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo verificar que la versión sea nueva y el repositorio público.' }
    Write-Host "Construyendo Tutoriales Visuales $version"

    Reset-ProjectDirectory $venvPath
    Reset-ProjectDirectory $buildPath
    Reset-ProjectDirectory $distPath
    New-Item -ItemType Directory -Force -Path $releasePath | Out-Null

    $venvPython = Join-Path $venvPath 'Scripts\python.exe'
    & $pythonCommand.Source -m venv $venvPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw 'No fue posible crear el entorno virtual de publicación.'
    }

    & $venvPython -m pip install --disable-pip-version-check -r requirements-release.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias de publicación.' }

    & $venvPython scripts\generate_release_assets.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la generación de icono y metadatos.' }

    & $venvPython -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Las pruebas automatizadas fallaron.' }

    & $venvPython -m PyInstaller --noconfirm --clean `
        --distpath $distPath `
        --workpath (Join-Path $buildPath 'pyinstaller') `
        packaging\TutorialesVisuales.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller no pudo construir la aplicación.' }

    $bundlePath = Join-Path $distPath 'TutorialesVisuales'
    $portableExe = Join-Path $bundlePath 'TutorialesVisuales.exe'
    if (-not (Test-Path -LiteralPath $portableExe)) {
        throw 'El ejecutable esperado no fue generado.'
    }
    $smoke = Start-Process -FilePath $portableExe -ArgumentList '--smoke-test' `
        -PassThru -WindowStyle Hidden
    if (-not $smoke.WaitForExit(60000)) {
        Stop-Process -Id $smoke.Id
        throw 'El smoke test no terminó en 60 segundos; revisa el ejecutable empaquetado.'
    }
    if ($smoke.ExitCode -ne 0) {
        throw "El ejecutable empaquetado falló el smoke test (código $($smoke.ExitCode))."
    }

    $portableZip = Join-Path $releasePath "tutoriales-visuales-portable-$version.zip"
    $installer = Join-Path $releasePath "tutoriales-visuales-setup-$version.exe"
    $checksumFile = Join-Path $releasePath "tutoriales-visuales-$version.sha256"
    $manifestFile = Join-Path $releasePath 'release-manifest.json'
    foreach ($artifact in @($portableZip, $installer, $checksumFile, $manifestFile)) {
        $safeArtifact = Assert-ProjectChild $artifact
        if (Test-Path -LiteralPath $safeArtifact) {
            Remove-Item -LiteralPath $safeArtifact -Force
        }
    }

    Compress-Archive -Path (Join-Path $bundlePath '*') -DestinationPath $portableZip -CompressionLevel Optimal

    Push-Location (Join-Path $projectRoot 'packaging')
    try {
        & $innoCompiler "/DAppVersion=$version" installer.iss
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup no pudo compilar el instalador.' }
    }
    finally {
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath $installer)) {
        throw 'Inno Setup terminó sin producir el instalador esperado.'
    }

    $artifactFiles = @($installer, $portableZip)
    $artifactInfo = foreach ($artifact in $artifactFiles) {
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
        [ordered]@{
            name = [System.IO.Path]::GetFileName($artifact)
            bytes = (Get-Item -LiteralPath $artifact).Length
            sha256 = $hash.Hash.ToLowerInvariant()
        }
    }
    $checksumLines = $artifactInfo | ForEach-Object { "$($_.sha256)  $($_.name)" }
    Set-Content -LiteralPath $checksumFile -Value $checksumLines -Encoding utf8

    $pyInstallerVersion = (& $venvPython -m PyInstaller --version).Trim()
    $manifest = [ordered]@{
        product = 'Tutoriales Visuales'
        version = $version
        architecture = 'x64'
        installation_scope = 'current-user'
        signed = $false
        built_at_utc = [DateTime]::UtcNow.ToString('o')
        python = (& $venvPython --version 2>&1).ToString().Trim()
        pyinstaller = $pyInstallerVersion
        artifacts = $artifactInfo
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestFile -Encoding utf8

    Write-Host ''
    Write-Host 'Construcción local terminada (sin publicar en GitHub):'
    Write-Host "  Instalador: $installer"
    Write-Host "  Portable:   $portableZip"
    Write-Host "  SHA-256:    $checksumFile"
    Write-Host "  Manifiesto: $manifestFile"
}
finally {
    Pop-Location
}
