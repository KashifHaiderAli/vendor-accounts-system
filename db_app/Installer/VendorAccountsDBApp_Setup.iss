#define MyAppName "Vendor Accounts DB App"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "BH Tech Solutions"
#define MyAppExeName "VendorAccountsDBApp.exe"

[Setup]
AppId={{A8D7A18D-3B6D-4D5B-B39A-7F36FBEA9142}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Vendor Accounts DB App
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=VendorAccountsDBApp_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\VendorAccountsDBApp.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\backups"
Name: "{app}\logs"

[Icons]
Name: "{group}\Vendor Accounts DB App"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Vendor Accounts DB App"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Vendor Accounts DB App"; Flags: nowait postinstall skipifsilent