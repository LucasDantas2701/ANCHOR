; Inno Setup recipe for ANCHOR's Windows installer: ANCHOR-Setup-<version>.exe.
; It installs for the current user only (no administrator password), adds ANCHOR to the Start menu,
; starts it with Windows unless the box is unticked (so schedules run), and, when uninstalled, asks
; whether to delete the user's data too.
;
;   set ANCHOR_VERSION=0.5.0
;   iscc packaging\installer.iss          (after pyinstaller packaging\anchor.spec)

#define AppVersion GetEnv("ANCHOR_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{B6441AE2-AEA8-5FFF-A428-995652A6F6AC}
AppName=ANCHOR
AppVersion={#AppVersion}
AppVerName=ANCHOR {#AppVersion}
AppPublisher=Lucas dos Santos Dantas
AppPublisherURL=https://lucasdantas2701.github.io/ANCHOR/
AppSupportURL=https://github.com/LucasDantas2701/ANCHOR/issues
DefaultDirName={localappdata}\Programs\ANCHOR
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=ANCHOR-Setup-{#AppVersion}
SetupIconFile=..\anchor\desktop\anchor.ico
UninstallDisplayIcon={app}\ANCHOR.exe
UninstallDisplayName=ANCHOR
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
english.StartWithWindows=Start ANCHOR with Windows (so schedules run; you can turn it off in Settings)
brazilianportuguese.StartWithWindows=Abrir o ANCHOR com o Windows (para os agendamentos rodarem; dá para desligar em Settings)
english.DeleteData=Also delete your ANCHOR data (automations, schedules, remembered choices, outputs and the downloaded browser) in %1?%n%nSaved passwords stay in Windows' Credential Manager: delete them in ANCHOR's Settings before uninstalling, or in the Credential Manager.
brazilianportuguese.DeleteData=Apagar também os seus dados do ANCHOR (automações, agendamentos, escolhas lembradas, saídas e o navegador baixado) em %1?%n%nAs senhas salvas ficam no Gerenciador de Credenciais do Windows: apague-as em Settings, no ANCHOR, antes de desinstalar, ou no próprio Gerenciador.

[Tasks]
Name: "startup"; Description: "{cm:StartWithWindows}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\ANCHOR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\ANCHOR"; Filename: "{app}\ANCHOR.exe"
Name: "{userdesktop}\ANCHOR"; Filename: "{app}\ANCHOR.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ANCHOR"; ValueData: """{app}\ANCHOR.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\ANCHOR.exe"; Description: "{cm:LaunchProgram,ANCHOR}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM ANCHOR.exe /F"; Flags: runhidden; RunOnceId: "CloseAnchor"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Data := ExpandConstant('{localappdata}\ANCHOR');
    if DirExists(Data) and (MsgBox(FmtMessage(CustomMessage('DeleteData'), [Data]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(Data, True, True, True);
  end;
end;
