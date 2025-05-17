#define MyAppName "Media Player Scrobbler for SIMKL"
#define MyAppShortName "MPS for SIMKL"
#define MyAppPublisher "kavinthangavel"
#define MyAppURL "https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl"
#define MyAppExeName "MPSS"
#define MyAppTrayName "MPS for Simkl"
#define MyAppVersion "2.1.2"
#define MyAppDescription "Automatically track and scrobble media you watch to SIMKL"
#define MyAppCopyright "Copyright (C) 2025 kavinthangavel"
#define MyAppUpdateURL "https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/releases"
#define MyAppReadmeURL "https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl#readme"
#define MyAppIssuesURL "https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/issues"
#define MyLicense "GNU GPL v3"

[Setup]
AppId={{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppIssuesURL}
AppUpdatesURL={#MyAppUpdateURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppShortName}
AllowNoIcons=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\installer
OutputBaseFilename=MPSS_Setup_{#MyAppVersion}
SetupIconFile=simkl_mps\assets\simkl-mps.ico
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}.exe
UninstallDisplayName={#MyAppName}
WizardStyle=modern
MinVersion=10.0.17763
AppCopyright={#MyAppCopyright}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppDescription}
VersionInfoCopyright={#MyAppCopyright}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
AppContact={#MyAppIssuesURL}
LicenseFile=LICENSE
SetupMutex={#MyAppName}Setup
AlwaysRestart=no
RestartIfNeededByRun=yes
DisableDirPage=auto
DisableProgramGroupPage=auto
UsedUserAreasWarning=no
CreateUninstallRegKey=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to the [name] Setup Wizard
WelcomeLabel2=This will install [name/ver] on your computer.%n%nMedia Player Scrobbler for SIMKL automatically tracks what you watch in your media players and updates your SIMKL.com account.%n%nIt is recommended that you close all other applications before continuing.
FinishedHeadingLabel=Completing the [name] Setup Wizard
FinishedLabel=Setup has finished installing [name] on your computer. The application may be launched by selecting the installed shortcuts.
AboutSetupMenuItem=About [name]...
AboutSetupTitle=About [name]
AboutSetupMessage=[name] version [ver]%n[name] Media Player Scrobbler for SIMKL%n%nLicense: {#MyLicense}%n%nCopyright © kavinthangavel%n{#MyAppURL}

[CustomMessages]
LaunchAppDesc=Start MPS for SIMKL after installation
DesktopIconDesc=Create a desktop shortcut
StartupIconDesc=Start automatically when Windows starts
UpdateDesc=Schedule weekly update checks (recommended)
AboutApp=About Media Player Scrobbler for SIMKL
VersionInfo=Version: {#MyAppVersion}
LicenseInfo=License: {#MyLicense}

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIconDesc}"; GroupDescription: "Shortcuts:"
Name: "startupicon"; Description: "{cm:StartupIconDesc}"; GroupDescription: "Startup options:"
Name: "scheduledupdate"; Description: "{cm:UpdateDesc}"; GroupDescription: "Update options:"

[Files]
; Main executable
Source: "dist\MPSS.exe"; DestDir: "{app}"; Flags: ignoreversion signonce
; Tray executable
Source: "dist\MPS for Simkl.exe"; DestDir: "{app}"; Flags: ignoreversion signonce
; All other files (DLLs, data, etc.)
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Include updater script directly
Source: "simkl_mps\utils\updater.ps1"; DestDir: "{app}"; Flags: ignoreversion
; Create version file to help with About dialog
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu entries - simplified to just have "Start Scrobbler"
Name: "{group}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Comment: "Start SIMKL scrobbler in the background"; AppUserModelID: "kavinthangavel.simkl-mps"
Name: "{group}\{cm:UninstallProgram,{#MyAppShortName}}"; Filename: "{uninstallexe}"

; Desktop icon - simplified to just one "Start Scrobbler" icon
Name: "{commondesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Tasks: desktopicon; Check: IsAdminInstallMode; Comment: "Start SIMKL scrobbler in the background"; AppUserModelID: "kavinthangavel.simkl-mps"
Name: "{userdesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Tasks: desktopicon; Check: not IsAdminInstallMode; Comment: "Start SIMKL scrobbler in the background"; AppUserModelID: "kavinthangavel.simkl-mps"

; Startup entry - renamed to "MPS for Simkl.exe" with specific icon
Name: "{userstartup}\{#MyAppShortName}"; Filename: "{app}\{#MyAppTrayName}"; Parameters: "start"; IconFilename: "{app}\{#MyAppTrayName}"; Tasks: startupicon; Check: not IsAdminInstallMode; Comment: "Start SIMKL scrobbler in the background"
Name: "{commonstartup}\{#MyAppShortName}"; Filename: "{app}\{#MyAppTrayName}"; Parameters: "start"; IconFilename: "{app}\{#MyAppTrayName}"; Tasks: startupicon; Check: IsAdminInstallMode; Comment: "Start SIMKL scrobbler in the background"

[Run]
; Options to run after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchAppDesc}"; Parameters: "start"; Flags: nowait postinstall skipifsilent runascurrentuser
Filename: "{#MyAppURL}"; Description: "Visit website"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallRun]
; Improved process termination for uninstallation
; First try to gracefully close the app
Filename: "{app}\{#MyAppExeName}.exe"; Parameters: "exit"; Flags: runhidden skipifdoesntexist; RunOnceId: "GracefulExit"
; Wait a moment before forcefully terminating
Filename: "{sys}\cmd.exe"; Parameters: "/c timeout /t 2 /nobreak > nul"; Flags: runhidden; RunOnceId: "WaitForExit"
; Forcefully terminate any remaining processes
Filename: "taskkill.exe"; Parameters: "/F /IM ""{#MyAppExeName}.exe"" /T"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillMainApp"
Filename: "taskkill.exe"; Parameters: "/F /IM ""MPS for Simkl.exe"" /T"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillTrayApp"

[Registry]
; Create a version information file for the about dialog
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "License"; ValueData: "{#MyLicense}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: dword; ValueName: "CheckUpdates"; ValueData: "1"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: dword; ValueName: "FirstRun"; ValueData: "0"; Flags: uninsdeletekey

; Admin installation - HKLM registry keys only for admin installs
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey; Check: IsAdminInstallMode

[InstallDelete]
; Make sure we delete any existing files to prevent conflicts - only if we're updating
Type: filesandordirs; Name: "{app}\*.dll"; Check: not IsFirstInstall
Type: filesandordirs; Name: "{app}\*.pyd"; Check: not IsFirstInstall

[Code]
const
  MyAppIdGuid = '{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}'; // Define the AppId GUID as a script constant
  CONFIG_FOLDER = 'simkl-mps';
  TASK_NAME = 'kavinthangavel.MediaPlayerScrobblerForSIMKL.UpdateCheck';

// Check if the app is currently running
function IsAppRunning: Boolean;
var
  ResultCode: Integer;
  AttemptsMade: Integer;
  ProcessesClosed: Boolean;
  WindowsProcKill: Boolean;
begin
  Result := False;
  ProcessesClosed := False;
  
  // Try to gently terminate the app first - but only if we're updating
  // (not during first installation where {app} isn't available yet)
  Log('Checking for running instances...');
  
  // Check if processes are running regardless of installation status
  AttemptsMade := 0;
  while (AttemptsMade < 3) and (not ProcessesClosed) do
  begin
    AttemptsMade := AttemptsMade + 1;
    Log('Process termination attempt #' + IntToStr(AttemptsMade));
    
    // Kill both executables with force
    WindowsProcKill := Exec('taskkill.exe', '/F /IM "{#MyAppExeName}.exe" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Log('taskkill for {#MyAppExeName}.exe result: ' + IntToStr(ResultCode));
    
    WindowsProcKill := Exec('taskkill.exe', '/F /IM "{#MyAppTrayName}.exe" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Log('taskkill for {#MyAppTrayName}.exe result: ' + IntToStr(ResultCode));
    
    // Extra aggressive kill for any remaining app processes
    Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "Get-Process -Name "{#MyAppExeName}","MPS for Simkl" -ErrorAction SilentlyContinue | Stop-Process -Force"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    
    // Wait between attempts
    Sleep(1000);
    
    // Check if processes are still running
    ProcessesClosed := True; // Assume success unless proven otherwise
    Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "$p = Get-Process -Name "{#MyAppExeName}","MPS for Simkl" -ErrorAction SilentlyContinue; if($p) { exit 1 } else { exit 0 }"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
    begin
      ProcessesClosed := False;
      Log('Processes still running after attempt #' + IntToStr(AttemptsMade));
    end;
  end;
  
  // Final check - return true if we believe processes are still running
  if not ProcessesClosed then
  begin
    Log('WARNING: Could not terminate all instances after multiple attempts!');
    Result := True;
  end else
    Log('Successfully terminated all app instances or none were running');
  
  // The function will automatically return the value of Result
end;

// Check if this is a first-time installation
function IsFirstInstall: Boolean;
begin
  Result := not RegKeyExists(HKEY_LOCAL_MACHINE, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1') and
           not RegKeyExists(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1');
end;

// Initialization function for setup
function InitializeSetup: Boolean;
begin
  // Check if app is running and terminate it before setup begins
  IsAppRunning();
  Result := True;
end;

// Create the scheduled task for updates (optional, only if user selects the task)
function CreateUpdateScheduledTask: Boolean;
var
  TaskName, AppPath, PowerShellPath, Params: String;
  ResultCode: Integer;
begin
  Result := False;
  TaskName := TASK_NAME;
  AppPath := ExpandConstant('{app}\updater.ps1');
  PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');

  // Updated parameters for silent operation (no -CheckOnly since the new script handles notifications)
  Params := '-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File "' + AppPath + '"';
  
  try
    // First delete any existing task with the same name to avoid duplicates
    Exec('schtasks.exe', '/Delete /TN "' + TaskName + '" /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    
    // Create a weekly task that runs every Saturday at 12:00
    if Exec('schtasks.exe',
      '/Create /TN "' + TaskName + '" /TR "\"' + PowerShellPath + '\" ' + Params + '" /SC WEEKLY /D SAT /ST 12:00 /F',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Result := True;
  except
    // ignore errors
  end;
end;

// Remove the scheduled task
function RemoveUpdateScheduledTask: Boolean;
var
  TaskName: String;
  ResultCode: Integer;
begin
  Result := False;
  TaskName := TASK_NAME;
  try
    if Exec('schtasks.exe', '/Delete /TN "' + TaskName + '" /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Result := True;
  except
    // ignore errors
  end;
end;

// Create a version file with info for the app to use
procedure CreateVersionFile;
var
  VersionFilePath: String;
  VersionContents: String;
begin
  VersionFilePath := ExpandConstant('{app}\version.txt');
  VersionContents := '{#MyAppVersion}';
  
  if not SaveStringToFile(VersionFilePath, VersionContents, False) then
    Log('Failed to create version.txt file');
end;

// Called after files are copied
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create version file
    CreateVersionFile();
    
    // Create scheduled task if selected
    if WizardIsTaskSelected('scheduledupdate') then
      CreateUpdateScheduledTask();
  end;
end;

// Enhanced cleanup during uninstallation
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigDirs: array of String;
  i: Integer;
  CleanupAll: Boolean;
  UserProfileDir, AppDataDir, LocalAppDataDir: String;
begin
  // Remove scheduled task as early as possible
  if CurUninstallStep = usUninstall then
    RemoveUpdateScheduledTask();
    
  if CurUninstallStep = usPostUninstall then
  begin
    // Ask user about data removal
    CleanupAll := SuppressibleMsgBox('Do you want to remove all user settings, logs, and application data?', 
                                     mbConfirmation, MB_YESNO, IDNO) = IDYES;
    
    if CleanupAll then
    begin
      // Get reliable paths for Windows environment folders
      UserProfileDir := GetEnv('USERPROFILE');
      AppDataDir := GetEnv('APPDATA');
      LocalAppDataDir := GetEnv('LOCALAPPDATA');
      
      // All possible config directories to check and remove - Windows specific
      SetArrayLength(ConfigDirs, 6);
      
      // Primary location: C:\Users\username\kavinthangavel\simkl-mps
      ConfigDirs[0] := UserProfileDir + '\kavinthangavel\' + CONFIG_FOLDER;
      
      // Other possible locations - using environment variables instead of constants
      ConfigDirs[1] := LocalAppDataDir + '\' + CONFIG_FOLDER;
      ConfigDirs[2] := AppDataDir + '\' + CONFIG_FOLDER;
      ConfigDirs[3] := UserProfileDir + '\' + CONFIG_FOLDER; 
      ConfigDirs[4] := UserProfileDir + '\AppData\Local\' + CONFIG_FOLDER;
      ConfigDirs[5] := UserProfileDir + '\Documents\' + CONFIG_FOLDER;
      
      // Loop through all possible locations and delete them if they exist
      for i := 0 to GetArrayLength(ConfigDirs) - 1 do
      begin
        if DirExists(ConfigDirs[i]) then
        begin
          Log('Deleting configuration directory: ' + ConfigDirs[i]);
          if not DelTree(ConfigDirs[i], True, True, True) then
          begin
            // Try CMD as fallback for difficult directories
            Exec('cmd.exe', '/c rd /s /q "' + ConfigDirs[i] + '"', '', SW_HIDE, ewWaitUntilTerminated, i);
          end;
        end;
      end;
      
      // Clean registry entries
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\{#MyAppPublisher}\{#MyAppName}');
      if IsAdminInstallMode then
        RegDeleteKeyIncludingSubkeys(HKLM, 'Software\{#MyAppPublisher}\{#MyAppName}');
    end;

    // Ensure Start Menu entries are removed
    DelTree(ExpandConstant('{group}'), True, True, True);
    
    // Ensure Desktop shortcuts are removed
    DeleteFile(ExpandConstant('{commondesktop}\{#MyAppShortName}.lnk'));
    DeleteFile(ExpandConstant('{userdesktop}\{#MyAppShortName}.lnk'));
    
    // Ensure Startup entries are removed
    DeleteFile(ExpandConstant('{commonstartup}\{#MyAppShortName}.lnk'));
    DeleteFile(ExpandConstant('{userstartup}\{#MyAppShortName}.lnk'));
  end;
end;

// Enhanced uninstall preparation
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  WindowsProcKill: Boolean;
  KillResult: String;
begin
  // Ensure all application processes are terminated before continuing
  
  // Try graceful exit first
  Exec(ExpandConstant('{app}\{#MyAppExeName}.exe'), 'exit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  // Wait briefly
  Sleep(1000);
  
  // Forceful termination of any remaining processes
  WindowsProcKill := Exec('taskkill.exe', '/F /IM "{#MyAppExeName}.exe" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if WindowsProcKill then
    KillResult := 'True'
  else
    KillResult := 'False';
  Log('Forcefully terminating MPSS.exe: ' + KillResult);
  
  // Also try to terminate the tray application
  WindowsProcKill := Exec('taskkill.exe', '/F /IM "MPS for Simkl.exe" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if WindowsProcKill then
    KillResult := 'True'
  else
    KillResult := 'False';
  Log('Forcefully terminating MPS for Simkl.exe: ' + KillResult);
  
  // Success - let uninstallation proceed
  Result := True;
end;