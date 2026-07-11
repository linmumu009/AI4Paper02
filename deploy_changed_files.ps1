# Upload the validated changed-file list, build the selected client, and restart services.

[CmdletBinding()]
param(
  [ValidateSet("View", "Mobile", "Both", "Backend")]
  [string]$Target = "View",
  [switch]$InstallNpm,
  [switch]$SkipUpload,
  [switch]$DryRun,
  [string]$Remote = "root@8.137.23.146",
  [int]$Port = 22,
  [string]$IdentityFile = (Join-Path $env:USERPROFILE ".ssh\ai4papers_sync_ed25519")
)

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$uploadScript = Join-Path $ScriptDirectory "upload_changed_files.ps1"
$IdentityFile = [System.IO.Path]::GetFullPath($IdentityFile)

if (-not (Test-Path -LiteralPath $uploadScript -PathType Leaf)) {
  throw "Upload script not found: $uploadScript"
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
  throw "SSH private key not found: $IdentityFile"
}

if (-not $SkipUpload) {
  $uploadParams = @{
    Remote = $Remote
    Port = $Port
    IdentityFile = $IdentityFile
  }
  if ($DryRun) { $uploadParams.DryRun = $true }

  & $uploadScript @uploadParams
  if (-not $?) { throw "Changed-file upload failed." }
}

$targetValue = $Target.ToLowerInvariant()
$remoteCommand = "bash /projects/ArxivPaper4/deploy_server.sh --target $targetValue"
if ($InstallNpm) { $remoteCommand += " --install-npm" }

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
