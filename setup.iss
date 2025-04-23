#define MyAppName "Media Player Scrobbler for SIMKL"
#define MyAppPublisher "kavinthangavel"
#define MyAppURL "https://github.com/kavinthangavel/simkl-movie-tracker"
#define MyAppExeName "MPSS"
#define MyAppTrayName "MPS for Simkl"
#define MyAppVersion "1.0.0"
#define MyAppDescription "Automatically track and scrobble media you watch to SIMKL"
#define MyAppCopyright "Copyright (C) 2025 kavinthangavel"
#define MyAppUpdateURL "https://github.com/kavinthangavel/simkl-movie-tracker/releases"
#define MyAppReadmeURL "https://github.com/kavinthangavel/simkl-movie-tracker#readme"
#define MyAppIssuesURL "https://github.com/kavinthangavel/simkl-movie-tracker/issues"

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
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Privilege level settings - allow user to choose
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
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
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Modern UI
WizardStyle=modern
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

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}";
Name: "startupicon"; Description: "Start {#MyAppName} when Windows starts"; GroupDescription: "Windows Startup"
Name: "scheduledupdate"; Description: "Schedule weekly update checks (recommended)"; GroupDescription: "Update Settings";

[Files]
; Main executable
Source: "dist\MPSS.exe"; DestDir: "{app}"; Flags: ignoreversion signonce
; Tray executable
Source: "dist\MPS for Simkl.exe"; DestDir: "{app}"; Flags: ignoreversion signonce
; All other files (DLLs, data, etc.)
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Include updater script directly
Source: "simkl_mps\utils\updater.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu entries
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Start Media Scrobbler"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"
Name: "{group}\{cm:ProgramOnTheWeb,{#MyAppName}}"; Filename: "{#MyAppURL}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop icons (optional based on tasks)
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Check: IsAdminInstallMode
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Check: not IsAdminInstallMode

; Startup entry (optional based on tasks)
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Tasks: startupicon; Check: not IsAdminInstallMode

[Run]
; Options to run after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Start Media Scrobbler"; Parameters: "start"; Flags: nowait postinstall skipifsilent runascurrentuser
Filename: "{#MyAppURL}"; Description: "Visit the project website"; Flags: postinstall shellexec skipifsilent  

[UninstallRun]
; Stop any running processes before uninstall
Filename: "taskkill.exe"; Parameters: "/F /IM ""{#MyAppExeName}"" /T"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillMain"
Filename: "taskkill.exe"; Parameters: "/F /IM ""{#MyAppTrayName}"" /T"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillTray"

[Registry]
; Custom app registration (for uninstall)
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"; Flags: uninsdeletekey; Check: IsAdminInstallMode
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "URLInfoAbout"; ValueData: "{#MyAppURL}"; Flags: uninsdeletekey; Check: IsAdminInstallMode

; User installation registry entries (non-admin installations)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "URLInfoAbout"; ValueData: "{#MyAppURL}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode

; Auto-update settings
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode

; Add to Apps & Features list for non-admin installs (Windows 10+)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Flags: uninsdeletekey; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{3FF84A4E-B9C2-4F49-A8DE-5F7EA15F5D88}_is1"; ValueType: dword; ValueName: "EstimatedSize"; ValueData: "50000"; Flags: uninsdeletekey; Check: not IsAdminInstallMode

[Code]
const
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

// Called after files are copied
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('scheduledupdate') then
      CreateUpdateScheduledTask();
  end;
end;

// Called when uninstalling
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RemoveUpdateScheduledTask();
    if SuppressibleMsgBox('Do you want to remove all user settings?', mbConfirmation, MB_YESNO, IDNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\' + CONFIG_FOLDER), True, True, True);
  end;
end;