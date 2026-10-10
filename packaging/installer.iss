#ifndef AppVersion
  #error AppVersion must be defined from build-release.ps1
#endif

#define AppName "Tutoriales Visuales"
#define AppExeName "TutorialesVisuales.exe"
#define AppGuid "{{7F0D71C7-99BB-4B22-98A2-53B3E591B925}"
#define AppMutexName "TutorialesVisuales.App.7f0d71c7-99bb-4b22-98a2-53b3e591b925"

[Setup]
AppId={#AppGuid}
AppName={#AppName}
AppVersion={#AppVersion}
VersionInfoVersion={#GetFileVersion("..\dist\TutorialesVisuales\TutorialesVisuales.exe")}
VersionInfoProductVersion={#GetFileVersion("..\dist\TutorialesVisuales\TutorialesVisuales.exe")}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Tutoriales Visuales
DefaultDirName={localappdata}\Programs\Tutoriales Visuales
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=tutoriales-visuales-setup-{#AppVersion}
SetupIconFile=..\assets\tutoriales-visuales.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex={#AppMutexName}
ChangesAssociations=yes
UsedUserAreasWarning=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce

[Files]
Source: "..\dist\TutorialesVisuales\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installation.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.tutorial"; ValueType: string; ValueName: ""; ValueData: "TutorialesVisuales.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.tutorial"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-tutoriales-visuales"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\TutorialesVisuales.Project"; ValueType: string; ValueName: ""; ValueData: "Proyecto de Tutoriales Visuales"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\TutorialesVisuales.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"
Root: HKA; Subkey: "Software\Classes\TutorialesVisuales.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
