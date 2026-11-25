; Script Inno Setup para o Registrale-DOU
; Compilado por windows/build.ps1 via ISCC.exe /DAppVersion=x.y.z

#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

#ifndef StageDir
  #define StageDir "..\build\stage"
#endif

#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

#define AppName "Registrale-DOU"
#define AppPublisher "Registrale"
#define AppURL "https://github.com/Yaddz/Registrale-dou"

[Setup]
; Avisa o Explorer (SHChangeNotify) ao terminar, para atualizar ícones de atalhos já existentes.
ChangesAssociations=yes
AppId={{8F6D54A2-7B9E-4C13-9A41-2C6E7B5D1F08}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\Registrale
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=Registrale-Setup-{#AppVersion}
SetupIconFile=registrale.ico
UninstallDisplayIcon={app}\app\windows\registrale.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
; Robô da marca no canto do assistente (gerado por make_icon.py)
WizardSmallImageFile=wizard-small-55.bmp,wizard-small-110.bmp
CloseApplications=yes
CloseApplicationsFilter=python.exe,pythonw.exe,pg_ctl.exe,postgres.exe
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos e inicialização:"
Name: "startupicon"; Description: "Iniciar automaticamente com o Windows"; GroupDescription: "Atalhos e inicialização:"

[InstallDelete]
; Atualização limpa: remove o programa da versão anterior antes de copiar o novo,
; para não sobrar arquivo que a versão nova removeu. Os dados ficam em
; {localappdata}\Registrale e não são tocados.
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\site-packages"
Type: filesandordirs; Name: "{app}\python"

[UninstallDelete]
; Remove também o que o app criou em tempo de execução (ex.: __pycache__).
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\site-packages"
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#StageDir}\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\site-packages\*"; DestDir: "{app}\site-packages"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\windows\launcher.pyw"""; WorkingDir: "{app}\app"; IconFilename: "{app}\app\windows\registrale.ico"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\windows\launcher.pyw"""; WorkingDir: "{app}\app"; IconFilename: "{app}\app\windows\registrale.ico"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\windows\launcher.pyw"" --no-browser"; WorkingDir: "{app}\app"; IconFilename: "{app}\app\windows\registrale.ico"; Tasks: startupicon

[Run]
; Renova o cache de ícones do Windows para o atalho mostrar o ícone novo depois de atualizar.
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\windows\launcher.pyw"""; WorkingDir: "{app}\app"; Description: "Iniciar o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PgCtlPath: String;
  PgDataDir: String;
  ResultCode: Integer;
begin
  Result := '';
  PgCtlPath := ExpandConstant('{app}\app\windows\vendor\pgsql\bin\pg_ctl.exe');
  PgDataDir := ExpandConstant('{localappdata}\Registrale\pgdata');
  if FileExists(PgCtlPath) and FileExists(PgDataDir + '\postmaster.pid') then
  begin
    Exec(PgCtlPath, 'stop -D "' + PgDataDir + '" -m fast -w -t 10', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  Choice: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Registrale');
    if DirExists(DataDir) then
    begin
      { SuppressibleMsgBox: na desinstalação silenciosa responde Não (preserva os dados). }
      Choice := SuppressibleMsgBox(
        'Deseja remover também os dados locais do Registrale-DOU (banco de empresas, menções, configurações e logs em ' + DataDir + ')?' + #13#10 + #13#10 +
        'Clique em Não (recomendado) para preservar seus dados para uma futura reinstalação.',
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2,
        IDNO
      );
      if Choice = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
