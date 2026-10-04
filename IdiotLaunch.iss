; IdiotLaunch.iss — 安装脚本（Flutter 前端 + Python 后端）
;
; 设计取舍（作者确认过，不是疏漏）：
;   * 强制安装到 D:\IdiotLaunch：学校电脑 C 盘有冰点还原，装 C 盘重启就没了。
;   * 不显示目录页/组件页/完成页：老师只需要双击，不需要做技术选择。
;
; 卸载策略：卸载即清除全部内容（程序、后端、data 数据、快捷方式、
;           临时文件、壁纸自启注册表项、历史遗留目录）。

#define MyAppName "傻瓜启动器"
#define MyAppVersion "3.0.0.0-beta27"
#define MyAppPublisher "tgcz2011"
#define MyAppExeName "IdiotLaunch.exe"
#define MyBackendExeName "IdiotLaunchBackend.exe"
#define MyAppURL "https://github.com/tgcz2011/idiot-launch"

[Setup]
AppId={{B7E3A2D1-4F5A-4C8E-9B2D-1A3F5E7C9D0B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
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
CloseApplicationsFilter=IdiotLaunch.exe,IdiotLaunchBackend.exe,CountdownDesktop.exe
RestartApplications=no
Uninstallable=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UsePreviousAppDir=no
UsePreviousGroup=no
UsePreviousTasks=no
UsePreviousUserInfo=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
SetupIconFile=assets\icon.ico

[Languages]
Name: "chinesesimp"; MessagesFile: "assets\ChineseSimplified.isl"

[Files]
; Flutter 前端产物（整个 Release 目录：exe + dll + data\）
Source: "flutter_app\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Python 后端产物
Source: "dist\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 快捷方式由后台守护进程负责创建（冰点还原清掉后会自动补回来），这里不再重复创建

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载后清除全部内容与数据
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "D:\IdiotLaunch\CountdownDesktop"
Type: files; Name: "D:\傻瓜启动器.lnk"
Type: files; Name: "{commondesktop}\傻瓜启动器.lnk"
Type: files; Name: "{userdesktop}\傻瓜启动器.lnk"
Type: filesandordirs; Name: "{userappdata}\Microsoft\Windows\Start Menu\Programs\{#MyAppName}"

[Code]
function IsAutoUpdate: Boolean;
var
  Tail: String;
begin
  { 自动更新时后端会带 /AutoUpdate=1 启动安装包，装完由我们把程序拉起来 }
  Tail := Uppercase(GetCmdTail);
  Result := Pos('/AUTOUPDATE=1', Tail) > 0;
end;

procedure KillAppProcesses;
var
  ResultCode: Integer;
begin
  { 不带 /T：安装包可能是被我们自己的进程启动的，
    /T 会顺着进程树把安装包本身也杀掉（历史事故：更新脚本被自己杀死，
    结果文件永远停在 "running"，重启和清理全部没执行）。 }
  Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('taskkill', '/F /IM {#MyBackendExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup: Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  if not DirExists('D:\') then
  begin
    { Suppressible：静默自动更新时不再弹窗卡住安装 }
    SuppressibleMsgBox('未检测到 D 盘！' + #13#10 +
           '傻瓜启动器需要安装到 D 盘以规避冰点还原。' + #13#10 +
           '请联系管理员检查 D 盘是否正常。', mbError, MB_OK, IDOK);
    Abort;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { 打开即装：跳过欢迎页，只保留原生进度条 }
  if CurPageID = wpWelcome then
    WizardForm.NextButton.OnClick(WizardForm);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  { 1. 先请后端优雅退出（会顺带关掉壁纸、悬浮球和早晚读浏览器） }
  if FileExists(ExpandConstant('{app}\backend\{#MyBackendExeName}')) then
    Exec(ExpandConstant('{app}\backend\{#MyBackendExeName}'), '--quit', '',
         SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(2500);
  { 2. 兜底强杀残留进程 }
  KillAppProcesses;
  Sleep(800);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DShortcutPath: String;
  WshShell: Variant;
  Shortcut: Variant;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    { D 盘根目录快捷方式 }
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

    { 静默自动更新：装完把程序重新拉起来（普通安装由 [Run] 负责） }
    if IsAutoUpdate then
    begin
      Sleep(1200);
      Exec(ExpandConstant('{app}\{#MyAppExeName}'), '', ExpandConstant('{app}'),
           SW_SHOWNORMAL, ewNoWait, ResultCode);
    end;
  end;
end;

procedure CleanupUserFiles;
var
  FindRec: TFindRec;
  TempPath: String;
begin
  { %TEMP% 下的运行时文件 }
  TempPath := ExpandConstant('{%TEMP}');
  if TempPath = '' then
    Exit;
  if FindFirst(TempPath + '\idiot_launch_*', FindRec) then
  begin
    try
      repeat
        DeleteFile(TempPath + '\' + FindRec.Name);
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { 1. 优雅退出后端 }
    if FileExists(ExpandConstant('{app}\backend\{#MyBackendExeName}')) then
      Exec(ExpandConstant('{app}\backend\{#MyBackendExeName}'), '--quit', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(3000);
    { 2. 强杀兜底（含壁纸/悬浮球/早晚读浏览器，都是同一个 exe） }
    KillAppProcesses;
    Sleep(800);
    { 3. 快捷方式 }
    DeleteFile('D:\傻瓜启动器.lnk');
    DeleteFile(ExpandConstant('{commondesktop}\傻瓜启动器.lnk'));
    DeleteFile(ExpandConstant('{userdesktop}\傻瓜启动器.lnk'));
    { 4. 壁纸自启注册表项（Countdown Desktop 写进去的） }
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'CountdownDesktop');
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'IdiotLaunch');
    { 5. 临时文件 }
    CleanupUserFiles;
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    { 6. 清掉整个安装目录（含 data：登录信息、日志、下载的安装包） }
    DelTree('D:\IdiotLaunch\CountdownDesktop', True, True, True);
    DelTree(ExpandConstant('{app}\backend'), True, True, True);
    DelTree(ExpandConstant('{app}\data'), True, True, True);
    DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
