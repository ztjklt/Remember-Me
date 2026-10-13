param(
    [Parameter(Mandatory=$true)][string]$JdkDirectory,
    [Parameter(Mandatory=$true)][string]$SdkClassesJar,
    [Parameter(Mandatory=$true)][string]$AndroidJar,
    [Parameter(Mandatory=$true)][string]$KotlinStdlibJar,
    [Parameter(Mandatory=$true)][string]$AppClassesDirectory,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\app\build\hardware-sdk-example')
)
$ErrorActionPreference = 'Stop'
foreach ($path in @($SdkClassesJar, $AndroidJar, $KotlinStdlibJar, $AppClassesDirectory)) {
    if (-not (Test-Path -LiteralPath $path)) { throw 'A required local compiler input is missing.' }
}
$compiler = Join-Path $JdkDirectory 'bin\javac.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'JDK javac is required.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$classpath = @($SdkClassesJar, $AndroidJar, $KotlinStdlibJar, $AppClassesDirectory) -join [IO.Path]::PathSeparator
$sources = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'src') -Filter '*.java' | ForEach-Object FullName)
& $compiler -encoding UTF-8 -source 17 -target 17 -cp $classpath -d $OutputDirectory @sources
if ($LASTEXITCODE -ne 0) { throw 'SDK bridge compilation failed; no runtime initialization was attempted.' }
Write-Output 'Compiled the SDK 1.3.02 bridge example. Authentication, device I/O and decoding were not run.'
