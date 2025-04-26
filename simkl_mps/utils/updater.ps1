# PowerShell Updater Script for simkl-mps
# Checks for updates, notifies user, and opens the installer download URL in browser if update is found

# Parameters
param (
    [switch]$CheckOnly,
    [switch]$Silent
)

$AppName = "Media Player Scrobbler for SIMKL"
$Publisher = "kavinthangavel"
$ApiURL = "https://api.github.com/repos/kavinthangavel/Media-Player-Scrobbler-for-Simkl/releases/latest"
$UserAgent = "MPSS-Updater/2.1"
$LogFile = Join-Path $env:LOCALAPPDATA "SIMKL-MPS\updater.log"

# Ensure log directory exists
$LogDir = Split-Path $LogFile -Parent
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Helper function to log messages
function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Add-Content -Path $LogFile -Value $LogMessage
}

# Display a Windows notification
function Show-Notification {
    param (
        [string]$Title,
        [string]$Message
    )
    Write-Log "Showing notification: $Title - $Message"
    if ($Silent) {
        Write-Log "Silent mode enabled, skipping notification."
        return
    }
    
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $notification = New-Object System.Windows.Forms.NotifyIcon
        # Try to find app icon (best effort)
        $IconPath = $null
        $PossibleIconPaths = @(
            (Join-Path -Path $PSScriptRoot -ChildPath "..\simkl-mps.ico"),
            (Join-Path -Path $PSScriptRoot -ChildPath "..\..\simkl-mps.ico"),
            (Join-Path -Path (Split-Path $PSScriptRoot -Parent) -ChildPath "assets\simkl-mps.ico"),
            "$env:ProgramFiles\Media Player Scrobbler for SIMKL\simkl-mps.ico",
            "$env:LOCALAPPDATA\Programs\Media Player Scrobbler for SIMKL\simkl-mps.ico"
        )
        foreach ($Path in $PossibleIconPaths) {
            if (Test-Path $Path) {
                $IconPath = $Path
                break
            }
        }
        if ($IconPath -and (Test-Path $IconPath)) {
            $notification.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($IconPath)
        } else {
            $notification.Icon = [System.Drawing.SystemIcons]::Information
        }
        $notification.BalloonTipTitle = $Title
        $notification.BalloonTipText = $Message
        $notification.Visible = $true
        $notification.ShowBalloonTip(15000) # Show for 15 seconds
        # Keep script running briefly to ensure notification is seen
        Start-Sleep -Seconds 6
        $notification.Dispose()
        Write-Log "Successfully displayed Windows Forms notification"
    } catch {
        Write-Log "Error showing notification: $_"
        # Fallback: MessageBox (will be visible if script isn't hidden, but shouldn't happen via tray)
        try {
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show($Message, $Title, 'OK', 'Information')
        } catch {
            Write-Log "MessageBox fallback failed: $_"
        }
    }
}

# Get current version from registry
function Get-CurrentVersion {
    $RegPath = "HKCU:\Software\$Publisher\$AppName"
    
    if (Test-Path $RegPath) {
        $Version = (Get-ItemProperty -Path $RegPath -Name "Version" -ErrorAction SilentlyContinue).Version
        if ($Version) {
            return $Version
        }
    }
    
    # Try to get version from uninstall registry
    $UninstallPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"
    if (Test-Path $UninstallPath) {
        $Version = (Get-ItemProperty -Path $UninstallPath -Name "DisplayVersion" -ErrorAction SilentlyContinue).DisplayVersion
        if ($Version) {
            return $Version
        }
    }
    
    # Admin installation check
    $AdminUninstallPath = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"
    if (Test-Path $AdminUninstallPath) {
        $Version = (Get-ItemProperty -Path $AdminUninstallPath -Name "DisplayVersion" -ErrorAction SilentlyContinue).DisplayVersion
        if ($Version) {
            return $Version
        }
    }
    
    return "0.0.0"
}

# Compare version strings
function Compare-Versions {
    param([string]$Version1, [string]$Version2)
    
    try {
        # Ensure versions are properly formatted by removing any leading 'v'
        $Version1 = $Version1 -replace '^v', ''
        $Version2 = $Version2 -replace '^v', ''
        
        # If versions are identical strings, return 0 immediately
        if ($Version1 -eq $Version2) {
            Write-Log "Versions are identical: $Version1 = $Version2"
            return 0
        }
        
        # Handle versions with different segment counts like "2.0" vs "2.0.0"
        $V1Parts = $Version1.Split('.')
        $V2Parts = $Version2.Split('.')
        
        # Pad the shorter version with zeros
        if ($V1Parts.Length -ne $V2Parts.Length) {
            $MaxLength = [Math]::Max($V1Parts.Length, $V2Parts.Length)
            if ($V1Parts.Length -lt $MaxLength) {
                $V1Parts = $V1Parts + (0..($MaxLength - $V1Parts.Length - 1) | ForEach-Object { "0" })
                $Version1 = [string]::Join(".", $V1Parts)
            }
            if ($V2Parts.Length -lt $MaxLength) {
                $V2Parts = $V2Parts + (0..($MaxLength - $V2Parts.Length - 1) | ForEach-Object { "0" })
                $Version2 = [string]::Join(".", $V2Parts)
            }
            Write-Log "Normalized versions for comparison: $Version1 vs $Version2"
        }
        
        # Parse as System.Version for proper comparison
        $V1 = [System.Version]::Parse($Version1)
        $V2 = [System.Version]::Parse($Version2)
        
        $Result = $V1.CompareTo($V2)
        Write-Log "Version comparison result: $Result (>0 means $Version1 is newer than $Version2)"
        return $Result
    }
    catch {
        Write-Log "Error comparing versions: $_"
        # Last resort fallback to string comparison
        if ($Version1 -eq $Version2) { return 0 }
        elseif ($Version1 -gt $Version2) { return 1 }
        else { return -1 }
    }
}

# Check GitHub for the latest release
function Get-LatestReleaseInfo {
    Write-Log "Checking for updates..."
    
    try {
        # Check for internet connectivity first
        if (-not (Test-Connection -ComputerName "github.com" -Count 1 -Quiet -ErrorAction SilentlyContinue)) {
            Write-Log "No internet connection available."
            return @{
                ErrorMessage = "No internet connection available. Please check your network settings and try again later."
                NoConnection = $true
            }
        }
        
        # Set TLS 1.2 for HTTPS connections
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        
        $Headers = @{
            "User-Agent" = $UserAgent
        }
        
        $Response = Invoke-RestMethod -Uri $ApiURL -Headers $Headers -Method Get
        
        if ($Response.tag_name) {
            # Clean up version string (remove leading 'v' if present)
            $Version = $Response.tag_name -replace '^v', ''
            
            # Ensure version is properly formatted with at least one decimal (e.g., convert "2" to "2.0")
            if ($Version -notmatch '\.') {
                $Version = "$Version.0"
                Write-Log "Added decimal to version number: $Version"
            }
            
            $ReleaseInfo = @{
                Version = $Version
                PublishedAt = $Response.published_at
                Name = $Response.name
                Body = $Response.body
                DownloadUrl = $null
            }
            
            # Find the Windows installer asset
            foreach ($Asset in $Response.assets) {
                if ($Asset.name -like "*Setup*.exe") {
                    $ReleaseInfo.DownloadUrl = $Asset.browser_download_url
                    break
                }
            }
            
            Write-Log "Latest release found: v$Version released on $($Response.published_at)"
            if ($ReleaseInfo.DownloadUrl) {
                Write-Log "Installer URL: $($ReleaseInfo.DownloadUrl)"
            } else {
                Write-Log "Warning: No installer asset found in release"
            }
            
            return $ReleaseInfo
        }
    }
    catch {
        Write-Log "Error checking for updates: $_"
        # Check if the error is network-related
        if ($_.Exception.Message -match "network|connection|internet|timeout|unable to connect" -or 
            $_.Exception.InnerException.Message -match "network|connection|internet|timeout|unable to connect") {
            return @{
                ErrorMessage = "Could not connect to update server. Please check your internet connection and try again later."
                NoConnection = $true
            }
        }
        return @{
            ErrorMessage = "Error checking for updates: $_"
            NoConnection = $false
        }
    }
    
    return $null
}

# --- Main Logic ---
try {
    Write-Log "========================================"
    Write-Log "MPSS Updater started - CheckOnly: $CheckOnly, Silent: $Silent"

    # Get current version
    $CurrentVersion = Get-CurrentVersion
    Write-Log "Current version: $CurrentVersion"

    # Check for updates
    $LatestRelease = Get-LatestReleaseInfo

    if ($null -eq $LatestRelease) {
        Write-Log "Failed to check for updates."
        Show-Notification "Update Check Failed" "Could not check for updates. Please try again later or check logs."
        exit 1
    }
    
    # Handle network connectivity errors
    if ($LatestRelease.ContainsKey("ErrorMessage")) {
        Write-Log $LatestRelease.ErrorMessage
        
        if ($LatestRelease.NoConnection) {
            # Don't show any notification if running as weekly scheduled task 
            if (-not ([Environment]::GetCommandLineArgs() -match "Task Scheduler")) {
                Show-Notification "Update Check Failed" "Could not check for updates. No internet connection available."
            }
            # Exit quietly without error for scheduled tasks to avoid unnecessary error messages
            exit 0
        } else {
            Show-Notification "Update Error" $LatestRelease.ErrorMessage
            exit 1
        }
    }

    Write-Log "Latest version found: $($LatestRelease.Version)"

    # Compare versions
    $CompareResult = Compare-Versions -Version1 $LatestRelease.Version -Version2 $CurrentVersion
    if ($CurrentVersion -eq "0.0.0" -or [string]::IsNullOrWhiteSpace($CurrentVersion)) {
        $CompareResult = 1 # Treat as update needed if current version unknown
    }

    if ($CompareResult -gt 0) {
        Write-Log "Update available: $($LatestRelease.Version)"
        
        # Output in the expected format for parsing by the application
        $DownloadUrl = if ($LatestRelease.DownloadUrl) { $LatestRelease.DownloadUrl } else { "https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/releases/latest" }
        Write-Output "UPDATE_AVAILABLE: $($LatestRelease.Version) $DownloadUrl"
        
        if ($CheckOnly -eq $false) {
            if ($LatestRelease.DownloadUrl) {
                Show-Notification "Update Available" "Version $($LatestRelease.Version) is available! Opening download page..."
                # Open the specific installer download URL in the default browser
                Start-Process $LatestRelease.DownloadUrl
            } else {
                Write-Log "Error: Download URL not found in release info."
                Show-Notification "Update Error" "Version $($LatestRelease.Version) is available, but the download link could not be found."
            }
        } else {
            Show-Notification "Update Available" "Version $($LatestRelease.Version) is available! Current version: $CurrentVersion"
        }
    } else {
        Write-Log "No update available. Already running the latest version ($CurrentVersion)."
        # Output in the expected format for parsing by the application
        Write-Output "NO_UPDATE: $CurrentVersion"
        
        if ($CheckOnly -and -not $Silent) {
            Show-Notification "No Updates Found" "You are already running the latest version ($CurrentVersion)."
        }
    }

    Write-Log "Updater check finished."
    exit 0

} catch {
    Write-Log "Unhandled exception in updater: $_"
    Show-Notification "Update Error" "An unexpected error occurred during the update check: $_"
    exit 5
}