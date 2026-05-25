; Inno Setup script for Vendor Accounts Web App - Main Version
; Build output: VendorAccountsWebApp_Main_Setup.exe

#define MyAppName "Vendor Accounts Web App - Main Version"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Vendor Accounts"
#define MyAppExeName "start_main_web.bat"

[Setup]
AppId={{F64A987B-151A-4D21-A118-6E19D86910F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\VendorAccounts\MainVersion
DisableDirPage=no
DefaultGroupName=Vendor Accounts\Main Version
OutputDir=.
OutputBaseFilename=VendorAccountsWebApp_Main_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Dirs]
Name: "C:\VendorAccounts\MainVersion\data"
Name: "C:\VendorAccounts\MainVersion\backups"
Name: "C:\VendorAccounts\MainVersion\logs"
Name: "C:\VendorAccounts\MainVersion\runtime"

[Files]
Source: "package\MainVersion\web_app\*"; DestDir: "C:\VendorAccounts\MainVersion\web_app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "package\MainVersion\runtime\python\*"; DestDir: "C:\VendorAccounts\MainVersion\runtime\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "package\MainVersion\start_main_web.bat"; DestDir: "C:\VendorAccounts\MainVersion"; Flags: ignoreversion
Source: "package\MainVersion\open_firewall_port_8000.bat"; DestDir: "C:\VendorAccounts\MainVersion"; Flags: ignoreversion
Source: "package\MainVersion\test_installed_main_web.bat"; DestDir: "C:\VendorAccounts\MainVersion"; Flags: ignoreversion

[Icons]
Name: "{group}\Start Vendor Accounts Web App - Main Version"; Filename: "C:\VendorAccounts\MainVersion\start_main_web.bat"; WorkingDir: "C:\VendorAccounts\MainVersion\web_app"
Name: "{group}\Open Firewall Port 8000"; Filename: "C:\VendorAccounts\MainVersion\open_firewall_port_8000.bat"; WorkingDir: "C:\VendorAccounts\MainVersion"
Name: "{group}\Test Installed Main Web App"; Filename: "C:\VendorAccounts\MainVersion\test_installed_main_web.bat"; WorkingDir: "C:\VendorAccounts\MainVersion\web_app"
Name: "{commondesktop}\Start Vendor Accounts Web App - Main Version"; Filename: "C:\VendorAccounts\MainVersion\start_main_web.bat"; WorkingDir: "C:\VendorAccounts\MainVersion\web_app"
Name: "{commondesktop}\Test Installed Main Web App"; Filename: "C:\VendorAccounts\MainVersion\test_installed_main_web.bat"; WorkingDir: "C:\VendorAccounts\MainVersion\web_app"

[Run]
Filename: "C:\VendorAccounts\MainVersion\open_firewall_port_8000.bat"; Description: "Open Windows Firewall port 8000"; Flags: postinstall skipifsilent
