# Prueba local aislada: no registra asociaciones, accesos directos ni desinstaladores.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $root '.release-venv\Scripts\python.exe'
$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
$testRoot = Join-Path $root ('work\update-integration-' + [guid]::NewGuid().ToString('N'))
$stage = Join-Path $testRoot 'stage'
$installed = Join-Path $testRoot 'installed'
$previousLocalAppData = $env:LOCALAPPDATA
if (Get-Process TutorialesVisuales -ErrorAction SilentlyContinue) {
    throw 'Cierra Tutoriales Visuales antes de ejecutar esta prueba aislada.'
}
New-Item -ItemType Directory -Force $stage | Out-Null
try {
    $env:LOCALAPPDATA = Join-Path $testRoot 'appdata'
    foreach ($directory in @('tutorial_app', 'assets', 'packaging')) {
        Copy-Item -LiteralPath (Join-Path $root $directory) -Destination $stage -Recurse
    }
    Copy-Item -LiteralPath (Join-Path $root 'run.py') -Destination $stage
    New-Item -ItemType Directory (Join-Path $stage 'scripts') | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'scripts\generate_release_assets.py') -Destination (Join-Path $stage 'scripts')
    $first = (& $python -c 'from tutorial_app import __version__; print(__version__)').Trim()
    $parts = $first.Split('.')
    $next = if ($parts.Count -eq 3) { $first + '.2' } else { ($parts[0..2] -join '.') + '.' + ([int]$parts[3] + 1) }
    $init = Join-Path $stage 'tutorial_app\__init__.py'
    (Get-Content -LiteralPath $init -Raw).Replace($first, $next) | Set-Content -LiteralPath $init -Encoding utf8
    & $python (Join-Path $stage 'scripts\generate_release_assets.py')
    if ($LASTEXITCODE -ne 0) { throw 'Falló la generación del paquete de prueba.' }
    Push-Location $stage
    try {
        & $python -m PyInstaller --noconfirm --distpath (Join-Path $stage 'dist') --workpath (Join-Path $stage 'build') (Join-Path $stage 'packaging\TutorialesVisuales.spec')
    } finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0) { throw 'Falló la construcción del paquete de prueba.' }
    # Misma carga de aplicación e Inno Setup; se omiten integraciones del sistema
    # exclusivamente en estos instaladores de prueba y no se publican.
    foreach ($variant in @(@{ version=$first; bundle=(Join-Path $root 'dist\TutorialesVisuales') }, @{ version=$next; bundle=(Join-Path $stage 'dist\TutorialesVisuales') })) {
        $iss = @"
[Setup]
AppId=TutorialesVisuales.IntegrationTest
AppName=Tutoriales Visuales Integration Test
AppVersion=$($variant.version)
DefaultDirName=$installed
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=no
UsePreviousAppDir=no
CloseApplications=no
RestartApplications=no
OutputDir=$testRoot
OutputBaseFilename=tutoriales-visuales-setup-$($variant.version)
Compression=lzma2/fast
[Files]
Source: "$($variant.bundle)\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "$root\packaging\installation.json"; DestDir: "{app}"; Flags: ignoreversion
"@
        $issPath = Join-Path $testRoot ('setup-' + $variant.version + '.iss')
        Set-Content -LiteralPath $issPath -Value $iss -Encoding utf8
        & $iscc /Q $issPath
        if ($LASTEXITCODE -ne 0) { throw 'Falló Inno Setup en la prueba aislada.' }
    }
    $oldSetup = Join-Path $testRoot "tutoriales-visuales-setup-$first.exe"
    $setup = Start-Process -FilePath $oldSetup -ArgumentList '/VERYSILENT', '/NORESTART' -Wait -PassThru -WindowStyle Hidden
    if ($setup.ExitCode -ne 0) { throw 'Falló la instalación inicial.' }
    $exe = Join-Path $installed 'TutorialesVisuales.exe'
    $smoke = Start-Process -FilePath $exe -ArgumentList '--smoke-test' -Wait -PassThru -WindowStyle Hidden
    if ($smoke.ExitCode -ne 0) { throw 'El paquete inicial falló el smoke test.' }
    $project = Join-Path $testRoot 'conservar.tutorial'
    & $python -c 'import sys; from tutorial_app.models import TutorialProject; from tutorial_app.project_io import save_project; save_project(sys.argv[1], TutorialProject(title="Prueba de actualización"))' $project
    if ($LASTEXITCODE -ne 0) { throw 'No se creó el proyecto de prueba.' }
    $projectHash = (Get-FileHash -LiteralPath $project).Hash
    $newSetup = Join-Path $testRoot "tutoriales-visuales-setup-$next.exe"
    $parent = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-Command', 'Start-Sleep -Seconds 3' -PassThru -WindowStyle Hidden
    $jobPath = Join-Path $testRoot 'job.json'
    $resultPath = Join-Path $testRoot 'result.json'
    @{ pid=$parent.Id; installer=$newSetup; sha256=(Get-FileHash -LiteralPath $newSetup).Hash.ToLowerInvariant(); exe=$exe; directory=$installed; project=$project; result=$resultPath; log=(Join-Path $testRoot 'install.log') } | ConvertTo-Json | Set-Content -LiteralPath $jobPath -Encoding utf8
    $helperPath = Join-Path $root 'packaging\update-helper.ps1'
    $helper = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $helperPath + '"'), '-JobPath', ('"' + $jobPath + '"'), '-NoErrorDialog' -PassThru -WindowStyle Hidden
    if (-not $helper.WaitForExit(120000)) { throw 'El ayudante excedió el tiempo permitido.' }
    if ($helper.ExitCode -ne 0) { throw 'Falló el ayudante de actualización.' }
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if (-not $result.success) { throw $result.message }
    if ([Diagnostics.FileVersionInfo]::GetVersionInfo($exe).ProductVersion -ne $next) { throw 'La versión instalada no cambió.' }
    if ((Get-FileHash -LiteralPath $project).Hash -ne $projectHash) { throw 'El proyecto cambió durante la actualización.' }
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    $reopened = $null
    do {
        Start-Sleep -Milliseconds 250
        $reopened = Get-Process TutorialesVisuales -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe -and $_.MainWindowTitle -like "*v.$next*conservar.tutorial*" } | Select-Object -First 1
    } until ($reopened -or [DateTime]::UtcNow -gt $deadline)
    if (-not $reopened) { throw 'No se comprobó la reapertura del proyecto en la versión nueva.' }
    Write-Host "OK: $first -> $next; instalación, reinicio y proyecto conservado. Evidencia: $testRoot"
} finally {
    Get-Process TutorialesVisuales -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $installed 'TutorialesVisuales.exe') } | Stop-Process
    $env:LOCALAPPDATA = $previousLocalAppData
}
