# upload_changed_files.ps1
# 读取 changed_files_abs_paths.txt（本地绝对路径清单）
# 只建立一次 SFTP 连接：创建目录 + 上传。
# 默认使用仓库外的专用 Ed25519 私钥，不允许密码或键盘交互回退。

[CmdletBinding()]
param(
  [string]$Remote        = "root@8.137.23.146",
  [int]   $Port          = 22,
  [string]$ListFile      = (Join-Path $PSScriptRoot "changed_files_abs_paths.txt"),
  [string]$LocalRoot     = "D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\",
  [string]$RemoteRoot    = "/projects/ArxivPaper4/",
  [string]$IdentityFile  = (Join-Path $env:USERPROFILE ".ssh\ai4papers_sync_ed25519"),
  [string]$KnownHostsFile = (Join-Path $env:USERPROFILE ".ssh\known_hosts"),
  [switch]$InstallPublicKey,
  [switch]$DryRun
)

function Normalize-LocalRoot([string]$p) {
  $full = [System.IO.Path]::GetFullPath($p)
  if (-not $full.EndsWith('\')) { $full += '\' }
  return $full
}
function Normalize-RemoteRoot([string]$p) {
  $r = $p -replace '\\','/'
  if (-not $r.EndsWith('/')) { $r += '/' }
  return $r
}
function SftpQuote([string]$p) {
  # sftp 批处理里用双引号包本地路径；内部双引号转义
  $p = $p -replace '"','\"'
  return '"' + $p + '"'
}
function Get-RemoteDirChain([string]$dir) {
  # 生成 /a/b/c 的所有父目录：/a, /a/b, /a/b/c
  $dir = ($dir -replace '\\','/').TrimEnd('/')
  if ($dir -eq "") { return @() }
  $parts = $dir.TrimStart('/').Split('/', [System.StringSplitOptions]::RemoveEmptyEntries)
  $acc = ""
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($part in $parts) {
    $acc = $acc + "/" + $part
    $out.Add($acc)
  }
  return $out
}

$LocalRoot  = Normalize-LocalRoot $LocalRoot
$RemoteRoot = Normalize-RemoteRoot $RemoteRoot
$IdentityFile = [System.IO.Path]::GetFullPath($IdentityFile)
$KnownHostsFile = [System.IO.Path]::GetFullPath($KnownHostsFile)

if (-not (Test-Path -LiteralPath $ListFile)) { throw "List file not found: $ListFile" }
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
  throw "SSH private key not found: $IdentityFile`nCreate it with: ssh-keygen -t ed25519 -f `"$IdentityFile`" -N `"`""
}

# 私钥绝不能位于项目目录中，否则可能被 Git 或本脚本上传到服务器。
if ($IdentityFile.StartsWith($LocalRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to use a private key stored under LocalRoot: $IdentityFile"
}

$knownHostsDir = Split-Path -Parent $KnownHostsFile
if (-not (Test-Path -LiteralPath $knownHostsDir)) {
  New-Item -ItemType Directory -Path $knownHostsDir -Force | Out-Null
}

if ($InstallPublicKey) {
  $publicKeyFile = $IdentityFile + ".pub"
  if (-not (Test-Path -LiteralPath $publicKeyFile -PathType Leaf)) {
    throw "SSH public key not found: $publicKeyFile"
  }

  $publicKey = (Get-Content -LiteralPath $publicKeyFile -Raw).Trim()
  if (-not $publicKey.StartsWith("ssh-ed25519 ")) {
    throw "Unexpected public key format: $publicKeyFile"
  }

  Write-Host "Installing the public key on $Remote. Enter the server password once when prompted."
  $installCommand = 'umask 077; mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"; touch "$HOME/.ssh/authorized_keys"; chmod 600 "$HOME/.ssh/authorized_keys"; IFS= read -r key; grep -qxF "$key" "$HOME/.ssh/authorized_keys" || printf "%s\n" "$key" >> "$HOME/.ssh/authorized_keys"'
  $sshArgs = @(
    "-o","BatchMode=no",
    "-o","PubkeyAuthentication=no",
    "-o","PreferredAuthentications=password,keyboard-interactive",
    "-o","StrictHostKeyChecking=yes",
    "-o",("UserKnownHostsFile=" + $KnownHostsFile),
    "-o","ConnectTimeout=15",
    "-p",$Port,
    $Remote,
    $installCommand
  )

  $publicKey | & ssh @sshArgs
  if ($LASTEXITCODE -ne 0) { throw "Failed to install the SSH public key." }

  Write-Host "Public key installed. Verifying key-only authentication..."
  $verifyArgs = @(
    "-o","BatchMode=yes",
    "-o","IdentitiesOnly=yes",
    "-o","PreferredAuthentications=publickey",
    "-o","PasswordAuthentication=no",
    "-o","KbdInteractiveAuthentication=no",
    "-o","StrictHostKeyChecking=yes",
    "-o",("UserKnownHostsFile=" + $KnownHostsFile),
    "-o","ConnectTimeout=15",
    "-i",$IdentityFile,
    "-p",$Port,
    $Remote,
    "printf AI4PAPERS_KEY_AUTH_OK"
  )
  & ssh @verifyArgs
  if ($LASTEXITCODE -ne 0) { throw "The public key was installed but key-only authentication still failed." }
  Write-Host ""
}

$items = Get-Content -LiteralPath $ListFile |
  ForEach-Object { $_.Trim() } |
  Where-Object { $_ -ne "" -and -not $_.StartsWith("#") }

if (-not $items -or $items.Count -eq 0) {
  Write-Warning "No paths found in: $ListFile"
  exit 0
}

# 任务列表：Src / Dst
$tasks = @()
foreach ($src in $items) {
  if (-not (Test-Path -LiteralPath $src)) { Write-Warning "Missing (skip): $src"; continue }

  $srcFull = [System.IO.Path]::GetFullPath($src)

  if ($srcFull.Length -lt $LocalRoot.Length -or
      -not $srcFull.StartsWith($LocalRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Not under LocalRoot (skip): $srcFull"
    continue
  }

  $rel = $srcFull.Substring($LocalRoot.Length)
  $relPosix = $rel -replace '\\','/'
  $dst = $RemoteRoot + $relPosix
  $isDir = (Get-Item -LiteralPath $srcFull).PSIsContainer

  $tasks += [pscustomobject]@{ Src=$srcFull; Dst=$dst; IsDir=$isDir }
}

if ($tasks.Count -eq 0) { Write-Warning "No valid tasks to upload."; exit 0 }

# 需要创建的远端目录集合（用 HashSet 去重）
$remoteDirSet = New-Object 'System.Collections.Generic.HashSet[string]'

foreach ($t in $tasks) {
  # 文件：创建父目录；目录：创建目标目录本身 + 父目录链
  $targetDir = if ($t.IsDir) { $t.Dst.TrimEnd('/') } else { ($t.Dst -replace '/[^/]+$','') }
  foreach ($d in (Get-RemoteDirChain $targetDir)) { [void]$remoteDirSet.Add($d) }
}

# 重要：不要用 .ToArray()（避免你遇到的报错）
$dirs = $remoteDirSet | Sort-Object Length

# 生成 sftp 批处理文件（必须 ASCII，别用默认 UTF-16）
$batchFile = Join-Path $env:TEMP ("sftp_batch_{0}.txt" -f ([DateTime]::Now.ToString("yyyyMMdd_HHmmss")))
$lines = New-Object System.Collections.Generic.List[string]

# mkdir 没有 -p，所以把目录链都列出来；前缀 '-' 表示失败也继续（已存在会报错但忽略）
foreach ($d in $dirs) { $lines.Add("-mkdir $d") }

# 上传：文件用 put；目录用 put -r 到父目录（保证最终落点是同名目录）
foreach ($t in $tasks) {
  if ($t.IsDir) {
    $parent = ($t.Dst.TrimEnd('/') -replace '/[^/]+$','')
    $lines.Add(("put -r {0} {1}" -f (SftpQuote $t.Src), $parent))
  } else {
    $lines.Add(("put {0} {1}" -f (SftpQuote $t.Src), $t.Dst))
  }
}

$lines.Add("quit")
Set-Content -LiteralPath $batchFile -Value $lines -Encoding ASCII

try {
  $sftpArgs = @(
    "-o","BatchMode=yes",
    "-o","IdentitiesOnly=yes",
    "-o","PreferredAuthentications=publickey",
    "-o","PasswordAuthentication=no",
    "-o","KbdInteractiveAuthentication=no",
    "-o","StrictHostKeyChecking=accept-new",
    "-o",("UserKnownHostsFile=" + $KnownHostsFile),
    "-o","ConnectTimeout=15",
    "-i",$IdentityFile,
    "-P",$Port,
    "-b",$batchFile
  )
  $sftpArgs += @($Remote)

  Write-Host ("RUN: sftp " + ($sftpArgs -join " "))

  if ($DryRun) {
    Write-Host "---- batch file ----"
    $lines | ForEach-Object { Write-Host $_ }
    Write-Host "--------------------"
  } else {
    & sftp @sftpArgs
    if ($LASTEXITCODE -ne 0) { throw "sftp failed." }
  }
}
finally {
  if (Test-Path -LiteralPath $batchFile) { Remove-Item -LiteralPath $batchFile -Force }
}

Write-Host "Done."
