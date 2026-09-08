[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $ExpectedPublisher,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $ExpectedVersion,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string[]] $ArtifactPath,

    [Parameter(Mandatory = $false)]
    [string] $SignToolPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Verify already-signed release artifacts without loading any certificate or
# signing credential. The caller supplies the expected public publisher subject.
#
# Microsoft Authenticode and SmartScreen guidance:
# https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options
# https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation
# https://learn.microsoft.com/windows/win32/seccrypto/signtool

function Resolve-SignTool {
    param([string] $ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
            throw "signtool.exe not found at explicit path: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    if (-not (Test-Path -LiteralPath $kitsRoot -PathType Container)) {
        throw 'signtool.exe is unavailable and the Windows SDK bin directory was not found'
    }
    $toolArchitecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
    $candidate = Get-ChildItem -LiteralPath $kitsRoot -Filter signtool.exe -File -Recurse |
        Where-Object { $_.Directory.Name -eq $toolArchitecture } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if (-not $candidate) {
        throw 'signtool.exe was not found in the Windows SDK'
    }
    return $candidate.FullName
}

if ($ArtifactPath.Count -eq 0) {
    throw 'at least one Windows artifact is required'
}

$signTool = Resolve-SignTool -ExplicitPath $SignToolPath
$seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

foreach ($path in $ArtifactPath) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "artifact not found: $path"
    }
    $resolved = (Resolve-Path -LiteralPath $path).Path
    if (-not $seen.Add($resolved)) {
        throw "duplicate artifact path: $resolved"
    }

    & $signTool verify /pa /all /v $resolved
    if ($LASTEXITCODE -ne 0) {
        throw "signtool verification failed for $resolved (exit $LASTEXITCODE)"
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $resolved
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Authenticode status for $resolved is $($signature.Status): $($signature.StatusMessage)"
    }
    if (-not $signature.SignerCertificate) {
        throw "no signer certificate found for $resolved"
    }
    if ($signature.SignerCertificate.Subject -cne $ExpectedPublisher) {
        throw "unexpected publisher for $resolved: $($signature.SignerCertificate.Subject)"
    }
    if (-not $signature.TimeStamperCertificate) {
        throw "no trusted timestamp certificate found for $resolved"
    }
    $versionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($resolved)
    if ($versionInfo.ProductVersion -cne $ExpectedVersion) {
        throw "unexpected ProductVersion for $resolved: $($versionInfo.ProductVersion)"
    }
    if ($versionInfo.FileVersion -cne $ExpectedVersion) {
        throw "unexpected FileVersion for $resolved: $($versionInfo.FileVersion)"
    }

    $hash = Get-FileHash -LiteralPath $resolved -Algorithm SHA256
    Write-Output "Windows platform trust verified: $resolved"
    Write-Output "Publisher: $ExpectedPublisher"
    Write-Output "SHA256: $($hash.Hash)"
}
