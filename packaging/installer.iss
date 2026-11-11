; Inno Setup script - build with:  ISCC.exe packaging\installer.iss
; Expects the PyInstaller output in dist\SizeSeekerWeb (run packaging\build.ps1).

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{6F1C9C1E-5B7A-4C2E-9E8D-53A1F0D2B7C4}
AppName=SizeSeekerWeb
AppVersion={#AppVersion}
AppVerName=SizeSeekerWeb {#AppVersion}
AppPublisher=Denis Maslov
AppPublisherURL=https://github.com/DenisMaslov02/SizeSeekerWeb
DefaultDirName={localappdata}\Programs\SizeSeekerWeb
DefaultGroupName=SizeSeekerWeb
DisableProgramGroupPage=yes
; Per-user install: no admin rights needed.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SizeSeekerWeb-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\SizeSeekerWeb.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
LicenseFile=..\LICENSE

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\SizeSeekerWeb\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SizeSeekerWeb"; Filename: "{app}\SizeSeekerWeb.exe"
Name: "{group}\{cm:UninstallProgram,SizeSeekerWeb}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SizeSeekerWeb"; Filename: "{app}\SizeSeekerWeb.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SizeSeekerWeb.exe"; Description: "{cm:LaunchProgram,SizeSeekerWeb}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Logs and the search index (it lists every file name of the PC, so do not leave it behind).
Type: filesandordirs; Name: "{localappdata}\SizeSeekerWeb"

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM SizeSeekerWeb.exe"; Flags: runhidden; RunOnceId: "StopSizeSeekerWeb"
