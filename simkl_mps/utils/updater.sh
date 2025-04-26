#!/bin/bash

# updater.sh - Update script for Mac and Linux
# Checks for updates to the simkl-mps package on PyPI and installs them

# Configuration
APP_NAME="Media Player Scrobbler for SIMKL"
PACKAGE_NAME="simkl-mps"
PYPI_URL="https://pypi.org/pypi/${PACKAGE_NAME}/json"
USER_AGENT="MPSS-Updater/2.1"
SILENT=false
CHECK_ONLY=false  # Flag to only check, don't install
FORCE=false

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    # macOS-specific paths
    CONFIG_DIR="${HOME}/Library/Application Support/kavinthangavel/simkl-mps"
    PACKAGE_EXTRAS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    # Linux-specific paths
    CONFIG_DIR="${HOME}/.local/share/kavinthangavel/simkl-mps"
    PACKAGE_EXTRAS="linux"
else
    echo "Unsupported operating system: $OSTYPE"
    exit 1
fi

LOG_FILE="${CONFIG_DIR}/updater.log"

# Command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --Silent|-s)
            SILENT=true
            shift
            ;;
        --CheckOnly)
            CHECK_ONLY=true
            shift
            ;;
        --Force|-f)
            FORCE=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Ensure config directory exists
mkdir -p "${CONFIG_DIR}"

# Logging function
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

log_message "========== Update Check Started =========="
log_message "OS detected: $OS"

# Function to show a desktop notification
show_notification() {
    TITLE="$1"
    MESSAGE="$2"
    
    if [[ "$OS" == "macos" ]]; then
        # macOS notifications using osascript
        osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\""
    else
        # Linux notifications
        if command -v notify-send &> /dev/null; then
            # Use notify-send if available (most Linux distros)
            ICON_PATH=""
            if [ -f "${HOME}/.local/share/icons/simkl-mps.png" ]; then
                ICON_PATH="${HOME}/.local/share/icons/simkl-mps.png"
            elif [ -f "/usr/share/icons/simkl-mps.png" ]; then
                ICON_PATH="/usr/share/icons/simkl-mps.png"
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
    
    log_message "Notification: $TITLE - $MESSAGE"
}

# Get the installed simkl-mps version
get_installed_version() {
    local version=""
    
    # Try different methods to get the version
    
    # Method 1: Check if simkl-mps is installed in the current Python environment
    if command -v simkl-mps &> /dev/null; then
        version=$(simkl-mps --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        if [ -n "$version" ]; then
            log_message "Found version using simkl-mps command: $version"
            echo "$version"
            return
        fi
    fi
    
    # Method 2: Try using pip show
    if command -v pip3 &> /dev/null; then
        version=$(pip3 show simkl-mps 2>/dev/null | grep -E "^Version:" | cut -d " " -f 2)
        if [ -n "$version" ]; then
            log_message "Found version using pip3 show: $version"
            echo "$version"
            return
        fi
    fi

    if command -v pip &> /dev/null; then
        version=$(pip show simkl-mps 2>/dev/null | grep -E "^Version:" | cut -d " " -f 2)
        if [ -n "$version" ]; then
            log_message "Found version using pip show: $version"
            echo "$version"
            return
        fi
    fi
    
    # Method 3: Try using pipx list if installed with pipx
    if command -v pipx &> /dev/null; then
        version=$(pipx list | grep "simkl-mps" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        if [ -n "$version" ]; then
            log_message "Found version using pipx list: $version"
            echo "$version"
            return
        fi
    fi
    
    # Method 4: Try to extract version from Python package
    version=$(python3 -c "
try:
    import importlib.metadata
    try:
        print(importlib.metadata.version('simkl-mps'))
    except importlib.metadata.PackageNotFoundError:
        pass
except ImportError:
    try:
        import pkg_resources
        print(pkg_resources.get_distribution('simkl-mps').version)
    except (ImportError, pkg_resources.DistributionNotFound):
        pass
" 2>/dev/null)
    
    if [ -n "$version" ]; then
        log_message "Found version using Python importlib.metadata/pkg_resources: $version"
        echo "$version"
        return
    fi
    
    # If we still don't have a version, check stored version file
    if [ -f "${CONFIG_DIR}/version.txt" ]; then
        version=$(cat "${CONFIG_DIR}/version.txt")
        if [ -n "$version" ]; then
            log_message "Found version in version.txt: $version"
            echo "$version"
            return
        fi
    fi
    
    # Still no version? Return a default
    log_message "Could not determine installed version, using default: 0.0.0"
    echo "0.0.0"
}

# Get the latest version from PyPI
get_latest_version() {
    local pypi_response=""
    
    # Try curl first, then wget as fallback
    if command -v curl &> /dev/null; then
        pypi_response=$(curl -s -L -A "${USER_AGENT}" "${PYPI_URL}")
    elif command -v wget &> /dev/null; then
        pypi_response=$(wget -q -O- --header="User-Agent: ${USER_AGENT}" "${PYPI_URL}")
    else
        log_message "Error: Neither curl nor wget is installed"
        show_notification "Update Error" "Update check failed: curl or wget is required"
        return ""
    fi
    
    # Check if we got a valid response
    if [ -z "$pypi_response" ]; then
        log_message "Error: Empty response from PyPI"
        return ""
    fi
    
    # Extract version from JSON response
    if command -v jq &> /dev/null; then
        # Use jq if available for reliable JSON parsing
        local latest_version=$(echo "$pypi_response" | jq -r .info.version)
        log_message "Latest version from PyPI (using jq): $latest_version"
        echo "$latest_version"
    else
        # Fallback to Python for JSON parsing
        latest_version=$(python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    print(data['info']['version'])
except Exception as e:
    print(f'Error parsing JSON: {e}', file=sys.stderr)
    exit(1)
" <<< "$pypi_response" 2>/dev/null)

        # If Python method failed, try with grep/sed
        if [ -z "$latest_version" ]; then
            latest_version=$(echo "$pypi_response" | grep -o '"version":"[^"]*"' | grep -o '[0-9][0-9.]*' | head -1)
        fi
        
        log_message "Latest version from PyPI: $latest_version"
        echo "$latest_version"
    fi
}

# Compare version strings (returns 1 if version1 > version2, 0 if equal, -1 if version1 < version2)
compare_versions() {
    local version1="$1"
    local version2="$2"
    
    # Ensure we have non-empty versions to compare
    if [ -z "$version1" ] || [ -z "$version2" ]; then
        log_message "Warning: Empty version in comparison '$version1' vs '$version2'"
        # If either version is empty, assume we need an update
        if [ -z "$version1" ]; then
            echo -1  # version1 is empty, so version2 is "greater"
        else
            echo 1   # version2 is empty, so version1 is "greater"
        fi
        return
    fi
    
    # Normalize versions to strip any leading 'v'
    version1=$(echo "$version1" | sed 's/^v//')
    version2=$(echo "$version2" | sed 's/^v//')
    
    # If versions are identical, return 0
    if [ "$version1" = "$version2" ]; then
        echo 0
        return
    fi
    
    # Use Python for reliable version comparison if available
    local result=$(python3 -c "
from packaging import version
try:
    v1 = version.parse('$version1')
    v2 = version.parse('$version2')
    print(1 if v1 > v2 else -1)
except:
    # Fallback if packaging module isn't available
    import sys
    print(-1 if '$version1' < '$version2' else 1)
" 2>/dev/null)
    
    if [ -n "$result" ]; then
        echo "$result"
        return
    fi
    
    # Fallback to sort if Python approach fails
    local sort_result=$(echo -e "${version1}\n${version2}" | sort -V | head -n1)
    if [ "$sort_result" = "$version1" ]; then
        # version1 is lower (older)
        echo -1
    else
        # version1 is higher (newer)
        echo 1
    fi
}

# Update the package
update_package() {
    local new_version="$1"
    local installed_with_pipx=false
    
    # Check if installed with pipx
    if command -v pipx &> /dev/null && pipx list | grep -q "simkl-mps"; then
        installed_with_pipx=true
        log_message "Package installed with pipx"
    else
        log_message "Package installed with pip or other method"
    fi
    
    # Stop all running instances of the app
    log_message "Stopping any running instances of simkl-mps..."
    if [[ "$OS" == "macos" ]]; then
        pkill -f "simkl-mps" || true
    else
        pkill -f "simkl-mps" || true
    fi
    sleep 1
    
    # Install update
    log_message "Installing update to version $new_version..."
    
    # Show notification
    show_notification "Updating..." "Installing simkl-mps version $new_version. Please wait..."
    
    local update_output=""
    local exit_code=1
    
    if [ "$installed_with_pipx" = true ]; then
        # Update with pipx
        log_message "Updating with pipx..."
        update_output=$(pipx upgrade --include-injected "simkl-mps[$PACKAGE_EXTRAS]" 2>&1)
        exit_code=$?
    else
        # Try with pip3 first, then pip as fallback
        if command -v pip3 &> /dev/null; then
            log_message "Updating with pip3..."
            if [[ "$OS" == "macos" ]]; then
                update_output=$(pip3 install --upgrade "simkl-mps[$PACKAGE_EXTRAS]" 2>&1)
            else
                update_output=$(pip3 install --upgrade --user "simkl-mps[$PACKAGE_EXTRAS]" 2>&1)
            fi
            exit_code=$?
        elif command -v pip &> /dev/null; then
            log_message "Updating with pip..."
            if [[ "$OS" == "macos" ]]; then
                update_output=$(pip install --upgrade "simkl-mps[$PACKAGE_EXTRAS]" 2>&1)
            else
                update_output=$(pip install --upgrade --user "simkl-mps[$PACKAGE_EXTRAS]" 2>&1)
            fi
            exit_code=$?
        else
            log_message "No pip or pipx command found"
            exit_code=1
        fi
    fi
    
    log_message "Update command output: $update_output"
    
    if [ $exit_code -eq 0 ]; then
        # Update was successful
        log_message "Update successful!"
        # Save the new version to version.txt
        echo "$new_version" > "${CONFIG_DIR}/version.txt"
        
        # Try to restart the application if it was running
        if [[ "$OS" == "macos" ]]; then
            # On macOS, check if simkl-mps is in Applications folder
            log_message "Attempting to restart application on macOS..."
            if [ -d "/Applications/MPS for SIMKL.app" ]; then
                open "/Applications/MPS for SIMKL.app"
                log_message "Restarted app from /Applications folder"
            elif [ -f "/usr/local/bin/simkl-mps" ]; then
                /usr/local/bin/simkl-mps &
                log_message "Restarted app using simkl-mps command"
            fi
        else
            # On Linux, try to start from command or .desktop file
            log_message "Attempting to restart application on Linux..."
            if command -v simkl-mps &> /dev/null; then
                nohup simkl-mps > /dev/null 2>&1 &
                log_message "Restarted app using simkl-mps command"
            fi
        fi
        
        show_notification "Update Complete" "Media Player Scrobbler for SIMKL has been updated to version $new_version."
        return 0
    else
        # Update failed
        log_message "Update failed with exit code $exit_code"
        show_notification "Update Failed" "Failed to update to version $new_version. Please check the logs or try updating manually."
        return 1
    fi
}

# Function to ask for user confirmation
ask_for_confirmation() {
    local installed_version="$1"
    local latest_version="$2"
    
    if [[ "$OS" == "macos" ]]; then
        # macOS dialog
        local response=$(osascript -e "display dialog \"A new version of Media Player Scrobbler for SIMKL is available.

Current version: $installed_version
New version: $latest_version

Do you want to update now?\" buttons {\"Later\", \"Update Now\"} default button \"Update Now\"")
        
        if [[ "$response" == *"Update Now"* ]]; then
            return 0  # User chose to update
        else
            return 1  # User chose not to update
        fi
    else
        # Linux dialog
        if command -v zenity &> /dev/null; then
            # Use zenity for GUI prompt
            zenity --question \
                --title="Update Available" \
                --text="A new version of Media Player Scrobbler for SIMKL is available.\n\nCurrent version: $installed_version\nNew version: $latest_version\n\nDo you want to update now?" \
                --no-wrap
            
            return $?  # zenity returns 0 for yes, 1 for no
        else
            # Use terminal prompt
            read -p "A new version of SIMKL-MPS is available ($latest_version). Update now? (y/N) " response
            case "$response" in
                [yY][eE][sS]|[yY]) 
                    return 0
                    ;;
                *)
                    return 1
                    ;;
            esac
        fi
    fi
}

# Main function to check for updates
check_for_updates() {
    log_message "Checking for updates to $PACKAGE_NAME..."
    
    # Get current installed version
    local installed_version=$(get_installed_version)
    log_message "Installed version: $installed_version"
    
    if [ -z "$installed_version" ]; then
        log_message "Error: Could not determine installed version"
        show_notification "Update Error" "Could not determine installed version"
        return 1
    fi
    
    # Get latest version from PyPI
    local latest_version=$(get_latest_version)
    log_message "Latest version: $latest_version"
    
    if [ -z "$latest_version" ]; then
        log_message "Error: Could not determine latest version from PyPI"
        if [ "$SILENT" != "true" ]; then
            show_notification "Update Error" "Could not check for updates. Please try again later."
        fi
        return 1
    fi
    
    # Compare versions
    local comparison=$(compare_versions "$latest_version" "$installed_version")
    
    if [ "$FORCE" = "true" ] || [ "$comparison" -gt 0 ]; then
        # Update available
        log_message "Update available: $installed_version -> $latest_version"
        
        if [ "$CHECK_ONLY" = "true" ]; then
            # Just notify about the update
            if [ "$SILENT" != "true" ]; then
                show_notification "Update Available" "Version $latest_version is available. Current version: $installed_version"
                echo "UPDATE_AVAILABLE: $latest_version https://pypi.org/project/simkl-mps/$latest_version/"
            fi
            return 0
        fi
        
        # Prompt user for confirmation if not silent
        if [ "$SILENT" != "true" ] && [ "$FORCE" != "true" ]; then
            log_message "Asking user for update confirmation..."
            
            if ask_for_confirmation "$installed_version" "$latest_version"; then
                update_package "$latest_version"
                return $?
            else
                log_message "Update cancelled by user"
                return 0
            fi
        elif [ "$FORCE" = "true" ] || [ "$SILENT" = "true" ]; then
            # Forced update or silent update (from script)
            update_package "$latest_version"
            return $?
        fi
    else
        # No update available
        log_message "No update available. Current version ($installed_version) is the latest."
        if [ "$SILENT" != "true" ] && [ "$CHECK_ONLY" = "true" ]; then
            show_notification "No Updates Available" "You are already running the latest version ($installed_version)."
            echo "NO_UPDATE: $installed_version"
        fi
        return 0
    fi
}

# Check dependencies
if ! command -v python3 &> /dev/null; then
    log_message "Error: python3 is not installed"
    show_notification "Update Error" "Python 3 is required but not installed"
    exit 1
fi

# Run the update check
check_for_updates
exit_code=$?
log_message "Update check completed with exit code $exit_code"
exit $exit_code
