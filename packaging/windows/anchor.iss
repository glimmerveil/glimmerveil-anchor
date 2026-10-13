; Glimmerveil Anchor — the Windows installer. Built by ci/build_installer.py from the folder the zip is
; built from (dist\GlimmerveilAnchor after ci/package_windows.py [--voice]); proven by the `installer` job.
;
; Per-user, no admin: Anchor.bat writes models\ next to itself, so the install dir must stay writable.
; Her life is NOT in here: it lives in %USERPROFILE%\anchor\peeps\ and the uninstaller never goes there.
; The uninstaller removes only what this installer put down. models\ is left alone, whatever is in it.
; No [UninstallDelete], no update check, no download, no browser at the end.
;
;   iscc /DSourceDir=<dist\GlimmerveilAnchor> /DAppVersion=<x> /DNumVersion=<a.b.c.d> [/DVoice] [/DSIGN /Sanchorsign=<cmd $f>]

#ifndef SourceDir
  #error Pass /DSourceDir=<dist\GlimmerveilAnchor>
#endif
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#ifndef NumVersion
  #define NumVersion "0.0.0.0"
#endif
#ifdef Voice
  #define SetupName "AnchorSetup-voice"
#else
  #define SetupName "AnchorSetup"
#endif

[Setup]
; One AppId for both flavours: the voice build installs over the plain one as an upgrade, never beside it.
AppId={{B1C098F0-9733-46F2-8CFB-E2F55EA3EA99}
AppName=Glimmerveil Anchor
AppVersion={#AppVersion}
AppVerName=Glimmerveil Anchor {#AppVersion}
AppPublisher=Glimmerveil
AppSupportURL=https://github.com/glimmerveil/glimmerveil-anchor/issues
VersionInfoVersion={#NumVersion}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Glimmerveil Anchor
DefaultGroupName=Glimmerveil Anchor
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename={#SetupName}
SetupIconFile=anchor.ico
UninstallDisplayIcon={app}\anchor.ico
UninstallDisplayName=Glimmerveil Anchor
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
#ifdef SIGN
SignTool=anchorsign
SignedUninstaller=yes
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Dirs]
; Her brains live here. Never removed on uninstall, whatever is in it.
Name: "{app}\models"; Flags: uninsneveruninstall

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "\models\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\models\PUT_YOUR_GGUF_HERE.txt"; DestDir: "{app}\models"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "anchor.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Glimmerveil Anchor"; Filename: "{app}\Anchor.bat"; WorkingDir: "{app}"; IconFilename: "{app}\anchor.ico"
Name: "{autodesktop}\Glimmerveil Anchor"; Filename: "{app}\Anchor.bat"; WorkingDir: "{app}"; IconFilename: "{app}\anchor.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Anchor.bat"; WorkingDir: "{app}"; Description: "Launch Glimmerveil Anchor now"; Flags: postinstall nowait skipifsilent unchecked shellexec
