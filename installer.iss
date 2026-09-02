; ============================================================
; INNO SETUP SCRIPT - BACKGROUND REMOVER
; ============================================================
[Setup]
AppName=Background Remover
AppVersion=1.0.0
AppPublisher=DFiesta Software
AppPublisherURL=https://github.com/DFiesta/background_remover
DefaultDirName={autopf}\BackgroundRemover
DefaultGroupName=Background Remover
UninstallDisplayIcon={app}\app_icon.ico
SetupIconFile=assets\app_icon.ico
OutputDir=dist
OutputBaseFilename=BackgroundRemover_Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\BackgroundRemover.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprogramgroup}\Background Remover"; Filename: "{app}\BackgroundRemover.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{userdesktop}\Background Remover"; Filename: "{app}\BackgroundRemover.exe"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\BackgroundRemover.exe"; Description: "{cm:LaunchProgram,Background Remover}"; Flags: postinstall nowait skipifsilent
