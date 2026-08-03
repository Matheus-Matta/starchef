#define AppName "StarChef PDV"
; AppVersion normalmente vem de fora (build_installer.ps1 lê o pubspec.yaml e
; passa /DAppVersion=X.Y.Z ao ISCC) — assim a versão só existe em um lugar.
; O default abaixo só é usado se o .iss for compilado direto, sem o script.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "StarChef"
#define AppExeName "starchef_pdv.exe"
#define SourceDir "..\..\build\windows\x64\runner\Release"

[Setup]
AppId={{E6A8B1AA-36BB-4C3C-A65A-86114B770C67}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\StarChef PDV
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\..\artifacts
OutputBaseFilename=starchef-pdv
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
