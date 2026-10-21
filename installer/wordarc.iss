; WordArc installer (Inno Setup 6).
; Sürüm build.ps1 tarafından WORDARC_VERSION env üzerinden verilir;
; buraya asla sabit sürüm yazılmaz.
;
; Düzen: Program Files (admin), sabit ad WordArc.exe, kısayollar + açılış
; girdisi Inno tarafından yönetilir. Kullanıcı verisi
; (%APPDATA%/WordArc, %LOCALAPPDATA%/WordArc: kayıtlar, toplantılar,
; modeller) installer'in dışındadır; update ve uninstall dokunmaz.

#define AppVersion GetEnv("WORDARC_VERSION")
#define AppVersionNum GetEnv("WORDARC_VERSION_NUM")
#if AppVersion == ""
  #error WORDARC_VERSION is not set. Build through build.ps1.
#endif
#if AppVersionNum == ""
  #error WORDARC_VERSION_NUM is not set. Build through build.ps1.
#endif

[Setup]
AppId={{8890F12E-2735-49F7-AFBA-FD21D9C12EC8}}
AppName=WordArc
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersionNum}
AppPublisher=WordArc
DefaultDirName={autopf}\WordArc
DefaultGroupName=WordArc
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
SolidCompression=yes
Compression=lzma2/max
OutputDir=..\dist
OutputBaseFilename=WordArc-{#AppVersion}
UninstallDisplayName=WordArc {#AppVersion}
WizardStyle=modern
; Elle çalıştırmada canlı WordArc açıksa kapatmayı önerir. Program içi
; güncelleme setup'tan önce zaten kapanır; bu yalnız manuel çalıştırma içindir.
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\inner\WordArc.exe"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked
Name: "autostart"; Description: "Windows açılışında başlat"; Flags: checkedonce

[Icons]
Name: "{group}\WordArc"; Filename: "{app}\WordArc.exe"
Name: "{autodesktop}\WordArc"; Filename: "{app}\WordArc.exe"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WordArc"; ValueData: "{app}\WordArc.exe"; Flags: uninsdeletevalue; Tasks: autostart

; Hem taze kurulumda hem sessiz güncellemede uygulamayı kurulum sonunda
; kullanıcının kendisi olarak (elevasyonsuz) başlatır.
[Run]
Filename: "{app}\WordArc.exe"; Flags: nowait runasoriginaluser

[Code]
{ Eski portable düzenden (sürümlü exe, %LocalAppData%\Programs\WordArc)
  tek seferlik göç. Yalnız kurulum artefaktları silinir; kayıt, toplantı,
  model barındıran %APPDATA%/WordArc ve %LOCALAPPDATA%/WordArc'ya dokunulmaz. }
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

  { Eski kullanıcı Run girdisi portable yolu gösteriyorsa kaldır;
    güncel HKLM girdisi [Registry] bölümünden gelir. }
  if RegQueryStringValue(HKCU,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'WordArc', RunValue) then
  begin
    if Pos('Programs\WordArc\WordArc-', RunValue) > 0 then
      RegDeleteValue(HKCU,
        'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'WordArc');
  end;
  RegDeleteValue(HKCU,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'Verbatim');

  { Eski Başlat menüsü artıkları. }
  DeleteFile(ExpandConstant('{userprograms}\Verbatim.lnk'));
  DeleteFile(ExpandConstant('{commonprograms}\Verbatim.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\WordArc.lnk'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    CleanOldPortable();
end;
