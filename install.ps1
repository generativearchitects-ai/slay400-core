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
  The version to install. Default: the latest stable release, or the newest pre-release if there is no stable one
  yet.

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
  Write-Output "Version defaults to the latest stable release, or the newest pre-release if there is no stable"
  Write-Output "one yet. Folder defaults to `$HOME\.slay400."
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

function Get-RemoteStatusAndBody([string]$Uri) {
  # Returns @{ Status = <int>; Body = <string> } for any HTTP response (2xx/4xx/5xx); throws only when the request
  # could not be made at all (DNS, connection refused, timeout). A file:// URI (used only by tests, and by
  # docs:examples' local stand-in for a release) has no HTTP status: reading it is reported as Status 200, a
  # missing file as a thrown error -- the same two outcomes Get-RemoteFile/Get-RemoteText already give.
  if ($Uri -like "file://*") {
    $localPath = $Uri -replace "^file://", ""
    if (-not (Test-Path -LiteralPath $localPath -PathType Leaf)) {
      throw "file not found: $localPath"
    }
    return @{ Status = 200; Body = (Get-Content -LiteralPath $localPath -Raw) }
  }
  try {
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing
    $body = $response.Content
    if ($body -is [byte[]]) {
      $body = [System.Text.Encoding]::UTF8.GetString($body)
    }
    return @{ Status = [int]$response.StatusCode; Body = $body }
  } catch [Microsoft.PowerShell.Commands.HttpResponseException] {
    # PowerShell 7+'s Invoke-WebRequest throws this for a non-2xx response; the response itself is still there.
    $errorResponse = $_.Exception.Response
    $responseBody = $_.ErrorDetails.Message
    return @{ Status = [int]$errorResponse.StatusCode; Body = $responseBody }
  } catch [System.Net.WebException] {
    # Windows PowerShell 5.1's Invoke-WebRequest throws this instead; a response with no HTTP status at all (the
    # exception's own Response is null) is a real network failure, not an HTTP error status.
    $errorResponse = $_.Exception.Response
    if ($null -eq $errorResponse) {
      throw
    }
    $stream = $errorResponse.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream)
    $responseBody = $reader.ReadToEnd()
    return @{ Status = [int]$errorResponse.StatusCode; Body = $responseBody }
  }
}

function Get-TagFromJson([string]$Body, [string]$Context) {
  # The version named by one JSON object's "tag_name" field, without its leading "v".
  if ($Body -notmatch '"tag_name"\s*:\s*"v([^"]+)"') {
    Fail "could not read a tag_name from $Context"
  }
  return $Matches[1]
}

function Get-FirstNonDraftTag([string]$Body) {
  # The first "tag_name" in a JSON array of releases whose own "draft" is false, in document order (GitHub's list
  # endpoint returns releases sorted by creation time, descending -- newest first), without its leading "v"; $null
  # if there is none. Not a real JSON parser, like the rest of this script's reading of "tag_name": pairs each
  # tag_name with the "draft" value that follows it and precedes the next tag_name, which is how GitHub always
  # serializes a release's own fields (never interleaved with another's).
  $matches_ = [regex]::Matches($Body, '"tag_name"\s*:\s*"(v[^"]+)"|"draft"\s*:\s*(true|false)')
  $pending = $null
  foreach ($m in $matches_) {
    if ($m.Groups[1].Success) {
      $pending = $m.Groups[1].Value
    } elseif ($m.Groups[2].Success) {
      if ($pending) {
        if ($m.Groups[2].Value -eq "false") {
          return $pending.Substring(1)
        }
        $pending = $null
      }
    }
  }
  return $null
}

function Get-LatestNonDraftRelease {
  # No stable release exists ($ReleasesApi answered 404): fall back to the newest release that is not a draft,
  # which may be a pre-release -- said so in one line, since a reader who asked for "the latest" should know which
  # kind they got. GitHub's own "latest" endpoint already excludes both drafts and pre-releases, so reaching here
  # at all means there is no stable release yet.
  $listApi = $ReleasesApi -replace "/latest$", ""
  try {
    $result = Get-RemoteStatusAndBody $listApi
  } catch {
    Fail "could not reach $ReleasesApi to find the latest version"
  }
  if ($result.Status -ne 200) {
    Fail "could not reach $ReleasesApi to find the latest version"
  }
  $tag = Get-FirstNonDraftTag $result.Body
  if (-not $tag) {
    Fail "no release exists yet at $listApi"
  }
  # -InformationAction Continue: visible by default, same as Write-Host, but (unlike Write-Host) a stream a caller
  # can still redirect or suppress, and not flagged by PSScriptAnalyzer's PSAvoidUsingWriteHost.
  Write-Information "slay400: no stable release exists yet; installing the pre-release $tag" -InformationAction Continue
  return $tag
}

function Get-LatestVersion {
  try {
    $result = Get-RemoteStatusAndBody $ReleasesApi
  } catch {
    Fail "could not reach $ReleasesApi to find the latest version"
  }
  switch ($result.Status) {
    200 { return Get-TagFromJson $result.Body $ReleasesApi }
    404 { return Get-LatestNonDraftRelease }
    default { Fail "could not reach $ReleasesApi to find the latest version" }
  }
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
