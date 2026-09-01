#define MyAppName "Winget Universal Dashboard"
#define MyAppExeName "WingetUniversalDashboard.exe"
#define MyCliExeName "WingetUniversalDashboardCLI.exe"
#define MyPublisher "CyberIncome"
#define MyURL "https://github.com/CyberIncome/winget-app"

#ifndef AppVersion
  #error AppVersion must be supplied by scripts/build_installer.py
#endif

#ifndef AppVersionNumeric
  #error AppVersionNumeric must be supplied by scripts/build_installer.py
#endif

[Setup]
AppId={{C41A014A-142E-43E7-AB8F-07AC4479E07F}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#MyPublisher}
AppPublisherURL={#MyURL}
AppSupportURL={#MyURL}/issues
AppUpdatesURL={#MyURL}/releases/latest
VersionInfoVersion={#AppVersionNumeric}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyPublisher}
VersionInfoDescription={#MyAppName} Windows x64 installer
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
DefaultDirName={localappdata}\Programs\WingetUniversalDashboard
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=WingetUniversalDashboard-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
ChangesEnvironment=no
ChangesAssociations=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\{#MyCliExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Check: not WizardNoIcons
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
