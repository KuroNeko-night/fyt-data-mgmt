; 峰运通数据管理系统 —— Inno Setup 安装脚本
; ============================================
; 由 build.py 自动填入版本号等占位符后编译；也可手动定义 /D 覆盖。
; 生成中文安装向导：选安装目录、桌面/开始菜单快捷方式、安装完成可直接运行。
; 兼容 Windows 7 SP1 及以上。

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef MyAppName
  #define MyAppName "峰运通数据管理系统"
#endif
#ifndef MyAppId
  #define MyAppId "FYTDataMgmt"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "重庆峰运通供应链管理公司"
#endif
#ifndef MyAppExe
  #define MyAppExe "FYTDataMgmt.exe"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\FYTDataMgmt"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif
#ifndef AssetsDir
  #define AssetsDir "..\assets"
#endif

[Setup]
AppId={{A7F3C2E1-4B9D-4E6A-9C21-FYTDATAMGMT01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppId}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir={#OutputDir}
OutputBaseFilename={#MyAppId}_Setup_{#MyAppVersion}
SetupIconFile={#AssetsDir}\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
MinVersion=6.1sp1
PrivilegesRequiredOverridesAllowed=dialog
; 在线更新覆盖安装时，自动检测并关闭正在运行的旧程序，避免文件被占用导致更新失败。
CloseApplications=yes
RestartApplications=no
AppMutex={#MyAppId}_SingleInstance

[Languages]
; build.py 若在 Inno 安装目录找到简体中文语言文件，会通过 /DChineseIsl=<路径> 传入，
; 此时安装向导为简体中文；否则回退到必定存在的 Default.isl(英文向导)，保证一定能编译。
#ifdef ChineseIsl
Name: "cn"; MessagesFile: "{#ChineseIsl}"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式:"

[Files]
Source: "{#SourceDir}\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}"
