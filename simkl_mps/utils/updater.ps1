# updater.ps1
# PowerShell script for checking and installing updates for Media Player Scrobbler for SIMKL
# This script is called by the Inno Setup installer and can also be run manually or on schedule

param (
    [switch]$Silent = $false,         # Suppress non-essential console output (still logs to file)
    [switch]$Force = $false,          # Force update check even if version matches
    [switch]$CheckOnly = $false,      # Only check for updates, don't download or install
    [switch]$SilentInstall = $false  # Perform installation silently without notifications/prompts
)

# Constants
$AppName = "Media Player Scrobbler for SIMKL"
$Publisher = "kavinthangavel"
$RepoURL = "https://github.com/kavinthangavel/simkl-movie-tracker"
$ReleasesURL = "https://github.com/kavinthangavel/simkl-movie-tracker/releases"
$ApiURL = "https://api.github.com/repos/kavinthangavel/simkl-movie-tracker/releases/latest"
$UserAgent = "MPSS-Updater/1.0"
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
    
    if (-not $Silent) {
        Write-Host $LogMessage
    }
    
    Add-Content -Path $LogFile -Value $LogMessage
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

# Get installation path from registry
function Get-InstallationPath {
    $RegPath = "HKCU:\Software\$Publisher\$AppName"
    
    if (Test-Path $RegPath) {
        $InstallPath = (Get-ItemProperty -Path $RegPath -Name "InstallPath" -ErrorAction SilentlyContinue).InstallPath
        if ($InstallPath -and (Test-Path $InstallPath)) {
            return $InstallPath
        }
    }
    
    # Try to get path from uninstall registry
    $UninstallPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"
    if (Test-Path $UninstallPath) {
        $InstallPath = (Get-ItemProperty -Path $UninstallPath -Name "InstallLocation" -ErrorAction SilentlyContinue).InstallLocation
        if ($InstallPath -and (Test-Path $InstallPath)) {
            return $InstallPath
        }
    }
    
    # Admin installation check
    $AdminUninstallPath = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"
    if (Test-Path $AdminUninstallPath) {
        $InstallPath = (Get-ItemProperty -Path $AdminUninstallPath -Name "InstallLocation" -ErrorAction SilentlyContinue).InstallLocation
        if ($InstallPath -and (Test-Path $InstallPath)) {
            return $InstallPath
        }
    }
    
    return $null
}

# Check if automatic updates are enabled
function Is-AutoUpdateEnabled {
    $RegPath = "HKCU:\Software\$Publisher\$AppName"
    
    if (Test-Path $RegPath) {
        $AutoUpdate = (Get-ItemProperty -Path $RegPath -Name "AutoUpdate" -ErrorAction SilentlyContinue).AutoUpdate
        if ($null -ne $AutoUpdate) {
            return [bool]$AutoUpdate
        }
    }
    
    return $false
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
    }
    
    return $null
}

# Download the installer to a temporary location
function Download-Installer {
    param([string]$Url)
    
    try {
        $TempFile = [System.IO.Path]::GetTempFileName() + ".exe"
        
        Write-Log "Downloading update to $TempFile..."
        
        # Set TLS 1.2 for HTTPS connections
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        
        $WebClient = New-Object System.Net.WebClient
        $WebClient.Headers.Add("User-Agent", $UserAgent)
        $WebClient.DownloadFile($Url, $TempFile)
        
        Write-Log "Download completed."
        return $TempFile
    }
    catch {
        Write-Log "Error downloading update: $_"
        return $null
    }
}

# Stop running applications before update
function Stop-RunningApps {
    try {
        $Processes = @("MPSS", "MPS for Simkl")
        
        foreach ($Process in $Processes) {
            $Running = Get-Process -Name $Process -ErrorAction SilentlyContinue
            if ($Running) {
                Write-Log "Stopping $Process..."
                Stop-Process -Name $Process -Force
                Start-Sleep -Seconds 2
            }
        }
        return $true
    }
    catch {
        Write-Log "Error stopping applications: $_"
        return $false
    }
}

# Update the "last check" timestamp in registry
function Update-LastCheckTimestamp {
    $RegPath = "HKCU:\Software\$Publisher\$AppName"
    
    if (-not (Test-Path $RegPath)) {
        New-Item -Path $RegPath -Force | Out-Null
    }
    
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Set-ItemProperty -Path $RegPath -Name "LastUpdateCheck" -Value $Timestamp
}

# Display a Windows notification - simplified version that always works
# Suppressed if $SilentInstall is true
function Show-Notification {
    param (
        [string]$Title,
        [string]$Message
    )

    # Suppress notifications during silent install
    if ($SilentInstall) {
        Write-Log "Notification suppressed (SilentInstall): $Title - $Message"
        return
    }

    Write-Log "Showing notification: $Title - $Message"

    # Use WPF dialog that mimics a notification without relying on OS notification system
    try {
        # Load required assemblies first to check if they exist
        Add-Type -AssemblyName System.Windows.Forms
        $notification = New-Object System.Windows.Forms.NotifyIcon
        
        # Try to find the app icon
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
        
        # Use system icon if we can't find the app icon
        if ($IconPath -and (Test-Path $IconPath)) {
            $notification.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($IconPath)
        } else {
            $notification.Icon = [System.Drawing.SystemIcons]::Information
        }
        
        $notification.BalloonTipTitle = $Title
        $notification.BalloonTipText = $Message
        $notification.Visible = $true
        $notification.ShowBalloonTip(10000)
        
        # Keep PowerShell process running long enough for notification to be seen
        Start-Sleep -Seconds 5
        $notification.Dispose()
        
        Write-Log "Successfully displayed Windows Forms notification"
        return
    }
    catch {
        Write-Log "Error with Windows Forms notification: $_"
    }
    
    # Fallback to MessageBox if notification fails
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($Message, $Title, 'OK', 'Information')
        Write-Log "Displayed MessageBox as fallback"
        return
    }
    catch {
        Write-Log "All notification methods failed. Error: $_"
    }
}

# Run the installer with correct parameters
function Run-Installer {
    param([string]$InstallerPath)
    
    try {
        Write-Log "Running installer: $InstallerPath"
        
        # Verify the installer file exists and has content
        if (-not (Test-Path $InstallerPath)) {
            Write-Log "ERROR: Installer file not found at $InstallerPath"
            return $false
        }
        
        $FileInfo = Get-Item $InstallerPath
        if ($FileInfo.Length -lt 1000000) {  # Less than ~1MB is suspicious for an installer
            Write-Log "WARNING: Installer file seems too small (${$FileInfo.Length} bytes)"
        }
        
        # Create more robust installer arguments
        $Arguments = "/SILENT /SUPPRESSMSGBOXES /NORESTART"
        
        # For silent installations, we want to use the same installation dir
        $InstallDir = Get-InstallationPath
        if ($InstallDir) {
            # Make sure there are no trailing backslashes that could break paths
            $InstallDir = $InstallDir.TrimEnd('\')
            $Arguments += " /DIR=`"$InstallDir`""
            Write-Log "Using existing installation directory: $InstallDir"
        }
        
        # Add tasks to preserve the user's choices
        $RegPath = "HKCU:\Software\$Publisher\$AppName"
        $TasksString = ""
        
        # Check for desktop icon preference
        $DesktopIcon = $false
        if (Test-Path $RegPath) {
            $DesktopIcon = (Get-ItemProperty -Path $RegPath -Name "DesktopIcon" -ErrorAction SilentlyContinue).DesktopIcon
        }
        if ($DesktopIcon -eq 1) {
            $TasksString += "desktopicon,"
        }
        
        # Check for startup preference - default to true if not found
        $StartupIcon = $true
        if (Test-Path $RegPath) {
            $StartupIconValue = (Get-ItemProperty -Path $RegPath -Name "StartupIcon" -ErrorAction SilentlyContinue).StartupIcon
            if ($null -ne $StartupIconValue) {
                $StartupIcon = ($StartupIconValue -eq 1)
            }
        }
        if ($StartupIcon) {
            $TasksString += "startupicon,"
        }
        
        # Check for auto-update preference
        $AutoUpdate = $true  # Default to true
        if (Test-Path $RegPath) {
            $AutoUpdateValue = (Get-ItemProperty -Path $RegPath -Name "CheckUpdates" -ErrorAction SilentlyContinue).CheckUpdates
            if ($null -ne $AutoUpdateValue) {
                $AutoUpdate = ($AutoUpdateValue -eq 1)
            }
        }
        if ($AutoUpdate) {
            $TasksString += "scheduledupdate,"
        }
        
        # Trim trailing comma and add to arguments if any tasks were specified
        $TasksString = $TasksString.TrimEnd(',')
        if ($TasksString) {
            $Arguments += " /TASKS=`"$TasksString`""
        }
        
        # Log the command
        Write-Log "Running: Start-Process -FilePath '$InstallerPath' -ArgumentList '$Arguments' -Wait"
        
        # Execute the installer
        $Process = Start-Process -FilePath $InstallerPath -ArgumentList $Arguments -Wait -PassThru
        $ExitCode = $Process.ExitCode
        
        Write-Log "Installer completed with exit code: $ExitCode"
        
        # Code 0 = success, Code 3010 = success but needs reboot
        if ($ExitCode -eq 0 -or $ExitCode -eq 3010) {
            if (-not $SilentInstall) {
                if ($ExitCode -eq 3010) {
                    Show-Notification "Update Successful - Restart Required" "Media Player Scrobbler for SIMKL has been updated successfully. Please restart your computer to complete the installation."
                } else {
                    Show-Notification "Update Successful" "Media Player Scrobbler for SIMKL has been updated successfully."
                }
            }

            # Wait a moment before trying to restart the app
            Start-Sleep -Seconds 2
            
            # Try to restart the application after update
            try {
                $InstallDir = Get-InstallationPath
                if ($InstallDir -and (Test-Path "$InstallDir\MPS for Simkl.exe")) {
                    Write-Log "Attempting to restart the application..."
                    Start-Process -FilePath "$InstallDir\MPS for Simkl.exe" -ArgumentList "start"
                }
            }
            catch {
                Write-Log "Error restarting application: $_"
            }
            
            return $true
        }
        else {
            Write-Log "Update failed with exit code $ExitCode"
            if (-not $SilentInstall) {
                Show-Notification "Update Failed" "The update could not be completed. Exit code: $ExitCode"
            }
            return $false # Indicate installer failure
        }
    }
    catch {
        Write-Log "Error running installer: $_"
        if (-not $SilentInstall) {
            Show-Notification "Update Error" "An error occurred during the update: $_"
        }
        return $false # Indicate installer failure
    }
}

# Main update check and installation logic
function Check-And-Install-Update {
    param([switch]$ForceInstall = $false)
    
    # Get current version
    $CurrentVersion = Get-CurrentVersion
    Write-Log "Current version: $CurrentVersion"
    
    # Check for updates
    $LatestRelease = Get-LatestReleaseInfo
    
    if ($null -eq $LatestRelease) {
        Write-Log "Failed to check for updates."
        if (-not $SilentInstall) { # Use SilentInstall to control user-facing notifications
            Show-Notification "Update Check Failed" "Could not check for updates. Please try again later."
        }
        # Exit Code 1: Failed to check for updates
        exit 1
    }

    Write-Log "Latest version: $($LatestRelease.Version)"
    
    # Compare versions
    $CompareResult = Compare-Versions -Version1 $LatestRelease.Version -Version2 $CurrentVersion
    # If current version is 0.0.0 or empty, always treat as update needed
    if ($CurrentVersion -eq "0.0.0" -or [string]::IsNullOrWhiteSpace($CurrentVersion)) {
        $CompareResult = 1
        Write-Log "Current version is 0.0.0 or empty, forcing update available."
    }
    
    if ($CompareResult -le 0 -and -not $ForceInstall) {
        Write-Log "Already running the latest version."
        if (-not $SilentInstall) { # Use SilentInstall to control user-facing notifications
            Show-Notification "No Updates Available" "You are already running the latest version ($CurrentVersion)."
        }
        # Exit Code 0: Success (no update needed)
        exit 0
    }

    # If this is only a check, output status to stdout and exit
    if ($CheckOnly) {
        if ($CompareResult > 0) {
            Write-Log "Update available: $($LatestRelease.Version)"
            # Output parsable string for calling application
            Write-Host "UPDATE_AVAILABLE: $($LatestRelease.Version) $($LatestRelease.DownloadUrl)"
            # Optionally show notification if not silent
            if (-not $Silent -and -not $SilentInstall) {
                 Show-Notification "Update Available" "Version $($LatestRelease.Version) is available. Current version: $CurrentVersion"
            }
        } else {
            Write-Log "No update available - already on latest version $CurrentVersion"
            # Output parsable string for calling application
            Write-Host "NO_UPDATE: $CurrentVersion"
             # Optionally show notification if not silent
            if (-not $Silent -and -not $SilentInstall) {
                 Show-Notification "No Updates Available" "You are already running the latest version ($CurrentVersion)."
            }
        }
        # Exit Code 0: Success (check completed)
        exit 0
    }

    # Confirm update if not silent or forced or silent install
    if (-not $Silent -and -not $ForceInstall -and -not $SilentInstall) {
        $Confirmation = [System.Windows.Forms.MessageBox]::Show(
            "A new version ($($LatestRelease.Version)) of Media Player Scrobbler for SIMKL is available.`n`nCurrent version: $CurrentVersion`n`nDo you want to update now?",
            "Update Available",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        
        if ($Confirmation -ne [System.Windows.Forms.DialogResult]::Yes) {
            Write-Log "Update canceled by user."
            # Exit Code 0: User cancelled (not an error)
            exit 0
        }
    }

    # Check for download URL
    if (-not $LatestRelease.DownloadUrl) {
        Write-Log "No download URL found for the latest release."
        if (-not $SilentInstall) { # Use SilentInstall to control user-facing notifications
            Show-Notification "Update Error" "Could not find the download URL for the latest version."
        }
        # Exit Code 2: Failed to find download URL (treat as download failure)
        exit 2
    }

    # Download the installer
    $InstallerPath = Download-Installer -Url $LatestRelease.DownloadUrl
    
    if (-not $InstallerPath) {
        Write-Log "Failed to download the installer."
        if (-not $SilentInstall) { # Use SilentInstall to control user-facing notifications
            Show-Notification "Update Error" "Could not download the update. Please try again later."
        }
        # Exit Code 2: Failed to download
        exit 2
    }

    # Stop running instances
    $Stopped = Stop-RunningApps
    
    if (-not $Stopped) {
        Write-Log "Failed to stop running applications. Update might fail."
        if (-not $SilentInstall) { # Use SilentInstall to control user-facing notifications
            Show-Notification "Update Warning" "Could not stop all running instances. Update may fail."
        }
        # Don't exit here, just warn. Installer might still work.
        # Consider adding Exit Code 3 if this becomes critical
    }

    # Run the installer
    $InstallSuccess = Run-Installer -InstallerPath $InstallerPath

    # Clean up the temporary file
    if (Test-Path $InstallerPath) {
        Remove-Item -Path $InstallerPath -Force
    }

    if (-not $InstallSuccess) {
        # Exit Code 4: Installer failed
        exit 4
    }

    # Exit Code 0: Success (update installed)
    exit 0
}

# Main execution
try {
    # Add necessary .NET assembly for Windows Forms
    Add-Type -AssemblyName System.Windows.Forms
    
    Write-Log "========================================"
    Write-Log "MPSS Updater started with parameters:"
    Write-Log "  Silent: $Silent"          # Console output suppressed
    Write-Log "  Force: $Force"           # Force check/install
    Write-Log "  CheckOnly: $CheckOnly"       # Only check, don't install
    Write-Log "  SilentInstall: $SilentInstall" # Install without notifications/prompts

    # Update the "last check" timestamp
    Update-LastCheckTimestamp
    
    # Run the update check
    # Run the update check/install process
    # The Check-And-Install-Update function now handles its own exit codes
    Check-And-Install-Update -ForceInstall $Force

    # Note: The script will exit within Check-And-Install-Update based on the outcome.
    # This part might not be reached unless Check-And-Install-Update is modified further.
    Write-Log "Updater script finished."
    exit 0 # Default exit code if somehow reached here

}
catch {
    Write-Log "Unhandled exception in updater: $_"
    if (-not $SilentInstall) { # Use SilentInstall to control user-facing notifications
        [System.Windows.Forms.MessageBox]::Show(
            "An unexpected error occurred during the update process: $_",
            "Update Error",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        )
    }
    # Exit Code 5: Unhandled exception
    exit 5
}