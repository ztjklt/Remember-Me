param(
    [string]$Adb = 'D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe',
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runDir = Join-Path $repoRoot 'services/backend/var/android-ecs-demo'
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$forward = '127.0.0.1:18843:127.0.0.1:18443'
$listener = Get-NetTCPConnection -State Listen -LocalPort 18843 -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
    if ($owner.Name -ne 'ssh.exe' -or !$owner.CommandLine.Contains($forward) -or !$owner.CommandLine.Contains('remember-me-ecs')) {
        throw '18843 is used by another process; no process was stopped or reused.'
    }
} else {
    $ssh = (Get-Command ssh).Source
    $tunnel = Start-Process -FilePath $ssh -WindowStyle Hidden -PassThru -ArgumentList '-N','-L',$forward,'-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=30','remember-me-ecs' -RedirectStandardError (Join-Path $runDir 'ssh.log')
    $tunnel.Id | Set-Content (Join-Path $runDir 'tunnel.pid')
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if ($tunnel.HasExited) { throw 'SSH stopped; inspect services/backend/var/android-ecs-demo/ssh.log.' }
        if (Get-NetTCPConnection -State Listen -LocalPort 18843 -ErrorAction SilentlyContinue) { break }
        Start-Sleep -Milliseconds 500
    }
    if (!(Get-NetTCPConnection -State Listen -LocalPort 18843 -ErrorAction SilentlyContinue)) { throw 'SSH tunnel not ready.' }
}
& $Adb reverse tcp:18843 tcp:18843
if ($LASTEXITCODE -ne 0) { throw 'Connect one Android device or emulator with USB debugging enabled.' }
if ($Install) {
    & $Adb install -r (Join-Path $repoRoot 'apps/android/app/build/outputs/apk/debug/app-debug.apk')
    if ($LASTEXITCODE -ne 0) { throw 'APK installation failed.' }
}
Write-Output 'Demo connection prepared: Android https://localhost:18843 -> USB/ADB -> verified SSH -> ECS. Keep the PC connected. This is not public IP direct access.'
