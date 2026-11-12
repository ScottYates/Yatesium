# Builds Yatesium on this Windows PC.
#
# Run it by double-clicking "Build Yatesium.cmd", or from PowerShell:
#   powershell -ExecutionPolicy Bypass -File local-build.ps1
#
# What it does, skipping anything already done:
#   1. Checks disk space and memory.
#   2. Installs missing tools: Git, Python, Visual Studio 2022 Build Tools
#      with the C++ workload, and the Windows SDK Chromium needs. Windows
#      asks for administrator approval for the installs.
#   3. Clones or updates the Yatesium repository.
#   4. Runs build.py. The first run downloads about 40 GB of Chromium source
#      and compiles for several hours. Running this script again resumes.
#
# Everything goes into two folders, on C: if it has room and otherwise on the
# drive with the most free space:
#   <drive>:\yatesium   this repository
#   <drive>:\y          Chromium source, build output, logs, finished zip

param(
    [string]$Drive = '',
    [string]$RepoUrl = 'https://github.com/ScottYates/Yatesium.git',
    [int]$Jobs = 0
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$WindowsSdk = '10.0.28000.0'   # must match SDK_VERSION in src/build/vs_toolchain.py
$SdkInstallerUrl = 'https://download.microsoft.com/download/38ab8f6d-3676-4860-ae84-3361308b9d7f/KIT_BUNDLE_WINDOWSSDK_MEDIACREATION/winsdksetup.exe'
$MinFreeGB = 110

function Say($text) { Write-Host "[yatesium] $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "[yatesium] $text" -ForegroundColor Red; exit 1 }

function Find-Exe($name, $candidates) {
    # Returns the full path of a working executable, or $null.
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*\WindowsApps\*') { return $command.Source }
    return $null
}

function Install-WithWinget($id, $extraArgs) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "winget is not available. Install '$id' by hand, then run this script again."
    }
    $arguments = @('install', '--exact', '--id', $id, '--accept-source-agreements',
                   '--accept-package-agreements', '--disable-interactivity') + $extraArgs
    Say "Installing $id (approve the Windows prompt if one appears)"
    & winget @arguments
    if ($LASTEXITCODE -ne 0) { Fail "winget could not install $id (exit code $LASTEXITCODE)." }
}

# -- 1. Machine checks -------------------------------------------------------

if (-not [Environment]::Is64BitOperatingSystem) { Fail 'A 64-bit version of Windows is required.' }

$memoryGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$cores = [Environment]::ProcessorCount
Say "This PC: $cores logical processors, $memoryGB GB memory"
if ($memoryGB -lt 15) { Fail 'Building Chromium needs at least 16 GB of memory.' }

if (-not $Drive) {
    # Reuse the drive of an earlier run, otherwise take the one with most space.
    $existing = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
        Where-Object { Test-Path (Join-Path $_.DeviceID '\y\state') } | Select-Object -First 1
    if ($existing) {
        $Drive = $existing.DeviceID
    } else {
        # Prefer C: when it has room, otherwise the drive with the most space.
        $system = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
        if ($system -and ($system.FreeSpace / 1GB) -ge $MinFreeGB) {
            $Drive = 'C:'
        } else {
            $Drive = (Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
                Sort-Object FreeSpace -Descending | Select-Object -First 1).DeviceID
        }
    }
}
$Drive = $Drive.TrimEnd('\')
if ($Drive -notmatch '^[A-Za-z]:$') { Fail "Drive must look like D: (got '$Drive')." }

$buildDir = "$Drive\y"
$repoDir = "$Drive\yatesium"
$freeGB = [math]::Round((Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$Drive'").FreeSpace / 1GB)
$resuming = Test-Path "$buildDir\state\checkout"
Say "Build folder: $buildDir ($freeGB GB free on $Drive)"
if (-not $resuming -and $freeGB -lt $MinFreeGB) {
    Fail "Drive $Drive has $freeGB GB free. A first build needs about $MinFreeGB GB. Free some space, or pass -Drive X: for another drive."
}

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$logFile = "$buildDir\build.log"
Start-Transcript -Path $logFile -Append | Out-Null
Say "Log file: $logFile"

# Keep the PC awake while this script runs. This does not change any power
# setting; it ends when the script ends.
Add-Type -Namespace Yatesium -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);'
[Yatesium.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

# -- 2. Tools ----------------------------------------------------------------

$git = Find-Exe 'git' @("$env:ProgramFiles\Git\cmd\git.exe")
if (-not $git) {
    Install-WithWinget 'Git.Git' @()
    $git = Find-Exe 'git' @("$env:ProgramFiles\Git\cmd\git.exe")
    if (-not $git) { Fail 'Git was installed but git.exe was not found. Open a new window and run this again.' }
}
Say "Git: $git"

$pythonCandidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:ProgramFiles\Python313\python.exe",
    "$env:ProgramFiles\Python312\python.exe",
    "$env:ProgramFiles\Python311\python.exe")
$python = Find-Exe 'python' $pythonCandidates
if (-not $python) {
    Install-WithWinget 'Python.Python.3.12' @()
    $python = Find-Exe 'python' $pythonCandidates
    if (-not $python) { Fail 'Python was installed but python.exe was not found. Open a new window and run this again.' }
}
Say "Python: $python"

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
function Find-VisualStudio($requires) {
    if (-not (Test-Path $vswhere)) { return $null }
    $found = & $vswhere -products * -version '[17.0,19.0)' -latest -requires $requires -property installationPath
    if ($found) { return ($found | Select-Object -First 1) }
    return $null
}

$vcTools = 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64'
$atl = 'Microsoft.VisualStudio.Component.VC.ATL'
$vsPath = Find-VisualStudio @($vcTools, $atl)
if (-not $vsPath) {
    $partial = Find-VisualStudio @($vcTools)
    if ($partial) {
        Say "Adding the ATL/MFC component to Visual Studio at $partial"
        $setup = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\setup.exe"
        $process = Start-Process -FilePath $setup -Wait -PassThru -ArgumentList @(
            'modify', '--installPath', "`"$partial`"", '--add', 'Microsoft.VisualStudio.Component.VC.ATLMFC',
            '--add', $atl, '--passive', '--norestart')
        if ($process.ExitCode -ne 0 -and $process.ExitCode -ne 3010) {
            Fail "Visual Studio Installer failed (exit code $($process.ExitCode))."
        }
    } else {
        Install-WithWinget 'Microsoft.VisualStudio.2022.BuildTools' @(
            '--override',
            '--passive --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --add Microsoft.VisualStudio.Component.VC.ATLMFC --add Microsoft.VisualStudio.Component.VC.ATL')
    }
    $vsPath = Find-VisualStudio @($vcTools, $atl)
    if (-not $vsPath) { Fail 'Visual Studio with the C++ tools and ATL was not found after the install.' }
}
Say "Visual Studio: $vsPath"
# Tell Chromium where Visual Studio is, in case it is not in the default place.
$vsVersion = & $vswhere -path $vsPath -property catalog_productLineVersion
if ($vsVersion) { Set-Item -Path "Env:vs$($vsVersion)_install" -Value $vsPath }

$kits = "${env:ProgramFiles(x86)}\Windows Kits\10"
$haveSdk = (Test-Path "$kits\Include\$WindowsSdk\um\windows.h") -and (Test-Path "$kits\Debuggers\x64\dbghelp.dll")
if (-not $haveSdk) {
    Say "Installing Windows SDK $WindowsSdk with Debugging Tools (approve the Windows prompt)"
    $installer = "$buildDir\winsdksetup.exe"
    Invoke-WebRequest -Uri $SdkInstallerUrl -OutFile $installer -UseBasicParsing
    $process = Start-Process -FilePath $installer -Verb RunAs -Wait -PassThru -ArgumentList @(
        '/features', 'OptionId.DesktopCPPx64', 'OptionId.DesktopCPPx86', 'OptionId.WindowsDesktopDebuggers',
        'OptionId.UWPCPP', 'OptionId.SigningTools', '/q', '/norestart', '/ceip', 'off')
    if ($process.ExitCode -ne 0 -and $process.ExitCode -ne 3010) {
        Fail "The Windows SDK installer failed (exit code $($process.ExitCode))."
    }
    if (-not (Test-Path "$kits\Include\$WindowsSdk\um\windows.h")) {
        Fail "Windows SDK $WindowsSdk was not found after the install."
    }
}
Say "Windows SDK: $WindowsSdk"

$env:PATH = (Split-Path $git) + ';' + (Split-Path $python) + ';' + $env:PATH

# -- 3. Repository -----------------------------------------------------------

if (Test-Path "$repoDir\.git") {
    Say "Updating $repoDir"
    & $git -C $repoDir -c core.autocrlf=false pull --ff-only
    if ($LASTEXITCODE -ne 0) { Fail "Could not update $repoDir. Resolve local changes there, then run this again." }
} else {
    Say "Cloning $RepoUrl to $repoDir"
    & $git -c core.autocrlf=false clone $RepoUrl $repoDir
    if ($LASTEXITCODE -ne 0) { Fail 'Could not clone the Yatesium repository.' }
}

# -- 4. Build ----------------------------------------------------------------
#
# The build runs as a hidden child process that writes to build-output.log.
# This window stays open as a small controller. It accepts three requests,
# each given by writing one word into <build folder>\control\request.txt:
#   build   update the repository and start (or resume) the build
#   stop    stop the running build
#   quit    stop the build and close the controller
# Nothing else is accepted, so the file cannot be used to run other commands.
# The current state is written to control\status.txt every few seconds.

$ErrorActionPreference = 'Continue'
$env:PYTHONUNBUFFERED = '1'
$outputLog = "$buildDir\build-output.log"
$controlDir = "$buildDir\control"
$requestFile = "$controlDir\request.txt"
$statusFile = "$controlDir\status.txt"
$pidFile = "$controlDir\build.pid"
New-Item -ItemType Directory -Force -Path $controlDir | Out-Null
if (Test-Path $requestFile) { Remove-Item $requestFile -Force }

function Write-Status($state, $detail) {
    $lines = @("state=$state", "detail=$detail", "updated=$(Get-Date -Format o)")
    try { Set-Content -Path $statusFile -Value $lines -Encoding ASCII } catch { }
}

function Update-Repository {
    & $git -C $repoDir -c core.autocrlf=false pull --ff-only 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $outputLog -Append -Encoding ASCII
    return ($LASTEXITCODE -eq 0)
}

function Start-Build {
    $command = "`"$python`" `"$repoDir\build.py`" --build-dir `"$buildDir`""
    if ($Jobs -gt 0) { $command += " -j $Jobs" }
    $runner = "$buildDir\run-build.cmd"
    Set-Content -Path $runner -Encoding ASCII -Value @(
        '@echo off',
        "echo ==== build started %DATE% %TIME% ==== >> `"$outputLog`"",
        "$command >> `"$outputLog`" 2>&1",
        'exit /b %ERRORLEVEL%')
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/c', "`"$runner`"") -WindowStyle Hidden -PassThru
    $null = $process.Handle   # keeps the exit code readable after the process ends
    Set-Content -Path $pidFile -Value $process.Id -Encoding ASCII
    Say "Build started (process $($process.Id)). Output: $outputLog"
    return $process
}

function Find-RunningBuild {
    # A build started by an earlier controller window keeps running after
    # that window is closed. Pick it up again instead of starting a second.
    if (-not (Test-Path $pidFile)) { return $null }
    try {
        $id = [int](([string](Get-Content -Path $pidFile -Raw)).Trim())
        $process = Get-Process -Id $id -ErrorAction Stop
        if ($process.ProcessName -ne 'cmd') { return $null }
        $null = $process.Handle
        Say "Found the build already running (process $id)."
        return $process
    } catch { return $null }
}

function Stop-Build($process) {
    & taskkill.exe /T /F /PID $process.Id 2>&1 | Out-Null
    Add-Content -Path $outputLog -Value "==== build stopped on request $(Get-Date -Format o) ====" -Encoding ASCII
}

function Get-LastLogLine {
    try {
        $tail = Get-Content -Path $outputLog -Tail 1 -ErrorAction Stop
        if ($tail) { return "$tail" }
    } catch { }
    return ''
}

Say 'This window controls the build. Closing it does not stop a running build. Run the launcher again to get this window back.'
$build = Find-RunningBuild
if (-not $build) { $build = Start-Build }
$lastShown = Get-Date
$running = $true
while ($running) {
    Start-Sleep -Seconds 5

    $request = ''
    if (Test-Path $requestFile) {
        try {
            $request = ([string](Get-Content -Path $requestFile -Raw)).Trim().ToLower()
            Remove-Item $requestFile -Force
        } catch { $request = '' }
    }

    if ($build -and $build.HasExited) {
        $code = $build.ExitCode
        $build = $null
        if ($code -eq 0) {
            $zip = Get-ChildItem "$buildDir\dist\*.zip" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            Write-Status 'succeeded' "$($zip.FullName)"
            Say "Build finished. Portable browser: $($zip.FullName)"
        } else {
            Write-Status 'failed' "exit code $code"
            Say "Build stopped with exit code $code. See $outputLog"
        }
    }

    if ($request -eq 'build') {
        if ($build) {
            Say 'Build request ignored: a build is already running.'
        } elseif (Update-Repository) {
            $build = Start-Build
        } else {
            Write-Status 'failed' 'could not update the repository'
            Say "Could not update $repoDir. See $outputLog"
        }
    } elseif ($request -eq 'stop' -or $request -eq 'quit') {
        if ($build) {
            Stop-Build $build
            $build = $null
            Write-Status 'stopped' 'stopped on request'
            Say 'Build stopped on request.'
        }
        if ($request -eq 'quit') { $running = $false }
    } elseif ($request) {
        Say "Unknown request ignored: $request"
    }

    if ($build) {
        $line = Get-LastLogLine
        Write-Status 'building' $line
        if (((Get-Date) - $lastShown).TotalSeconds -ge 60) {
            if ($line.Length -gt 110) { $line = $line.Substring(0, 110) }
            Say $line
            $lastShown = Get-Date
        }
    }
}
Say 'Controller closed.'
Stop-Transcript | Out-Null
