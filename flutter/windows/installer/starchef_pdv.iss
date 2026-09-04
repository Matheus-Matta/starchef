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
OutputBaseFilename=StarChef-PDV-Setup-{#AppVersion}
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
; Sem esta regra o Windows bloqueia a porta do Caixa Principal e os outros
; aparelhos (caixas secundários e app do garçom) não conectam. Pede elevação
; só neste passo — o instalador em si continua sem exigir administrador.
Name: "firewall"; Description: "Liberar o Caixa Principal no Firewall do Windows (recomendado)"; GroupDescription: "Rede local:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Vai junto mesmo quando a tarefa é desmarcada: quem pular na instalação (ou
; mudar a porta depois) precisa conseguir rodar o script sozinho.
Source: "liberar_firewall.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Liberar Caixa Principal no Firewall"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\liberar_firewall.ps1"""; Comment: "Reabre a porta do Caixa Principal no Firewall do Windows"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\liberar_firewall.ps1"" -NoPause"; StatusMsg: "Liberando o Caixa Principal no firewall..."; Flags: runhidden waituntilterminated; Tasks: firewall
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Mesma chave de desinstalação que o Inno usa pra esse AppId (com o mesmo
// GUID em [Setup], sempre resolve pra cá — é assim que identificamos uma
// instalação anterior, mesma lógica que alimenta UsePreviousAppDir).
const
  UninstallSubkey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E6A8B1AA-36BB-4C3C-A65A-86114B770C67}_is1';

function GetInstalledVersion(): String;
var
  version: String;
begin
  if not RegQueryStringValue(HKCU, UninstallSubkey, 'DisplayVersion', version) then
    if not RegQueryStringValue(HKLM, UninstallSubkey, 'DisplayVersion', version) then
      version := '';
  Result := version;
end;

// Compara "X.Y.Z" puro (sem sufixo de pre-release) segmento a segmento como
// inteiro -- comparacao de string pura erraria "1.0.10" < "1.0.9".
function CompareVersions(V1, V2: String): Integer;
var
  dot1, dot2: Integer;
  seg1, seg2: String;
  n1, n2: Integer;
begin
  Result := 0;
  while (V1 <> '') or (V2 <> '') do
  begin
    dot1 := Pos('.', V1);
    if dot1 = 0 then begin seg1 := V1; V1 := ''; end
    else begin seg1 := Copy(V1, 1, dot1 - 1); V1 := Copy(V1, dot1 + 1, Length(V1)); end;

    dot2 := Pos('.', V2);
    if dot2 = 0 then begin seg2 := V2; V2 := ''; end
    else begin seg2 := Copy(V2, 1, dot2 - 1); V2 := Copy(V2, dot2 + 1, Length(V2)); end;

    n1 := StrToIntDef(seg1, 0);
    n2 := StrToIntDef(seg2, 0);
    if n1 > n2 then begin Result := 1; Exit; end;
    if n1 < n2 then begin Result := -1; Exit; end;
  end;
end;

// Identifica uma instalação já existente (mesmo AppId) e só deixa seguir se
// essa versão for mais nova — instalador desatualizado nunca sobrescreve uma
// instalação mais recente, e reinstalar a mesma versão vira um no-op avisado.
function InitializeSetup(): Boolean;
var
  installedVersion: String;
begin
  Result := True;
  installedVersion := GetInstalledVersion();
  if (installedVersion <> '') and (CompareVersions(installedVersion, '{#AppVersion}') >= 0) then
  begin
    MsgBox(
      'O StarChef PDV ' + installedVersion + ' já está instalado neste computador.' + #13#10 +
      'Este instalador é da versão {#AppVersion}, que não é mais recente — nada será alterado.',
      mbInformation, MB_OK);
    Result := False;
  end;
end;
