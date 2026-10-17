; Instalador do Lunix Download Manager (Inno Setup 6).
; ISCC /DAppVersion=1.4.0 /DDistDir=...\windows\build\dist\LDM /DOutDir=...\windows\build\out /DIconFile=...\ldm.ico ldm.iss
#define AppName "Lunix Download Manager"

[Setup]
AppId={{8C2F3B5E-6A47-4C1E-9D3B-2B7A5E1F0C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=João Carlos
AppPublisherURL=https://github.com/jcrodriguesjr0/linux-download-manager
AppSupportURL=https://github.com/jcrodriguesjr0/linux-download-manager/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; instala sem pedir administrador (em %LOCALAPPDATA%\Programs); o usuário pode escolher "para todos"
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename=Lunix_Download_Manager-{#AppVersion}-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\LDM.exe
LicenseFile={#DistDir}\LICENSE.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Iniciar com o Windows (minimizado na bandeja)"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\LDM.exe"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\LDM.exe"; Tasks: desktopicon

[Registry]
; mesma chave e formato que o LDM usa em Opções > "Iniciar automaticamente"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "LDM"; ValueData: """{app}\LDM.exe"" --tray"; Tasks: autostart
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "LDM"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\LDM.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
