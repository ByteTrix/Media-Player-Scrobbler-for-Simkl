#!/bin/bash

# updater.sh - Update script for macOS and Linux
# Checks for updates and manages installation of Media Player Scrobbler for SIMKL

# Configuration
APP_NAME="MPS for SIMKL"
REPO="kavinthangavel/simkl-movie-tracker"
USER_AGENT="MPSS-Updater/1.0"
CONFIG_DIR="${HOME}/.config/simkl-mps"
LOG_FILE="${CONFIG_DIR}/updater.log"
SILENT=false
FORCE=false
FIRST_RUN_FILE="${CONFIG_DIR}/first_run"

# Ensure config directory exists
mkdir -p "${CONFIG_DIR}"

# Logging function
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# Function to show a desktop notification
show_notification() {
    TITLE="$1"
    MESSAGE="$2"
    
    # Determine OS
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS
        osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\""
    else
        # Linux - use various notification methods
        if command -v notify-send &> /dev/null; then
            # Use notify-send if available (most Linux distros)
            ICON_PATH=""
            if [ -f "${HOME}/.local/share/icons/simkl-mps.png" ]; then
                ICON_PATH="${HOME}/.local/share/icons/simkl-mps.png"
            elif [ -f "/usr/share/icons/simkl-mps.png" ]; then
                ICON_PATH="/usr/share/icons/simkl-mps.png"
            elif [ -f "/usr/share/pixmaps/simkl-mps.png" ]; then
                ICON_PATH="/usr/share/pixmaps/simkl-mps.png"
            fi
            
            if [ -n "$ICON_PATH" ]; then
                notify-send -i "$ICON_PATH" "$TITLE" "$MESSAGE"
            else
                notify-send "$TITLE" "$MESSAGE"
            fi
        elif command -v zenity &> /dev/null; then
            # Fallback to zenity
            zenity --notification --text="$TITLE: $MESSAGE"
        else
            # Text-only fallback
            echo "$TITLE: $MESSAGE" >&2
        fi
    fi
}

# Show first run message if applicable
check_first_run() {
    if [ -f "$FIRST_RUN_FILE" ]; then
        log_message "First run detected"
        
        # Determine the platform
        if [[ "$(uname)" == "Darwin" ]]; then
            # macOS - use dialog
            osascript -e 'display dialog "Welcome to Media Player Scrobbler for SIMKL!\n\nThis app will automatically check for updates once a week.\n\nYou can manually check for updates from the app menu." buttons {"OK"} default button "OK" with title "MPSS Auto-Update"'
        else
            # Linux - use zenity if available
            if command -v zenity &> /dev/null; then
                zenity --info --title="MPSS Auto-Update" --text="Welcome to Media Player Scrobbler for SIMKL!\n\nThis app will automatically check for updates once a week.\n\nYou can manually check for updates from the app menu."
            else
                # Fall back to notification
                show_notification "MPSS Auto-Update" "Weekly update checks are enabled. You can manually check from the app menu."
            fi
        fi
        
        # Remove first run file
        rm -f "$FIRST_RUN_FILE"
    fi
}

# Get current version
get_current_version() {
    if [ -f "${CONFIG_DIR}/version.txt" ]; then
        cat "${CONFIG_DIR}/version.txt"
    else
        echo "0.0.0"  # Default if version file doesn't exist
    fi
}

# Get latest release info from GitHub
get_latest_release() {
    local api_url="https://api.github.com/repos/${REPO}/releases/latest"
    
    if command -v curl &> /dev/null; then
        curl -s -A "${USER_AGENT}" "${api_url}"
    elif command -v wget &> /dev/null; then
        wget -q -O- --header="User-Agent: ${USER_AGENT}" "${api_url}"
    else
        log_message "Error: Neither curl nor wget is installed"
        return 1
    fi
}

# Parse version from semantic version string (e.g., "v1.2.3" -> "1.2.3")
parse_version() {
    echo "$1" | sed 's/^v//'
}

# Compare versions (returns 1 if version1 > version2, 0 otherwise)
compare_versions() {
    local version1="$1"
    local version2="$2"
    
    # Use sort for version comparison
    if [ "$(echo -e "${version1}\n${version2}" | sort -V | head -n1)" = "${version2}" ]; then
        echo 1
    else
        echo 0
    fi
}

# Download and install the update
install_update() {
    local download_url="$1"
    local version="$2"
    local temp_dir
    
    # Create temporary directory
    temp_dir=$(mktemp -d)
    log_message "Created temporary directory: ${temp_dir}"
    
    # Download the file
    local filename
    
    if [[ "$(uname)" == "Darwin" ]]; then
        filename="MPSS_macOS.dmg"
    else
        filename="MPSS_Linux.tar.gz"
    fi
    
    local download_path="${temp_dir}/${filename}"
    
    log_message "Downloading update from: ${download_url}"
    
    if command -v curl &> /dev/null; then
        curl -L -A "${USER_AGENT}" -o "${download_path}" "${download_url}"
    elif command -v wget &> /dev/null; then
        wget -q --header="User-Agent: ${USER_AGENT}" -O "${download_path}" "${download_url}"
    else
        log_message "Error: Neither curl nor wget is installed"
        return 1
    fi
    
    if [ ! -f "${download_path}" ]; then
        log_message "Download failed"
        show_notification "Update Error" "Failed to download the update"
        return 1
    fi
    
    log_message "Download completed: ${download_path}"
    
    # Stop running applications
    pkill -f "MPSS" || true
    pkill -f "MPS for SIMKL" || true
    
    # Install based on platform
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS - mount DMG and copy app
        local mount_point="/Volumes/MPSS"
        log_message "Mounting DMG: ${download_path}"
        hdiutil attach "${download_path}" -mountpoint "${mount_point}"
        
        if [ -d "${mount_point}/MPSS.app" ]; then
            log_message "Installing application to /Applications"
            cp -R "${mount_point}/MPSS.app" "/Applications/"
            # Update version file
            echo "${version}" > "${CONFIG_DIR}/version.txt"
            show_notification "Update Successful" "Media Player Scrobbler for SIMKL has been updated to version ${version}"
        else
            log_message "Error: Application not found in DMG"
            show_notification "Update Failed" "Could not find the application in the downloaded package"
        fi
        
        # Unmount DMG
        hdiutil detach "${mount_point}" -force
    else
        # Linux - extract tar.gz
        local extract_dir="${temp_dir}/extract"
        mkdir -p "${extract_dir}"
        
        log_message "Extracting archive: ${download_path}"
        tar -xzf "${download_path}" -C "${extract_dir}"
        
        # Find the executable
        if [ -f "${extract_dir}/MPSS" ]; then
            log_message "Installing to ${HOME}/.local/bin"
            mkdir -p "${HOME}/.local/bin"
            cp "${extract_dir}/MPSS" "${HOME}/.local/bin/"
            cp "${extract_dir}/MPS for SIMKL" "${HOME}/.local/bin/"
            
            # Copy other required files
            if [ -d "${extract_dir}/lib" ]; then
                mkdir -p "${HOME}/.local/lib/simkl-mps"
                cp -R "${extract_dir}/lib/" "${HOME}/.local/lib/simkl-mps/"
            fi
            
            # Copy icons if present
            if [ -d "${extract_dir}/icons" ]; then
                mkdir -p "${HOME}/.local/share/icons"
                cp -R "${extract_dir}/icons/" "${HOME}/.local/share/icons/"
            fi
            
            # Make executables... executable
            chmod +x "${HOME}/.local/bin/MPSS"
            chmod +x "${HOME}/.local/bin/MPS for SIMKL"
            
            # Update version file
            echo "${version}" > "${CONFIG_DIR}/version.txt"
            show_notification "Update Successful" "Media Player Scrobbler for SIMKL has been updated to version ${version}"
        else
            log_message "Error: Executable not found in archive"
            show_notification "Update Failed" "Could not find the application in the downloaded package"
        fi
    fi
    
    # Clean up
    rm -rf "${temp_dir}"
    log_message "Cleanup completed"
}

# Main update function
check_and_install_update() {
    log_message "Checking for updates..."
    
    # Get current version
    local current_version
    current_version=$(get_current_version)
    log_message "Current version: ${current_version}"
    
    # Get latest release info from GitHub
    local release_info
    release_info=$(get_latest_release)
    
    if [ -z "${release_info}" ]; then
        log_message "Failed to get latest release info"
        show_notification "Update Check Failed" "Could not check for updates. Please try again later."
        return 1
    fi
    
    # Extract version and download URL from release info
    local latest_version
    latest_version=$(echo "${release_info}" | grep '"tag_name":' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')
    latest_version=$(parse_version "${latest_version}")
    
    log_message "Latest version: ${latest_version}"
    
    # Compare versions
    if [ "$(compare_versions "${latest_version}" "${current_version}")" -eq 0 ] && [ "${FORCE}" != "true" ]; then
        log_message "Already running the latest version"
        if [ "${SILENT}" != "true" ]; then
            show_notification "No Updates Available" "You are already running the latest version (${current_version})."
        fi
        return 0
    fi
    
    log_message "Update available: ${latest_version}"
    
    # If silent, just notify about the update
    if [ "${SILENT}" = "true" ]; then
        show_notification "Update Available" "Version ${latest_version} is available. Current version: ${current_version}"
        return 0
    fi
    
    # Get the appropriate download URL based on the platform
    local download_url
    
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS
        download_url=$(echo "${release_info}" | grep -o '"browser_download_url": *"[^"]*\.dmg"' | head -n 1 | sed -E 's/.*"browser_download_url": *"([^"]+)".*/\1/')
    else
        # Linux
        download_url=$(echo "${release_info}" | grep -o '"browser_download_url": *"[^"]*\.tar\.gz"' | head -n 1 | sed -E 's/.*"browser_download_url": *"([^"]+)".*/\1/')
    fi
    
    if [ -z "${download_url}" ]; then
        log_message "Could not find download URL for the latest version"
        show_notification "Update Error" "Could not find the download URL for the latest version"
        return 1
    fi
    
    log_message "Download URL: ${download_url}"
    
    # Ask for confirmation if not forced
    if [ "${FORCE}" != "true" ]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            # macOS dialog
            osascript -e "display dialog \"A new version (${latest_version}) of Media Player Scrobbler for SIMKL is available.\n\nCurrent version: ${current_version}\n\nDo you want to update now?\" buttons {\"Later\", \"Update Now\"} default button \"Update Now\" with title \"Update Available\""
            if [ $? -ne 0 ]; then
                log_message "Update canceled by user"
                return 0
            fi
        else
            # Linux dialog
            if command -v zenity &> /dev/null; then
                zenity --question --title="Update Available" --text="A new version (${latest_version}) of Media Player Scrobbler for SIMKL is available.\n\nCurrent version: ${current_version}\n\nDo you want to update now?"
                if [ $? -ne 0 ]; then
                    log_message "Update canceled by user"
                    return 0
                fi
            else
                # Use terminal if GUI is not available
                read -p "A new version (${latest_version}) is available. Do you want to update now? (y/N) " response
                case "$response" in
                    [yY][eE][sS]|[yY]) 
                        # Continue with update
                        ;;
                    *)
                        log_message "Update canceled by user"
                        return 0
                        ;;
                esac
            fi
        fi
    fi
    
    # Download and install the update
    install_update "${download_url}" "${latest_version}"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--silent)
            SILENT=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        --check-first-run)
            check_first_run
            exit 0
            ;;
        *)
            log_message "Unknown option: $1"
            shift
            ;;
    esac
done

# Update the "last check" timestamp
mkdir -p "${CONFIG_DIR}"
date +%s > "${CONFIG_DIR}/last_update_check"

# Check for first run
check_first_run

# Run the update check
log_message "MPSS Updater started"
check_and_install_update

log_message "Update check completed"
exit 0
