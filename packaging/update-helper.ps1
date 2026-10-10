param([Parameter(Mandatory)][string]$JobPath, [switch]$NoErrorDialog)
$ErrorActionPreference = 'Stop'
$job = Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    $parent = Get-Process -Id $job.pid -ErrorAction SilentlyContinue
    if ($parent -and -not $parent.WaitForExit(120000)) { throw 'La aplicación no terminó a tiempo.' }
    $stream = [IO.File]::OpenRead($job.installer)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
    if ($digest -ne $job.sha256) {
        throw 'El instalador no supera la verificación SHA-256.'
    }
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCLOSEAPPLICATIONS',
        '/NORESTARTAPPLICATIONS', ('/DIR="' + $job.directory + '"'), ('/LOG="' + $job.log + '"'))
    $setup = Start-Process -FilePath $job.installer -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
    if ($setup.ExitCode -ne 0) { throw "La instalación terminó con código $($setup.ExitCode). Registro: $($job.log)" }
    @{ success = $true; message = 'Actualización instalada correctamente.' } | ConvertTo-Json | Set-Content -LiteralPath $job.result -Encoding UTF8
    if ($job.project) {
        Start-Process -FilePath $job.exe -ArgumentList ('"' + $job.project + '"')
    } else {
        Start-Process -FilePath $job.exe
    }
} catch {
    @{ success = $false; message = $_.Exception.Message } | ConvertTo-Json | Set-Content -LiteralPath $job.result -Encoding UTF8
    if (-not $NoErrorDialog) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'No se pudo actualizar Tutoriales Visuales') | Out-Null
    }
    exit 1
}
