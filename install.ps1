#Requires -Version 5.1
<#
.SYNOPSIS
  Installs slay400 (kickoff 17): downloads a release archive and its SHA-256 file over HTTPS, verifies it, unpacks
  it to <Folder>\<Version>, and rewrites a small wrapper <Folder>\bin\slay400.cmd that calls through to it. Never
  requires elevated rights, never edits a profile: it prints the one line to add to PATH, and how to check.
  Idempotent; a failed download or a wrong checksum leaves the previous installation untouched. -Uninstall removes
  only what this script created.

  Windows has no unprivileged symbolic link by default, so the stable entry point is a literal wrapper file that is
  rewritten on every install, instead of the symlink install.sh uses on POSIX.

.PARAMETER Version
  The version to install. Default: the latest GitHub release.

.PARAMETER Folder
  The install folder. Default: $HOME\.slay400.

.PARAMETER Uninstall
  Remove the installation in Folder instead of installing.

.NOTES
  Reads $env:SLAY400_RELEASES_URL and $env:SLAY400_RELEASES_API only to let tests point at a local stand-in instead
  of the real GitHub endpoints; leave both unset for a real install.
#>
param(
  [string]$Version,
  [string]$Folder = (Join-Path $HOME ".slay400"),
  [switch]$Uninstall,
  [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
  Write-Output "Usage: install.ps1 [-Version <version>] [-Folder <folder>]"
  Write-Output "       install.ps1 -Uninstall [-Folder <folder>]"
  Write-Output ""
  Write-Output "Version defaults to the latest GitHub release. Folder defaults to `$HOME\.slay400."
  exit 0
}

$Repo = "generativearchitects-ai/slay400-core"
$ReleasesUrl = if ($env:SLAY400_RELEASES_URL) { $env:SLAY400_RELEASES_URL } else { "https://github.com/$Repo/releases" }
$ReleasesApi = if ($env:SLAY400_RELEASES_API) { $env:SLAY400_RELEASES_API } else { "https://api.github.com/repos/$Repo/releases/latest" }

function Fail($message) {
  Write-Error "install.ps1: $message"
  exit 1
}

function Get-RemoteFile([string]$Uri, [string]$Destination) {
  if ($Uri -like "file://*") {
    $localPath = $Uri -replace "^file://", ""
    Copy-Item -LiteralPath $localPath -Destination $Destination -Force
  } else {
    Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing
  }
}

function Get-RemoteText([string]$Uri) {
  if ($Uri -like "file://*") {
    $localPath = $Uri -replace "^file://", ""
    return Get-Content -LiteralPath $localPath -Raw
  }
  # The response's Content is a string or a byte[] depending on the server's Content-Type header; decode either way.
  $content = (Invoke-WebRequest -Uri $Uri -UseBasicParsing).Content
  if ($content -is [byte[]]) {
    return [System.Text.Encoding]::UTF8.GetString($content)
  }
  return $content
}

function Get-LatestVersion {
  try {
    $body = Get-RemoteText $ReleasesApi
  } catch {
    Fail "could not reach $ReleasesApi to find the latest version"
  }
  if ($body -notmatch '"tag_name"\s*:\s*"v([^"]+)"') {
    Fail "could not read a tag_name from $ReleasesApi"
  }
  return $Matches[1]
}

function Install-Slay400([string]$Version, [string]$Folder) {
  if (-not $Version) {
    $Version = Get-LatestVersion
  }
  # Covers a version given on the command line and one read from the releases API (both end up here, in $Version),
  # before it is used to build a download address or a path: a stray "\" or ".." must not reach either.
  if ($Version -notmatch '^[A-Za-z0-9.+-]+$') {
    Fail "'$Version' does not look like a version (letters, digits, '.', '-', '+' only)"
  }

  $work = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
  New-Item -ItemType Directory -Path $work | Out-Null
  try {
    $archive = "slay400-$Version.zip"
    $archivePath = Join-Path $work $archive
    $checksumPath = "$archivePath.sha256"

    try {
      Get-RemoteFile "$ReleasesUrl/download/v$Version/$archive" $archivePath
      Get-RemoteFile "$ReleasesUrl/download/v$Version/$archive.sha256" $checksumPath
    } catch {
      Fail "could not download $archive"
    }

    $expected = (Get-Content -LiteralPath $checksumPath -Raw).Split(" ")[0].Trim()
    $actual = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLower()
    if ($expected.ToLower() -ne $actual) {
      Fail "checksum mismatch for $archive`: expected $expected, got $actual"
    }

    $extracted = Join-Path $work "extracted"
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extracted
    $unpacked = Join-Path $extracted "slay400-$Version"
    if (-not (Test-Path $unpacked -PathType Container)) {
      Fail "the archive did not contain slay400-$Version\"
    }

    New-Item -ItemType Directory -Path $Folder -Force | Out-Null
    $target = Join-Path $Folder $Version
    if (Test-Path $target) {
      Remove-Item -LiteralPath $target -Recurse -Force
    }
    Move-Item -LiteralPath $unpacked -Destination $target

    $bin = Join-Path $Folder "bin"
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    $wrapperTarget = Join-Path $target "bin\slay400.cmd"
    $wrapper = Join-Path $bin "slay400.cmd"
    Set-Content -LiteralPath $wrapper -Encoding ASCII -Value @(
      "@echo off",
      "`"$wrapperTarget`" %*",
      "exit /b %ERRORLEVEL%"
    )

    Write-Output "slay400 $Version installed in $target"
    Write-Output "Add this to your PATH, in your profile or in your current session:"
    Write-Output "  `$env:PATH = `"$bin;`$env:PATH`""
    Write-Output "Then check with: slay400 --version"
  } finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
  }
}

# A sub-folder is one of our installs, beyond doubt, only when its name is the content of its own VERSION file and
# it holds bin\slay400.cmd and a jar under lib\ -- not merely "has a file named VERSION", which any number of
# unrelated projects also do.
function Test-OurInstall([System.IO.DirectoryInfo]$Entry) {
  $versionFile = Join-Path $Entry.FullName "VERSION"
  if (-not (Test-Path $versionFile -PathType Leaf)) {
    return $false
  }
  if ((Get-Content -LiteralPath $versionFile -Raw).Trim() -ne $Entry.Name) {
    return $false
  }
  if (-not (Test-Path (Join-Path $Entry.FullName "bin\slay400.cmd") -PathType Leaf)) {
    return $false
  }
  $jars = Get-ChildItem -LiteralPath (Join-Path $Entry.FullName "lib") -Filter "*.jar" -ErrorAction SilentlyContinue
  return [bool]$jars
}

function Uninstall-Slay400([string]$Folder) {
  if (Test-Path $Folder) {
    Get-ChildItem -LiteralPath $Folder -Directory | ForEach-Object {
      if (Test-OurInstall $_) {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
      }
    }
    $wrapper = Join-Path $Folder "bin\slay400.cmd"
    if (Test-Path $wrapper) {
      Remove-Item -LiteralPath $wrapper -Force
    }
    $bin = Join-Path $Folder "bin"
    if ((Test-Path $bin) -and -not (Get-ChildItem -LiteralPath $bin)) {
      Remove-Item -LiteralPath $bin -Force
    }
    if (-not (Get-ChildItem -LiteralPath $Folder -ErrorAction SilentlyContinue)) {
      Remove-Item -LiteralPath $Folder -Force
    }
  }
  Write-Output "slay400: removed the installation in $Folder (anything else there was left untouched)."
}

if ($Uninstall) {
  Uninstall-Slay400 $Folder
} else {
  Install-Slay400 $Version $Folder
}
