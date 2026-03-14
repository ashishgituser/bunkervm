; ══════════════════════════════════════════════════════════
;  BunkerDesktop — Inno Setup Installer Script
;
;  Builds a professional Windows installer (.exe) that deploys:
;    - BunkerDesktop.exe (native pywebview app — no browser needed)
;    - WSL2 backend setup (Firecracker microVMs)
;    - Start Menu + Desktop shortcuts
;    - Add/Remove Programs registration
;
;  Prerequisites:
;    - Build BunkerDesktop.exe first:
;        cd desktop && pyinstaller BunkerDesktop.spec --noconfirm
;    - Then build the installer:
;        iscc installer\windows\BunkerDesktopSetup.iss
;
;  CI builds both automatically via .github/workflows/release.yml
; ══════════════════════════════════════════════════════════

#define MyAppName "BunkerDesktop"
; Version can be overridden via: iscc /DMyAppVersion="1.0.0" ...
#ifndef MyAppVersion
  #define MyAppVersion "0.8.1"
#endif
#define MyAppPublisher "BunkerVM"
#define MyAppURL "https://github.com/ashishgituser/bunkervm"
#define MyAppExeName "BunkerDesktop.exe"

[Setup]
AppId={{B4E5A7C2-9D31-4F8E-A2C1-6D7B3E9F0A12}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=Output
OutputBaseFilename=BunkerDesktopSetup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
; Signing: uncomment when you have a code signing certificate
; SignTool=signtool sign /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 $f

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Start BunkerVM engine on login"; GroupDescription: "Additional options:"
Name: "setupwsl"; Description: "Set up WSL2 and install BunkerVM backend (recommended)"; GroupDescription: "Backend setup:"; Flags: checkedonce

[Files]
; The native desktop app (PyInstaller single-file exe)
Source: "..\..\desktop\dist\BunkerDesktop.exe"; DestDir: "{app}"; Flags: ignoreversion
; Icon
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\assets\icon.ico'))
; WSL setup script (runs post-install to set up backend)
Source: "install-desktop.ps1"; DestDir: "{app}"; Flags: ignoreversion
; Uninstaller helper
Source: "uninstall-helper.ps1"; DestDir: "{app}"; Flags: ignoreversion
; License
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
; Python source (needed for WSL pip install — bunkervm is not on PyPI yet)
Source: "..\..\pyproject.toml"; DestDir: "{app}\src"; Flags: ignoreversion
Source: "..\..\bunkervm\*"; DestDir: "{app}\src\bunkervm"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc,*.pyo"
Source: "..\..\rootfs\*"; DestDir: "{app}\src\rootfs"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "Launch BunkerDesktop"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Desktop (use {userdesktop} not {commondesktop} — we run without admin)
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Comment: "Launch BunkerDesktop"; Tasks: desktopicon

[Registry]
; Add install dir to user PATH
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))
; Auto-start on login (if selected)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Post-install: run WSL setup if selected
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install-desktop.ps1"" -SkipReboot"; Description: "Set up WSL2 backend"; Flags: postinstall nowait skipifsilent; Tasks: setupwsl
; Launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Stop engine before uninstall
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Invoke-WebRequest -Uri http://localhost:9551/engine/stop -Method POST -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue"""; Flags: runhidden; RunOnceId: "StopEngine"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\dashboard"
Type: filesandordirs; Name: "{app}\src"
Type: filesandordirs; Name: "{app}\logs"

[Code]
// Check if we need to add to PATH
function NeedsAddPath(Param: string): Boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

// Warn if WSL is not available
procedure InitializeWizard;
var
  ResultCode: Integer;
begin
  if not Exec('wsl.exe', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('WSL2 does not appear to be installed.' + #13#10 + #13#10 +
           'BunkerDesktop requires WSL2 to run Firecracker microVMs.' + #13#10 +
           'The installer will attempt to set it up, but a reboot may be needed.',
           mbInformation, MB_OK);
  end;
end;

// Check if icon file exists (for conditional file copy)
function FileExists(Path: string): Boolean;
begin
  Result := FileOrDirExists(Path);
end;
