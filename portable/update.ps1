# Yatesium updater.
#
# Checks the GitHub repository for a newer release, downloads the zip, checks
# its SHA-256, and replaces the program files once the browser is closed. The
# Data folder is never touched, apart from the Data\Update working folder.
#
#   -Auto   Started by the browser on launch. Checks at most once a day, shows
#           nothing, and waits for the browser to close before updating.
#   (none)  Started by "Update Yatesium.cmd". Checks now and reports progress.
#
# To turn automatic updates off, create an empty file Data\no-update.txt.
param(
    [switch]$Auto,
    [string]$Repo = 'ScottYates/Yatesium',
    [string]$InstallDir = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$InstallDir = (Resolve-Path -LiteralPath $InstallDir).Path
$dataDir = Join-Path $InstallDir 'Data'
$workDir = Join-Path $dataDir 'Update'
$logFile = Join-Path $workDir 'update.log'
$exeName = 'yatesium.exe'
$clientName = 'Yatesium-Updater'

function Say([string]$text) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $text
    try { Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8 } catch {}
    if (-not $Auto) { Write-Host $text }
}

# "157.0.8103.79-2" -> a list of numbers that compares in order.
function Get-VersionKey([string]$text) {
    $parts = @($text.Trim().TrimStart('v') -split '[.\-]')
    if ($parts.Count -lt 2) { return $null }
    $key = @()
    foreach ($part in $parts) {
        $number = 0
        if (-not [int]::TryParse($part, [ref]$number)) { return $null }
        $key += $number
    }
    return ,$key
}

function Test-Newer($candidate, $current) {
    $count = [Math]::Max($candidate.Count, $current.Count)
    for ($i = 0; $i -lt $count; $i++) {
        $a = 0; $b = 0
        if ($i -lt $candidate.Count) { $a = $candidate[$i] }
        if ($i -lt $current.Count) { $b = $current[$i] }
        if ($a -ne $b) { return ($a -gt $b) }
    }
    return $false
}

function Test-BrowserRunning {
    $target = Join-Path $InstallDir $exeName
    foreach ($process in @(Get-Process -Name 'yatesium' -ErrorAction SilentlyContinue)) {
        $path = $null
        try { $path = $process.Path } catch {}
        # A process whose path cannot be read is counted as running.
        if (-not $path -or $path -ieq $target) { return $true }
    }
    return $false
}

function Get-Sha256([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

# The expected hash comes from the release asset, or from the release notes.
function Get-ExpectedHash($release, $asset) {
    if ([string]$asset.digest -match '^sha256:([0-9a-fA-F]{64})$') {
        return $Matches[1].ToLowerInvariant()
    }
    if ([string]$release.body -match 'SHA-256:\s*([0-9a-fA-F]{64})') {
        return $Matches[1].ToLowerInvariant()
    }
    return $null
}

function Remove-Tree([string]$path) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Moves the old program files out and the new ones in. Both folders are on
# the same drive, so each move is a rename. On failure the old files go back.
function Install-Update([string]$newDir, [string]$oldDir) {
    New-Item -ItemType Directory -Path $oldDir -Force | Out-Null
    $movedOut = @()
    $movedIn = @()
    try {
        foreach ($item in @(Get-ChildItem -LiteralPath $InstallDir -Force)) {
            if ($item.Name -ieq 'Data') { continue }
            Move-Item -LiteralPath $item.FullName -Destination (Join-Path $oldDir $item.Name) -Force
            $movedOut += $item.Name
        }
        foreach ($item in @(Get-ChildItem -LiteralPath $newDir -Force)) {
            if ($item.Name -ieq 'Data') { continue }
            Move-Item -LiteralPath $item.FullName -Destination (Join-Path $InstallDir $item.Name) -Force
            $movedIn += $item.Name
        }
    } catch {
        $reason = $_.Exception.Message
        foreach ($name in $movedIn) {
            Remove-Tree (Join-Path $InstallDir $name)
        }
        foreach ($name in $movedOut) {
            Move-Item -LiteralPath (Join-Path $oldDir $name) -Destination (Join-Path $InstallDir $name) -Force
        }
        throw "Could not replace the program files, the old version was put back: $reason"
    }
}

# ---------------------------------------------------------------------------

if ($Auto -and (Test-Path -LiteralPath (Join-Path $dataDir 'no-update.txt'))) { exit 0 }

New-Item -ItemType Directory -Path $workDir -Force | Out-Null

# One updater per folder.
$md5 = [Security.Cryptography.MD5]::Create()
$folderId = [BitConverter]::ToString($md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($InstallDir.ToLowerInvariant()))) -replace '-', ''
$mutex = New-Object Threading.Mutex($false, "YatesiumUpdate-$folderId")
$haveMutex = $false
try { $haveMutex = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $haveMutex = $true }
if (-not $haveMutex) {
    if (-not $Auto) { Write-Host 'An update is already in progress for this folder.' }
    exit 0
}

try {
    if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 200KB) {
        Remove-Item -LiteralPath $logFile -Force
    }

    $versionFile = Join-Path $InstallDir 'version.txt'
    if (-not (Test-Path -LiteralPath $versionFile)) { throw 'version.txt is missing, cannot tell which version is installed.' }
    $currentText = ([string](Get-Content -LiteralPath $versionFile -TotalCount 1)).Trim()
    $current = Get-VersionKey $currentText
    if (-not $current) { throw "version.txt holds '$currentText', which is not a version." }

    # Leftovers of an earlier update.
    Get-ChildItem -LiteralPath $workDir -Directory -Force |
        Where-Object { $_.Name -like 'old-*' -or $_.Name -eq 'new' } |
        ForEach-Object { Remove-Tree $_.FullName }

    $stampFile = Join-Path $workDir 'last-check.txt'
    if ($Auto) {
        # Let the browser finish starting, then check at most once a day.
        Start-Sleep -Seconds 60
        if (Test-Path -LiteralPath $stampFile) {
            $age = (Get-Date) - (Get-Item -LiteralPath $stampFile).LastWriteTime
            if ($age.TotalHours -ge 0 -and $age.TotalHours -lt 24) { exit 0 }
        }
    }

    try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -UserAgent $clientName -UseBasicParsing
    Set-Content -LiteralPath $stampFile -Value (Get-Date -Format 'o') -Encoding ASCII

    $latestText = ([string]$release.tag_name).TrimStart('v')
    $latest = Get-VersionKey $latestText
    if (-not $latest) { throw "The latest release is tagged '$($release.tag_name)', which is not a version." }
    if (-not (Test-Newer $latest $current)) {
        Say "Yatesium $currentText is up to date."
        exit 0
    }

    $asset = @($release.assets | Where-Object { $_.name -like 'Yatesium-*-win-x64.zip' })[0]
    if (-not $asset) { throw "Release $latestText has no Windows zip attached." }
    if ($asset.browser_download_url -notlike "https://github.com/$Repo/releases/download/*") {
        throw "Unexpected download address: $($asset.browser_download_url)"
    }
    $expected = Get-ExpectedHash $release $asset
    if (-not $expected) { throw "Release $latestText does not publish a SHA-256, refusing to install it." }

    $zipPath = Join-Path $workDir $asset.name
    Get-ChildItem -LiteralPath $workDir -Filter '*.zip' -File |
        Where-Object { $_.FullName -ne $zipPath } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
    if (-not ((Test-Path -LiteralPath $zipPath) -and (Get-Sha256 $zipPath) -eq $expected)) {
        Say "Downloading Yatesium $latestText ($([Math]::Round($asset.size / 1MB)) MB)..."
        $partPath = "$zipPath.part"
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $partPath -UserAgent $clientName -UseBasicParsing
        $actual = Get-Sha256 $partPath
        if ($actual -ne $expected) {
            Remove-Item -LiteralPath $partPath -Force
            throw "The download does not match the published SHA-256 (got $actual), nothing was changed."
        }
        Move-Item -LiteralPath $partPath -Destination $zipPath -Force
    }

    $newRoot = Join-Path $workDir 'new'
    Remove-Tree $newRoot
    Expand-Archive -LiteralPath $zipPath -DestinationPath $newRoot -Force
    $newDir = Join-Path $newRoot 'Yatesium'
    $newVersionFile = Join-Path $newDir 'version.txt'
    if (-not (Test-Path -LiteralPath (Join-Path $newDir $exeName)) -or -not (Test-Path -LiteralPath $newVersionFile)) {
        throw "The zip for $latestText does not look like a Yatesium build."
    }
    $newText = ([string](Get-Content -LiteralPath $newVersionFile -TotalCount 1)).Trim()
    $newKey = Get-VersionKey $newText
    if (-not $newKey -or -not (Test-Newer $newKey $current)) {
        throw "The zip holds version '$newText', which is not newer than $currentText."
    }

    if (Test-BrowserRunning) {
        Say "Yatesium $newText is ready. It will be installed when the browser is closed."
        while (Test-BrowserRunning) { Start-Sleep -Seconds 5 }
        Start-Sleep -Seconds 3
        while (Test-BrowserRunning) { Start-Sleep -Seconds 5 }
    }

    $oldDir = Join-Path $workDir "old-$currentText"
    Remove-Tree $oldDir
    Install-Update $newDir $oldDir
    Say "Updated Yatesium from $currentText to $newText."

    Remove-Tree $oldDir
    Remove-Tree $newRoot
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    exit 0
} catch {
    Say "Update failed: $($_.Exception.Message)"
    exit 1
} finally {
    if ($haveMutex) { try { $mutex.ReleaseMutex() } catch {} }
}
