#define RootDir ".."

[Setup]
AppId={{1F5E73A8-AF4B-4AF2-8549-29FA7E1794D1}
AppName=CCFII Display Share
AppVersion=1.0.0
AppPublisher=Christ Charismatic Fellowship Int'l, Inc.
DefaultDirName={autopf}\CCFII Display Share
DefaultGroupName=CCFII Display Share
OutputBaseFilename=CCFIIDisplayShareInstaller
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#RootDir}\assets\ccfii-logo.ico
UninstallDisplayIcon={app}\CCFIIDisplayShare.exe

[Files]
Source: "{#RootDir}\dist\CCFIIDisplayShare\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CCFII Display Share"; Filename: "{app}\CCFIIDisplayShare.exe"
Name: "{autodesktop}\CCFII Display Share"; Filename: "{app}\CCFIIDisplayShare.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\CCFIIDisplayShare.exe"; Description: "Launch CCFII Display Share"; Flags: nowait postinstall skipifsilent
