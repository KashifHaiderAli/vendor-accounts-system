; Inno Setup script for Vendor Accounts Web App - Local Version
; Build output: VendorAccountsWebApp_Local_Setup.exe

#define MyAppName "Vendor Accounts Web App - Local Version"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Vendor Accounts"
#define MyAppExeName "start_local_web.bat"

[Setup]
AppId={{4F3DBE60-0C64-4946-BE9D-60A79E96D3E0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\VendorAccounts\LocalVersion
DisableDirPage=no
DefaultGroupName=Vendor Accounts\Local Version
OutputDir=.
OutputBaseFilename=VendorAccountsWebApp_Local_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Dirs]
Name: "C:\VendorAccounts\LocalVersion\data"
Name: "C:\VendorAccounts\LocalVersion\backups"
Name: "C:\VendorAccounts\LocalVersion\logs"
Name: "C:\VendorAccounts\LocalVersion\runtime"

[Files]
Source: "package\LocalVersion\web_app\*"; DestDir: "C:\VendorAccounts\LocalVersion\web_app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "package\LocalVersion\runtime\python\*"; DestDir: "C:\VendorAccounts\LocalVersion\runtime\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "package\LocalVersion\start_local_web.bat"; DestDir: "C:\VendorAccounts\LocalVersion"; Flags: ignoreversion
Source: "package\LocalVersion\open_firewall_port_8001.bat"; DestDir: "C:\VendorAccounts\LocalVersion"; Flags: ignoreversion
Source: "package\LocalVersion\test_installed_local_web.bat"; DestDir: "C:\VendorAccounts\LocalVersion"; Flags: ignoreversion

[Icons]
Name: "{group}\Start Vendor Accounts Web App - Local Version"; Filename: "C:\VendorAccounts\LocalVersion\start_local_web.bat"; WorkingDir: "C:\VendorAccounts\LocalVersion\web_app"
Name: "{group}\Open Firewall Port 8001"; Filename: "C:\VendorAccounts\LocalVersion\open_firewall_port_8001.bat"; WorkingDir: "C:\VendorAccounts\LocalVersion"
Name: "{group}\Test Installed Local Web App"; Filename: "C:\VendorAccounts\LocalVersion\test_installed_local_web.bat"; WorkingDir: "C:\VendorAccounts\LocalVersion\web_app"
Name: "{commondesktop}\Start Vendor Accounts Web App - Local Version"; Filename: "C:\VendorAccounts\LocalVersion\start_local_web.bat"; WorkingDir: "C:\VendorAccounts\LocalVersion\web_app"
Name: "{commondesktop}\Test Installed Local Web App"; Filename: "C:\VendorAccounts\LocalVersion\test_installed_local_web.bat"; WorkingDir: "C:\VendorAccounts\LocalVersion\web_app"

[Run]
Filename: "C:\VendorAccounts\LocalVersion\open_firewall_port_8001.bat"; Description: "Open Windows Firewall port 8001"; Flags: postinstall skipifsilent
