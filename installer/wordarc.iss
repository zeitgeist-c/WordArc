; WordArc installer (Inno Setup 6).
; The version is supplied by build.ps1 through the WORDARC_VERSION env;
; a fixed version is never written here.
;
; Layout: Program Files (admin), fixed name WordArc.exe, shortcuts + startup
; entry managed by Inno. User data
; (%APPDATA%/WordArc, %LOCALAPPDATA%/WordArc: recordings, meetings,
; models) lives outside the installer; update and uninstall leave it alone.

#define AppVersion GetEnv("WORDARC_VERSION")
#define AppVersionNum GetEnv("WORDARC_VERSION_NUM")
#if AppVersion == ""
  #error WORDARC_VERSION is not set. Build through build.ps1.
#endif
#if AppVersionNum == ""
  #error WORDARC_VERSION_NUM is not set. Build through build.ps1.
#endif

[Setup]
#ifdef WordArcTest
AppId={{8AAE344D-ACB6-432B-B153-A0DB6132C01B}
DefaultDirName={#WordArcTestDir}
PrivilegesRequired=lowest
#else
AppId={{8890F12E-2735-49F7-AFBA-FD21D9C12EC8}}
DefaultDirName={autopf}\WordArc
PrivilegesRequired=admin
#endif
AppName=WordArc
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersionNum}
AppPublisher=zeitgeist-c
DefaultGroupName=WordArc
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=no
DisableDirPage=yes
SetupLogging=yes
SolidCompression=yes
Compression=lzma2/max
OutputDir=..\dist
OutputBaseFilename=WordArc-{#AppVersion}
UninstallDisplayName=WordArc {#AppVersion}
WizardStyle=modern
; The setup file itself carries the product icon instead of the
; generic download arrow; brand assets are rendered by build_brand_assets.
SetupIconFile=..\assets\brand\wordarc.ico
; Offers to close a running WordArc when setup is started by hand. The in-app
; updater already closes it before setup; this is only for manual runs.
CloseApplications=yes
RestartApplications=no

[Files]
#ifdef WordArcTestPayload
Source: "{#WordArcTestPayload}"; DestDir: "{app}"; Flags: ignoreversion
#else
Source: "..\dist\inner\WordArc.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif

; 13 interface languages: Name is the application language code ({language}
; passes through as-is to --setup-language), MessagesFile is Inno's official
; translation.
[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "pt-BR"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "zh-CN"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
en.DesktopIcon=Create a desktop shortcut
en.AutoStart=Start with Windows
tr.DesktopIcon=Masaüstü kısayolu oluştur
tr.AutoStart=Windows açılışında başlat
de.DesktopIcon=Desktopverknüpfung erstellen
de.AutoStart=Mit Windows starten
es.DesktopIcon=Crear un acceso directo en el escritorio
es.AutoStart=Iniciar con Windows
fr.DesktopIcon=Créer un raccourci sur le bureau
fr.AutoStart=Démarrer avec Windows
it.DesktopIcon=Crea un collegamento sul desktop
it.AutoStart=Avvia con Windows
pt-BR.DesktopIcon=Criar um atalho na área de trabalho
pt-BR.AutoStart=Iniciar com o Windows
ru.DesktopIcon=Создать ярлык на рабочем столе
ru.AutoStart=Запускать вместе с Windows
pl.DesktopIcon=Utwórz skrót na pulpicie
pl.AutoStart=Uruchamiaj razem ze startem systemu Windows
nl.DesktopIcon=Een bureaubladsnelkoppeling maken
nl.AutoStart=Starten met Windows
zh-CN.DesktopIcon=创建桌面快捷方式
zh-CN.AutoStart=随 Windows 启动
ja.DesktopIcon=デスクトップにショートカットを作成
ja.AutoStart=Windows 起動時に開始
ko.DesktopIcon=바탕 화면 바로 가기 만들기
ko.AutoStart=Windows 시작 시 실행

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStart}"; Flags: checkedonce

[Icons]
#ifndef WordArcTest
Name: "{group}\WordArc"; Filename: "{app}\WordArc.exe"
Name: "{autodesktop}\WordArc"; Filename: "{app}\WordArc.exe"; Check: KeepDesktopLink
#endif

[Registry]
#ifndef WordArcTest
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WordArc"; ValueData: "{app}\WordArc.exe"; Flags: uninsdeletevalue; Tasks: autostart
#endif

; Launches the app at the end of setup, both on a fresh install and on a silent
; update, as the user themselves (unelevated). On a fresh install the language
; picked in the wizard carries over to the first launch through --setup-language;
; it does not run on a managed update, where the saved language is kept.
[Run]
Filename: "{app}\WordArc.exe"; Parameters: "--setup-language {language}"; Flags: nowait runasoriginaluser; Check: NotManagedUpdate; BeforeInstall: CleanLaunchEnvironment

[Code]
var
  PreviousInstallDir: String;
  PreflightDone: Boolean;

function OpenProcess(Access: LongWord; Inherit: Boolean; PID: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function SetEnvironmentVariable(Name, Value: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';
function SetDllDirectory(Path: Integer): Boolean;
  external 'SetDllDirectoryW@kernel32.dll stdcall';

procedure CleanLaunchEnvironment();
begin
  SetEnvironmentVariable('PYINSTALLER_RESET_ENVIRONMENT', '1');
  SetDllDirectory(0);
end;

function NotManagedUpdate(): Boolean;
begin
  Result := ExpandConstant('{param:WORDARC_MANAGED|0}') <> '1';
end;

function KeepDesktopLink(): Boolean;
begin
  Result := WizardIsTaskSelected('desktopicon') or
    FileExists(ExpandConstant('{autodesktop}\WordArc.lnk'));
end;

procedure InitializeWizard();
begin
  { Never retain a test/temp install location, even when /DIR was supplied. }
#ifdef WordArcTest
  WizardForm.DirEdit.Text := ExpandConstant('{#WordArcTestDir}');
#else
  WizardForm.DirEdit.Text := ExpandConstant('{autopf}\WordArc');
  RegQueryStringValue(HKLM32,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8890F12E-2735-49F7-AFBA-FD21D9C12EC8}}_is1',
    'InstallLocation', PreviousInstallDir);
#endif
end;

procedure RegisterExtraCloseApplicationsResources();
begin
  if (PreviousInstallDir <> '') and
     FileExists(AddBackslash(PreviousInstallDir) + 'WordArc.exe') then
    RegisterExtraCloseApplicationsResource(
#if VER >= EncodeVer(7, 0, 0)
      AddBackslash(PreviousInstallDir) + 'WordArc.exe');
#else
      False, AddBackslash(PreviousInstallDir) + 'WordArc.exe');
#endif
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code, PID, WaitResult: Integer;
  Handle: THandle;
  Health: AnsiString;
  Report, ReadyFile: String;
begin
  Result := '';
  if not PreflightDone then
  begin
    ExtractTemporaryFile('WordArc.exe');
    CleanLaunchEnvironment();
    Report := ExpandConstant('{tmp}\wordarc-preflight.json');
    if not Exec(ExpandConstant('{tmp}\WordArc.exe'),
      '--installation-check --output ' + AddQuotes(Report), ExpandConstant('{tmp}'),
      SW_HIDE, ewWaitUntilTerminated, Code) then
      Code := -1;
    if (Code <> 0) or not LoadStringFromFile(Report, Health) then
    begin
      Result := 'WordArc could not pass its installation check. The current version was retained.';
      Exit;
    end;
    if (Pos('"ok": true', String(Health)) = 0) or
       (Pos('"version": "{#AppVersion}"', String(Health)) = 0) then
    begin
      Result := 'WordArc installation check returned the wrong version.';
      Exit;
    end;
    PreflightDone := True;
  end;
  ReadyFile := ExpandConstant('{param:WORDARC_READY|}');
  if ReadyFile <> '' then
    if not SaveStringToFile(ReadyFile, 'ready', False) then
    begin
      Result := 'The application could not be notified that setup is ready.';
      Exit;
    end;
  PID := StrToIntDef(ExpandConstant('{param:WORDARC_OLDPID|0}'), 0);
  if PID > 0 then
  begin
    Handle := OpenProcess($100000, False, PID);
    if Handle <> 0 then
    begin
      WaitResult := WaitForSingleObject(Handle, 60000);
      CloseHandle(Handle);
      if WaitResult <> 0 then
        Result := 'The current WordArc did not close. Installation was cancelled.';
    end;
    Sleep(1000); { Allow the one-file bootloader to release the executable. }
  end;
end;

procedure CleanPreviousInstall();
var
  OldDir, KeyDir, RunValue: String;
begin
  OldDir := RemoveBackslash(PreviousInstallDir);
  if (OldDir = '') or (CompareText(OldDir, RemoveBackslash(ExpandConstant('{app}'))) = 0) then
    Exit;
  { Manual/legacy updates have no supervisor. Only delete the three owned
    program files, after the new payload passed preflight and was installed. }
  if NotManagedUpdate() then
  begin
    DeleteFile(OldDir + '\WordArc.exe');
    DeleteFile(OldDir + '\unins000.exe');
    DeleteFile(OldDir + '\unins000.dat');
    RemoveDir(OldDir); { Never recursive; unrelated files remain. }
  end;
#ifndef WordArcTest
  if RegQueryStringValue(HKLM32, 'Software\Microsoft\Windows\CurrentVersion\Run',
    'WordArc', RunValue) then
    if Pos(Lowercase(OldDir + '\WordArc.exe'), Lowercase(RunValue)) > 0 then
      RegDeleteValue(HKLM32, 'Software\Microsoft\Windows\CurrentVersion\Run', 'WordArc');
  if RegQueryStringValue(HKLM32,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8890F12E-2735-49F7-AFBA-FD21D9C12EC8}}_is1',
    'InstallLocation', KeyDir) then
    if CompareText(RemoveBackslash(KeyDir), OldDir) = 0 then
      RegDeleteKeyIncludingSubkeys(HKLM32,
        'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8890F12E-2735-49F7-AFBA-FD21D9C12EC8}}_is1');
#endif
end;
{ One-time migration from the old portable layout (versioned exe,
  %LocalAppData%\Programs\WordArc). Only install artifacts are deleted;
  %APPDATA%/WordArc and %LOCALAPPDATA%/WordArc, which hold user data,
  are left untouched. }
procedure CleanOldPortable();
var
  Dir, Path: String;
  FindRec: TFindRec;
  RunValue: String;
begin
  Dir := ExpandConstant('{localappdata}\Programs\WordArc');
  if DirExists(Dir) then
  begin
    if FindFirst(Dir + '\WordArc-*.exe', FindRec) then
    try
      repeat
        Path := Dir + '\' + FindRec.Name;
        if CompareText(Path, ExpandConstant('{app}\WordArc.exe')) <> 0 then
          if not DeleteFile(Path) then
            Log('Eski portable exe silinemedi: ' + Path);
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
    if FindFirst(Dir + '\WordArc-*.bat', FindRec) then
    try
      repeat
        Path := Dir + '\' + FindRec.Name;
        if not DeleteFile(Path) then
          Log('Eski portable bat silinemedi: ' + Path);
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
    if FindFirst(Dir + '\*', FindRec) then
    begin
      FindClose(FindRec);
    end
    else
      RemoveDir(Dir);
  end;

  { Drop the old per-user Run entry if it points at the portable path;
    the current HKLM entry comes from the [Registry] section. }
  if RegQueryStringValue(HKCU,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'WordArc', RunValue) then
  begin
    if Pos('Programs\WordArc\WordArc-', RunValue) > 0 then
      RegDeleteValue(HKCU,
        'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'WordArc');
  end;
  RegDeleteValue(HKCU,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'Verbatim');

  { Old Start menu leftovers. }
  DeleteFile(ExpandConstant('{userprograms}\Verbatim.lnk'));
  DeleteFile(ExpandConstant('{commonprograms}\Verbatim.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\WordArc.lnk'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if GetSHA256OfFile(ExpandConstant('{app}\WordArc.exe')) <>
       GetSHA256OfFile(ExpandConstant('{tmp}\WordArc.exe')) then
      RaiseException('Installed WordArc does not match the verified payload.');
#ifndef WordArcTest
    if NotManagedUpdate() then
      CleanOldPortable();
#endif
    CleanPreviousInstall();
  end;
end;
