#ifndef BuildRoot
  #define BuildRoot "..\\.build\\desktop\\dist"
#endif
#ifndef OutputRoot
  #define OutputRoot "..\\.build\\desktop\\installers"
#endif
[Setup]
AppId={{6B98AB20-53D3-46E8-A737-79533EF542AD}
AppName=Block Archive
AppVersion=1.0.0
AppPublisher=Block Archive contributors
AppPublisherURL=https://github.com/noordenbos/block-archive
DefaultDirName={localappdata}\Programs\Block Archive
DefaultGroupName=Block Archive
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputRoot}
OutputBaseFilename=BlockArchive-1.0.0-preview.1-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\BlockArchive.exe
CloseApplications=yes
[Files]
Source: "{#BuildRoot}\BlockArchive\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Block Archive"; Filename: "{app}\BlockArchive.exe"
Name: "{autodesktop}\Block Archive"; Filename: "{app}\BlockArchive.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\BlockArchive.exe"; Description: "Open Block Archive"; Flags: nowait postinstall skipifsilent
; User archives live outside {app} and are never removed by the uninstaller.
