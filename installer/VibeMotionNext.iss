; Inno Setup 6 — dibangun oleh CI:  iscc /DAppVersion=0.9 installer\VibeMotionNext.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7C2E8B1E-5F0B-4D8E-9A44-6C0B3F4C1A01}
AppName=Vibe Motion Next
AppVersion={#AppVersion}
AppPublisher=Vibe Motion
DefaultDirName={autopf}\Vibe Motion Next
DefaultGroupName=Vibe Motion Next
UninstallDisplayIcon={app}\VibeMotionNext.exe
OutputDir=..\dist
OutputBaseFilename=VibeMotionNext-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
SetupIconFile=..\assets\icon.ico

[Tasks]
Name: "desktopicon"; Description: "Buat ikon di Desktop"; GroupDescription: "Ikon tambahan:"

[Files]
Source: "..\dist\VibeMotionNext\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Vibe Motion Next"; Filename: "{app}\VibeMotionNext.exe"
Name: "{autodesktop}\Vibe Motion Next"; Filename: "{app}\VibeMotionNext.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VibeMotionNext.exe"; Description: "Jalankan Vibe Motion Next"; Flags: nowait postinstall skipifsilent

; Catatan: pengaturan, API key, dan proyek ada di %APPDATA%\VibeMotionNext dan SENGAJA tidak dihapus saat uninstall.
