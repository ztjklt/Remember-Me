param([switch]$Demo, [string]$DemoAccountFile)
$ErrorActionPreference = 'Stop'
$webRoot = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $webRoot '../..')).Path
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$webNode = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' }
$oldValues = @{}
try {
    if ($Demo) {
        # Use the existing dedicated Chen account, only in the local process.
        # The file is outside Git and is never copied into dist or release.
        if (-not $DemoAccountFile) { $DemoAccountFile = Join-Path $repoRoot '../chen-demo-20261017/demo-account.private.json' }
        $account = Get-Content -LiteralPath $DemoAccountFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $account.username -or -not $account.password -or -not $account.subject_id) { throw 'Dedicated demo account file is incomplete.' }
        $values = @{
            WEB_DEMO_OWNER_USER = $account.username
            WEB_DEMO_OWNER_PASSWORD = $account.password
            WEB_DEMO_SUBJECT_ID = $account.subject_id
            WEB_PRIVATE_DEMO = '1'
            WEB_DEMO_READER_USER = ''
            WEB_DEMO_READER_PASSWORD = ''
        }
        foreach ($key in $values.Keys) {
            $oldValues[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, $values[$key], 'Process')
        }
    }
    Push-Location $webRoot
    & $webNode build.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Web build failed.' }
    & $webNode --env-file-if-exists=.env server.mjs
} finally {
    Pop-Location
    foreach ($key in $oldValues.Keys) { [Environment]::SetEnvironmentVariable($key, $oldValues[$key], 'Process') }
}
