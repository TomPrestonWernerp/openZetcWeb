[CmdletBinding()]
param(
    [string]$SourceEnv = ".env",
    [string]$OutputFile = ".openzetc/infrastructure-key.env"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-RepoPath([string]$PathValue) {
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $repoRoot $PathValue
}

function Get-DotEnvValue([string]$PathValue, [string]$Name) {
    if (-not (Test-Path -LiteralPath $PathValue)) {
        return ""
    }
    $escapedName = [regex]::Escape($Name)
    $line = Get-Content -LiteralPath $PathValue |
        Where-Object { $_ -match "^\s*$escapedName\s*=" } |
        Select-Object -Last 1
    if ($null -eq $line) {
        return ""
    }
    $value = ($line -replace "^\s*$escapedName\s*=", "").Trim()
    if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        return $value.Substring(1, $value.Length - 2)
    }
    return $value
}

$sourcePath = Resolve-RepoPath $SourceEnv
$outputPath = Resolve-RepoPath $OutputFile
$key = Get-DotEnvValue $sourcePath "INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY"
if ([string]::IsNullOrWhiteSpace($key)) {
    $key = Get-DotEnvValue $sourcePath "JWT_SECRET_KEY"
}
if ([string]::IsNullOrWhiteSpace($key)) {
    throw "INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY or JWT_SECRET_KEY was not found in $sourcePath."
}

$outputDirectory = Split-Path -Parent $outputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}
$content = "INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY=$key`n"
[System.IO.File]::WriteAllText($outputPath, $content, [System.Text.UTF8Encoding]::new($false))

Write-Host "Infrastructure key transfer file created: $outputPath" -ForegroundColor Green
Write-Host "Upload it with the source code and run scripts/deploy-prod.sh on the server." -ForegroundColor Yellow
