# updater.ps1
# PowerShell script for checking and installing updates for Media Player Scrobbler for SIMKL
# This script is called by the Inno Setup installer and can also be run manually or on schedule

param (
    [switch]$Silent = $false,
    [switch]$Force = $false,
    [switch]$CheckOnly = $false
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
        $V1 = [System.Version]::Parse($Version1)
        $V2 = [System.Version]::Parse($Version2)
        
        return $V1.CompareTo($V2)
    }
    catch {
        Write-Log "Error comparing versions: $_"
        # If we can't parse as System.Version, do a string comparison
        return [string]::Compare($Version1, $Version2, $true)
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

# Display a Windows notification
function Show-Notification {
    param (
        [string]$Title,
        [string]$Message
    )

    try {
        # Load required assemblies for Windows 10 style notifications
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

        # Get the template
        $Template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
        $XmlDocument = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($Template)

        # Set the title and message in the notification
        $TextElements = $XmlDocument.GetElementsByTagName("text")
        $TextElements[0].AppendChild($XmlDocument.CreateTextNode($Title)) | Out-Null
        $TextElements[1].AppendChild($XmlDocument.CreateTextNode($Message)) | Out-Null

        # Create the notification
        $Toast = [Windows.UI.Notifications.ToastNotification]::new($XmlDocument)
        $Toast.Tag = "MPSS-Update"
        
        # Show the notification using the "MPS for SIMKL" app name
        $Notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("MPS for SIMKL")
        $Notifier.Show($Toast)
    }
    catch {
        # Fallback to PowerShell legacy notification method
        try {
            Add-Type -AssemblyName System.Windows.Forms
            $notification = New-Object System.Windows.Forms.NotifyIcon
            $notification.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon((Get-Command powershell).Path)
            $notification.BalloonTipIcon = "Info"
            $notification.BalloonTipTitle = $Title
            $notification.BalloonTipText = $Message
            $notification.Visible = $true
            $notification.ShowBalloonTip(10000)
        }
        catch {
            # If notifications fail, just log it
            Write-Log "Could not show notification: $_"
        }
    }
}

# Run the installer with correct parameters
function Run-Installer {
    param([string]$InstallerPath)
    
    try {
        Write-Log "Running installer: $InstallerPath"
        
        $Arguments = "/SILENT /SUPPRESSMSGBOXES /NORESTART"
        
        # For silent installations, we want to use the same installation dir
        $InstallDir = Get-InstallationPath
        if ($InstallDir) {
            $Arguments += " /DIR=`"$InstallDir`""
        }
        
        # Add tasks to preserve the user's choices
        $RegPath = "HKCU:\Software\$Publisher\$AppName"
        if (Test-Path $RegPath) {
            $AutoUpdate = (Get-ItemProperty -Path $RegPath -Name "AutoUpdate" -ErrorAction SilentlyContinue).AutoUpdate
            if ($AutoUpdate -eq 1) {
                $Arguments += " /TASKS=`"autoupdate`""
            }
        }
        
        # Log the command
        Write-Log "Running: Start-Process -FilePath '$InstallerPath' -ArgumentList '$Arguments' -Wait"
        
        # Execute the installer
        $Process = Start-Process -FilePath $InstallerPath -ArgumentList $Arguments -Wait -PassThru
        $ExitCode = $Process.ExitCode
        
        Write-Log "Installer completed with exit code: $ExitCode"
        
        if ($ExitCode -eq 0) {
            Show-Notification "Update Successful" "Media Player Scrobbler for SIMKL has been updated successfully."
            return $true
        }
        else {
            Write-Log "Update failed with exit code $ExitCode"
            Show-Notification "Update Failed" "The update could not be completed. Exit code: $ExitCode"
            return $false
        }
    }
    catch {
        Write-Log "Error running installer: $_"
        Show-Notification "Update Error" "An error occurred during the update: $_"
        return $false
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
        if (-not $Silent) {
            Show-Notification "Update Check Failed" "Could not check for updates. Please try again later."
        }
        return $false
    }
    
    Write-Log "Latest version: $($LatestRelease.Version)"
    
    # Compare versions
    $CompareResult = Compare-Versions -Version1 $LatestRelease.Version -Version2 $CurrentVersion
    
    if ($CompareResult -le 0 -and -not $ForceInstall) {
        Write-Log "Already running the latest version."
        if (-not $Silent) {
            Show-Notification "No Updates Available" "You are already running the latest version ($CurrentVersion)."
        }
        return $true
    }
    
    # If this is only a check, notify about available update and exit
    if ($CheckOnly) {
        Write-Log "Update available: $($LatestRelease.Version)"
        Show-Notification "Update Available" "Version $($LatestRelease.Version) is available. Current version: $CurrentVersion"
        return $true
    }
    
    # Confirm update if not silent or forced
    if (-not $Silent -and -not $ForceInstall) {
        $Confirmation = [System.Windows.Forms.MessageBox]::Show(
            "A new version ($($LatestRelease.Version)) of Media Player Scrobbler for SIMKL is available.`n`nCurrent version: $CurrentVersion`n`nDo you want to update now?",
            "Update Available",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        
        if ($Confirmation -ne [System.Windows.Forms.DialogResult]::Yes) {
            Write-Log "Update canceled by user."
            return $false
        }
    }
    
    # Check for download URL
    if (-not $LatestRelease.DownloadUrl) {
        Write-Log "No download URL found for the latest release."
        if (-not $Silent) {
            Show-Notification "Update Error" "Could not find the download URL for the latest version."
        }
        return $false
    }
    
    # Download the installer
    $InstallerPath = Download-Installer -Url $LatestRelease.DownloadUrl
    
    if (-not $InstallerPath) {
        Write-Log "Failed to download the installer."
        if (-not $Silent) {
            Show-Notification "Update Error" "Could not download the update. Please try again later."
        }
        return $false
    }
    
    # Stop running instances
    $Stopped = Stop-RunningApps
    
    if (-not $Stopped) {
        Write-Log "Failed to stop running applications."
        if (-not $Silent) {
            Show-Notification "Update Warning" "Could not stop all running instances. Update may fail."
        }
    }
    
    # Run the installer
    $Result = Run-Installer -InstallerPath $InstallerPath
    
    # Clean up the temporary file
    if (Test-Path $InstallerPath) {
        Remove-Item -Path $InstallerPath -Force
    }
    
    return $Result
}

# Main execution
try {
    # Add necessary .NET assembly for Windows Forms
    Add-Type -AssemblyName System.Windows.Forms
    
    Write-Log "========================================"
    Write-Log "MPSS Updater started with parameters:"
    Write-Log "  Silent: $Silent"
    Write-Log "  Force: $Force"
    Write-Log "  CheckOnly: $CheckOnly"
    
    # Update the "last check" timestamp
    Update-LastCheckTimestamp
    
    # Run the update check
    $Result = Check-And-Install-Update -ForceInstall $Force
    
    if ($Result) {
        Write-Log "Update process completed successfully."
        exit 0
    }
    else {
        Write-Log "Update process completed with errors."
        exit 1
    }
}
catch {
    Write-Log "Unhandled exception in updater: $_"
    if (-not $Silent) {
        [System.Windows.Forms.MessageBox]::Show(
            "An unexpected error occurred during the update process: $_",
            "Update Error",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        )
    }
    exit 1
}