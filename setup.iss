#define MyAppName "Media Player Scrobbler for SIMKL"
#define MyAppShortName "MPS for SIMKL"
#define MyAppPublisher "kavinthangavel"
#define MyAppURL "https://github.com/kavinthangavel/simkl-movie-tracker"
#define MyAppExeName "MPSS"
#define MyAppTrayName "MPS for Simkl"
#define MyAppVersion "2.0.1"
#define MyAppDescription "Automatically track and scrobble media you watch to SIMKL"
#define MyAppCopyright "Copyright (C) 2025 kavinthangavel"
#define MyAppUpdateURL "https://github.com/kavinthangavel/simkl-movie-tracker/releases"
#define MyAppReadmeURL "https://github.com/kavinthangavel/simkl-movie-tracker#readme"
#define MyAppIssuesURL "https://github.com/kavinthangavel/simkl-movie-tracker/issues"
#define MyLicense "GNU GPL v3"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
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
; Privilege level settings - set to lowest for per-user installation 
; and allow the user to choose to run as admin if needed
PrivilegesRequired=lowest
; 64-bit only application
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Output settings
OutputDir=dist\installer
OutputBaseFilename=MPSS_Setup_{#MyAppVersion}
SetupIconFile=simkl_mps\assets\simkl-mps.ico
; Compression settings
Compression=lzma2/ultra64
SolidCompression=yes
; Uninstall settings
UninstallDisplayIcon={app}\{#MyAppExeName}.exe
UninstallDisplayName={#MyAppShortName}
; Modern UI settings
WizardStyle=modern
WizardResizable=yes
WizardSizePercent=120
; This adds Windows 10/11 compatibility settings
MinVersion=10.0.17763
; App metadata
AppCopyright={#MyAppCopyright}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppDescription}
VersionInfoCopyright={#MyAppCopyright}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
; Support info
AppContact={#MyAppIssuesURL}
; License and readme files
LicenseFile=LICENSE
SetupMutex={#MyAppName}Setup
AlwaysRestart=no
RestartIfNeededByRun=yes
DisableDirPage=auto
DisableProgramGroupPage=auto
UsedUserAreasWarning=no

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
Name: "{group}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Comment: "Start SIMKL scrobbler in the background"
Name: "{group}\{cm:UninstallProgram,{#MyAppShortName}}"; Filename: "{uninstallexe}"

; Desktop icon - simplified to just one "Start Scrobbler" icon
Name: "{commondesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Tasks: desktopicon; Check: IsAdminInstallMode; Comment: "Start SIMKL scrobbler in the background"
Name: "{userdesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Tasks: desktopicon; Check: not IsAdminInstallMode; Comment: "Start SIMKL scrobbler in the background"

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
Filename: "taskkill.exe"; Parameters: "/F /IM ""{#MyAppExeName}.exe"" /T"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillMain"
Filename: "taskkill.exe"; Parameters: "/F /IM ""MPS for Simkl.exe"" /T"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillTray"
; Add a Windows PowerShell command to find and kill all related processes - fix curly braces escaping
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-Process | Where-Object {{$_.Path -like '*{{app}}*'}} | Stop-Process -Force"""; Flags: runhidden skipifdoesntexist runascurrentuser; RunOnceId: "KillAllRelated"
; Final wait to ensure processes have terminated
Filename: "{sys}\cmd.exe"; Parameters: "/c timeout /t 1 /nobreak > nul"; Flags: runhidden; RunOnceId: "FinalWait"

[Registry]
; Create a version information file for the about dialog
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "License"; ValueData: "{#MyLicense}"; Flags: uninsdeletekey

; Custom app registration (for uninstall)
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppShortName}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "URLInfoAbout"; ValueData: "{#MyAppURL}"; Flags: uninsdeletekey; Check: IsAdminInstallMode

; Custom app registration for uninstall with explicit icon path
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "UninstallString"; ValueData: """{uninstallexe}"""; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}.exe"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppShortName}"; Flags: uninsdeletekey; Check: IsAdminInstallMode

; User installation registry entries (non-admin installations)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppShortName}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "URLInfoAbout"; ValueData: "{#MyAppURL}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode

; User installation registry entries with updated uninstaller name and icon
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "UninstallString"; ValueData: """{uninstallexe}"""; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}.exe"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppShortName}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode

; Auto-update settings
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: dword; ValueName: "CheckUpdates"; ValueData: "1"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey; Check: IsAdminInstallMode

; Add to Apps & Features list for non-admin installs (Windows 10+)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: dword; ValueName: "EstimatedSize"; ValueData: "50000"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
; Add registry value to track first run state - will be used by tray app
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: dword; ValueName: "FirstRun"; ValueData: "0"; Flags: uninsdeletekey

[Code]
const
  MyAppIdGuid = '{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}'; // Define the AppId GUID as a script constant
  CONFIG_FOLDER = 'simkl-mps';
  TASK_NAME = 'kavinthangavel.MediaPlayerScrobblerForSIMKL.UpdateCheck';

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
  Params := '-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File "' + AppPath + '" -Silent';
  try
    // First delete any existing task with the same name to avoid duplicates
    Exec('schtasks.exe', '/Delete /TN "' + TaskName + '" /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
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
  if CurUninstallStep = usPostUninstall then
  begin
    // Remove scheduled task
    RemoveUpdateScheduledTask();
    
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
      
      // Log what directories we're checking
      Log('Looking for configuration directories to clean up...');
      
      // Loop through all possible locations and delete them if they exist
      for i := 0 to GetArrayLength(ConfigDirs) - 1 do
      begin
        if DirExists(ConfigDirs[i]) then
        begin
          Log('Deleting configuration directory: ' + ConfigDirs[i]);
          if not DelTree(ConfigDirs[i], True, True, True) then
          begin
            Log('Failed to delete directory with DelTree: ' + ConfigDirs[i]);
            // Try CMD as fallback for difficult directories
            Exec('cmd.exe', '/c rd /s /q "' + ConfigDirs[i] + '"', '', SW_HIDE, ewWaitUntilTerminated, i);
          end;
        end else
          Log('Directory not found: ' + ConfigDirs[i]);
      end;
      
      // Also clean registry entries
      Log('Deleting application specific registry keys...');
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\{#MyAppPublisher}\{#MyAppName}');
      if IsAdminInstallMode then
        RegDeleteKeyIncludingSubkeys(HKLM, 'Software\{#MyAppPublisher}\{#MyAppName}');

      // Explicitly delete Uninstall registry keys for good measure
      Log('Deleting Uninstall registry keys...');
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + MyAppIdGuid + '_is1');
      if IsAdminInstallMode then
        RegDeleteKeyIncludingSubkeys(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + MyAppIdGuid + '_is1');
    end;

    // Attempt to remove the main application directory as a final step
    Log('Attempting to remove application directory: ' + ExpandConstant('{app}'));
    if not DelTree(ExpandConstant('{app}'), True, True, True) then
    begin
      Log('Failed to remove application directory with DelTree: ' + ExpandConstant('{app}'));
    end;
  end;
end;

// Enhanced uninstall preparation
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  ProcessName: string;
begin
  // Ensure all application processes are terminated before continuing
  ProcessName := ExtractFileName(ExpandConstant('{app}\{#MyAppExeName}.exe'));
  
  // Try graceful exit first
  Exec(ExpandConstant('{app}\{#MyAppExeName}.exe'), 'exit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  // Wait briefly
  Sleep(1000);
  
  // Forceful termination of any remaining processes
  Exec('taskkill.exe', '/F /IM "' + ProcessName + '" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  
  // Also try to terminate the tray application
  Exec('taskkill.exe', '/F /IM "MPS for Simkl.exe" /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  
  // Success - let uninstallation proceed
  Result := True;
end;