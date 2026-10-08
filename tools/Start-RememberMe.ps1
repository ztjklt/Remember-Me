param(
    [string]$PythonExe = "python",
    [string]$AdbExe = "adb",
    [string]$Serial = "",
    [switch]$CheckOnly,
    [switch]$InstallAndroid
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$launchArgs = @((Join-Path $PSScriptRoot "start_product.py"))
if ($CheckOnly) { $launchArgs += "--check" }
if ($InstallAndroid) {
    $launchArgs += @("--install-android", "--adb", $AdbExe)
    if ($Serial) { $launchArgs += @("--serial", $Serial) }
}
& $PythonExe @launchArgs
if ($LASTEXITCODE -ne 0) { throw "启动未完成。请按上面的具体原因处理，勿重复启动服务。" }
