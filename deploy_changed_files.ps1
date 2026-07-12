# Upload the validated changed-file list, build the selected client, and restart services.

[CmdletBinding()]
param(
  [ValidateSet("View", "Mobile", "Both", "Backend")]
  [string]$Target = "View",
  [switch]$InstallNpm,
  [switch]$UseLocalDist,
  [switch]$SkipUpload,
  [switch]$DryRun,
  [string]$ListFile = "",
  [string]$Remote = "root@8.137.23.146",
  [int]$Port = 22,
  [string]$IdentityFile = (Join-Path $env:USERPROFILE ".ssh\ai4papers_sync_ed25519")
)

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$uploadScript = Join-Path $ScriptDirectory "upload_changed_files.ps1"
$changedFilesList = if ([string]::IsNullOrWhiteSpace($ListFile)) {
  Join-Path $ScriptDirectory "changed_files_abs_paths.txt"
} else {
  [System.IO.Path]::GetFullPath($ListFile)
}
$IdentityFile = [System.IO.Path]::GetFullPath($IdentityFile)

if (-not (Test-Path -LiteralPath $uploadScript -PathType Leaf)) {
  throw "Upload script not found: $uploadScript"
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
  throw "SSH private key not found: $IdentityFile"
}
if (-not (Test-Path -LiteralPath $changedFilesList -PathType Leaf)) {
  throw "Changed-file list not found: $changedFilesList"
}
if ($UseLocalDist -and $InstallNpm) {
  throw "UseLocalDist and InstallNpm cannot be used together. Build locally before using UseLocalDist."
}
if ($UseLocalDist -and $Target -eq "Backend") {
  throw "UseLocalDist is not valid for the Backend target."
}

# The uploader reads files from the live working tree. Refuse to deploy when a
# listed file differs from Git so unrelated or half-finished edits cannot be
# copied to production accidentally. Changes outside the manifest are ignored.
$repositoryRoot = [System.IO.Path]::GetFullPath($ScriptDirectory).TrimEnd([char]92, [char]47)
$repositoryPrefix = $repositoryRoot + [System.IO.Path]::DirectorySeparatorChar
$manifestPaths = @(
  Get-Content -LiteralPath $changedFilesList |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith("#") }
)
$relativeManifestPaths = @(
  foreach ($manifestPath in $manifestPaths) {
    $fullManifestPath = [System.IO.Path]::GetFullPath($manifestPath)
    if (-not $fullManifestPath.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Changed-file entry is outside the repository: $fullManifestPath"
    }
    $fullManifestPath.Substring($repositoryPrefix.Length).Replace([char]92, [char]47)
  }
)

$gitStatusArgs = @("status", "--porcelain=v1", "--untracked-files=all", "--") + $relativeManifestPaths
$dirtyManifestEntries = @(& git -C $repositoryRoot @gitStatusArgs)
if ($LASTEXITCODE -ne 0) {
  throw "Failed to inspect Git status for the changed-file manifest."
}
if ($dirtyManifestEntries.Count -gt 0) {
  Write-Host "Deployment blocked: the changed-file manifest contains uncommitted files:" -ForegroundColor Red
  $dirtyManifestEntries | ForEach-Object { Write-Host ("  " + $_) }
  throw "Commit or remove every listed change before deploying."
}

if (-not $SkipUpload) {
  $uploadParams = @{
    Remote = $Remote
    Port = $Port
    IdentityFile = $IdentityFile
    ListFile = $changedFilesList
  }
  if ($DryRun) { $uploadParams.DryRun = $true }

  & $uploadScript @uploadParams
  if (-not $?) { throw "Changed-file upload failed." }
}

function Send-DistArtifact([string]$ClientDirectory, [string]$RemoteName) {
  $clientRoot = Join-Path $ScriptDirectory $ClientDirectory
  $distIndex = Join-Path $clientRoot "dist\index.html"
  if (-not (Test-Path -LiteralPath $distIndex -PathType Leaf)) {
    throw "Prebuilt artifact not found: $distIndex. Run the local production build first."
  }

  if ($DryRun) {
    Write-Host "DRY RUN: would package $ClientDirectory\dist and upload it as $RemoteName."
    return
  }

  $tempRoot = [System.IO.Path]::GetFullPath($env:TEMP)
  $tempDir = Join-Path $tempRoot ("ai4papers_dist_" + [Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tempDir | Out-Null
  $archive = Join-Path $tempDir $RemoteName
  $batchFile = Join-Path $tempDir "artifact.sftp"

  try {
    & tar.exe -czf $archive -C $clientRoot dist
    if ($LASTEXITCODE -ne 0) { throw "Failed to package $ClientDirectory\dist." }

    $archiveForSftp = $archive.Replace([char]92, [char]47)
    $batchLines = @(
      "-mkdir /projects/ArxivPaper4/.deploy",
      ('put "{0}" /projects/ArxivPaper4/.deploy/{1}' -f $archiveForSftp, $RemoteName),
      "quit"
    )
    Set-Content -LiteralPath $batchFile -Value $batchLines -Encoding ASCII

    $artifactSftpArgs = @(
      "-o", "BatchMode=yes",
      "-o", "IdentitiesOnly=yes",
      "-o", "PreferredAuthentications=publickey",
      "-o", "PasswordAuthentication=no",
      "-o", "KbdInteractiveAuthentication=no",
      "-o", "GSSAPIAuthentication=no",
      "-o", "StrictHostKeyChecking=yes",
      "-o", "ConnectTimeout=15",
      "-i", $IdentityFile,
      "-P", $Port,
      "-b", $batchFile,
      $Remote
    )
    & sftp @artifactSftpArgs
    if ($LASTEXITCODE -ne 0) { throw "Failed to upload the prebuilt $ClientDirectory artifact." }
  }
  finally {
    $resolved = [System.IO.Path]::GetFullPath($tempDir)
    if ($resolved.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolved)) {
      Remove-Item -LiteralPath $resolved -Recurse -Force
    }
  }
}

if ($UseLocalDist) {
  if ($Target -eq "View" -or $Target -eq "Both") {
    Send-DistArtifact "View" "view-dist.tar.gz"
  }
  if ($Target -eq "Mobile" -or $Target -eq "Both") {
    Send-DistArtifact "mobile_new" "mobile-dist.tar.gz"
  }
}

$targetValue = $Target.ToLowerInvariant()
$remoteCommand = "bash /projects/ArxivPaper4/deploy_server.sh --target $targetValue"
if ($InstallNpm) { $remoteCommand += " --install-npm" }
if ($UseLocalDist) { $remoteCommand += " --prebuilt" }

$sshArgs = @(
  "-o", "BatchMode=yes",
  "-o", "IdentitiesOnly=yes",
  "-o", "PreferredAuthentications=publickey",
  "-o", "PasswordAuthentication=no",
  "-o", "KbdInteractiveAuthentication=no",
  "-o", "GSSAPIAuthentication=no",
  "-o", "StrictHostKeyChecking=yes",
  "-o", "ConnectTimeout=15",
  "-i", $IdentityFile,
  "-p", $Port,
  $Remote,
  $remoteCommand
)

Write-Host ("RUN: ssh " + ($sshArgs -join " "))
if ($DryRun) {
  Write-Host "DRY RUN: deployment command was not executed."
  exit 0
}

& ssh @sshArgs
if ($LASTEXITCODE -ne 0) { throw "Remote deployment failed." }

Write-Host "Deployment completed successfully."
