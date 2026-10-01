; IdiotLaunch.iss — Inno Setup 安装脚本
; 傻瓜启动器安装包：自动安装到 D:\IdiotLaunch，创建 D 盘根目录和桌面快捷方式
; 打开安装包后自动开始安装（跳过所有向导页），仅显示原生进度条
; PrivilegesRequired=lowest 免管理员，适配学校教室电脑

#define MyAppName "傻瓜启动器"
#define MyAppVersion "1.8.3.3"
#define MyAppPublisher "tgcz2011"
#define MyAppExeName "IdiotLaunch.exe"

; 压缩级别：默认 lzma2/max（比 ultra 宽松，降低 SmartScreen 误报概率）
; 可用 /DCOMPRESSION=none 参数构建仅储存版（供测试 SmartScreen 表现）

; 仅储存版输出文件名加 _store 后缀
#ifdef STOREBUILD
  #define MyOutputSuffix "_store"
#else
  #define MyOutputSuffix ""
#endif

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
OutputBaseFilename=IdiotLaunch_Setup_{#MyAppVersion}{#MyOutputSuffix}
#ifdef COMPRESSION
Compression={#COMPRESSION}
#else
Compression=lzma2/max
#endif
SolidCompression=no
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=yes
CloseApplicationsFilter=IdiotLaunch.exe;CountdownDesktop.exe
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
; onedir 模式：打包整个 dist\IdiotLaunch\ 目录（exe + _internal\ + 内嵌资源）
Source: "dist\IdiotLaunch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 桌面快捷方式由 daemon 守护创建（ensure_shortcuts），避免重复

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
  // 自动跳过欢迎页，直接进入安装（保留进度条显示）
  if CurPageID = wpWelcome then
    WizardForm.NextButton.OnClick(WizardForm);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DShortcutPath: String;
  WshShell: Variant;
  Shortcut: Variant;
  BuildTypeFile: String;
  BuildTypeContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    // 在 D 盘根目录创建快捷方式（流氓软件模式，应用启动后也会自动重建）
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
      // 静默失败，应用启动时会重试
    end;
    // 写 build_type 标记：compressed 或 store，供自动更新时选择对应安装包
    try
      BuildTypeFile := ExpandConstant('{app}\build_type.txt');
      #ifdef STOREBUILD
        BuildTypeContent := 'store';
      #else
        BuildTypeContent := 'compressed';
      #endif
      SaveStringToFile(BuildTypeFile, BuildTypeContent, False);
    except
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  // 卸载前：先优雅通知 daemon 退出，等 5 秒，未退则强杀兜底
  if CurUninstallStep = usUninstall then
  begin
    try
      // 优雅退出：通过命名事件通知 daemon
      Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--quit-daemon', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    // 等待 daemon 优雅退出（最多 5 秒）
    Sleep(5000);
    try
      // 兜底：如果 daemon 仍在运行，强制结束
      Exec('taskkill', '/F /IM IdiotLaunch.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;
    // 删除 daemon 创建的快捷方式
    try
      DeleteFile('D:\傻瓜启动器.lnk');
      DeleteFile(ExpandConstant('{commondesktop}\傻瓜启动器.lnk'));
      DeleteFile(ExpandConstant('{userdesktop}\傻瓜启动器.lnk'));
    except
    end;
  end;
  // 卸载后：清理残留（_internal 目录、build_type.txt）
  if CurUninstallStep = usPostUninstall then
  begin
    try
      DelTree(ExpandConstant('{app}\_internal'), True, True, True);
      DeleteFile(ExpandConstant('{app}\build_type.txt'));
    except
    end;
  end;
end;
