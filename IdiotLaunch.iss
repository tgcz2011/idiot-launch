; IdiotLaunch.iss — Inno Setup 安装脚本（Flutter 前端 + Python 后端版）
; 安装到 D:\IdiotLaunch，Flutter 前端为主入口，后端在 backend\ 子目录
; 打开安装包后自动开始安装，仅显示原生进度条

#define MyAppName "傻瓜启动器"
#define MyAppVersion "3.0.0.0-beta2"
#define MyAppPublisher "tgcz2011"
#define MyAppExeName "IdiotLaunch.exe"
#define MyBackendExeName "IdiotLaunchBackend.exe"

[Setup]
AppId={{B7E3A2D1-4F5A-4C8E-9B2D-1A3F5E7C9D0B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/tgcz2011/idiot-launch
AppSupportURL=https://github.com/tgcz2011/idiot-launch/issues
AppUpdatesURL=https://github.com/tgcz2011/idiot-launch/releases
DefaultDirName=D:\IdiotLaunch
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
DisableStartupPrompt=yes
OutputDir=dist
OutputBaseFilename=IdiotLaunch_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=no
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=yes
CloseApplicationsFilter=IdiotLaunch.exe;IdiotLaunchBackend.exe;CountdownDesktop.exe
RestartApplications=yes
Uninstallable=yes
UsePreviousAppDir=no
UsePreviousGroup=no
UsePreviousTasks=no
UsePreviousUserInfo=no
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinesesimp"; MessagesFile: "assets\ChineseSimplified.isl"

[Files]
; Flutter 前端产物（整个 Release 目录）
Source: "flutter_app\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Python 后端产物
Source: "dist\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 桌面快捷方式由 daemon 守护创建

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure InitializeWizard();
begin
  if not DirExists('D:\') then
  begin
    MsgBox('未检测到 D 盘！' + #13#10 +
           '傻瓜启动器需要安装到 D 盘以规避冰点还原。' + #13#10 +
           '请联系管理员检查 D 盘是否正常。', mbError, MB_OK);
    Abort;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    WizardForm.NextButton.OnClick(WizardForm);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  // 1. 优雅退出：通知后端 daemon
  try
    Exec(ExpandConstant('{app}\backend\{#MyBackendExeName}'), '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  Sleep(2000);
  // 2. 强制结束残留进程（Flutter 前端 + 后端 + 壁纸）
  try
    Exec('taskkill', '/F /IM IdiotLaunch.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  try
    Exec('taskkill', '/F /IM IdiotLaunchBackend.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
  end;
  Sleep(1000);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DShortcutPath: String;
  WshShell: Variant;
  Shortcut: Variant;
begin
  if CurStep = ssPostInstall then
  begin
    // D 盘根目录快捷方式
    try
      DShortcutPath := 'D:\傻瓜启动器.lnk';
      WshShell := CreateOleObject('WScript.Shell');
      Shortcut := WshShell.CreateShortcut(DShortcutPath);
      Shortcut.TargetPath := ExpandConstant('{app}\{#MyAppExeName}');
      Shortcut.WorkingDirectory := ExpandConstant('{app}');
      Shortcut.IconLocation := ExpandConstant('{app}\{#MyAppExeName}') + ',0';
      Shortcut.Description := '教室倒计时一键启动器';
      Shortcut.Save;
    except
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // 优雅退出后端
    try
      Exec(ExpandConstant('{app}\backend\{#MyBackendExeName}'), '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    Sleep(3000);
    // 强杀兜底
    try
      Exec('taskkill', '/F /IM IdiotLaunch.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    try
      Exec('taskkill', '/F /IM IdiotLaunchBackend.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    // 删除快捷方式
    try
      DeleteFile('D:\傻瓜启动器.lnk');
      DeleteFile(ExpandConstant('{commondesktop}\傻瓜启动器.lnk'));
      DeleteFile(ExpandConstant('{userdesktop}\傻瓜启动器.lnk'));
    except
    end;
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    // 清理残留目录
    try
      DelTree(ExpandConstant('{app}\backend'), True, True, True);
      DelTree(ExpandConstant('{app}\data'), True, True, True);
    except
    end;
  end;
end;
