; IdiotLaunch.iss — Inno Setup 安装脚本
; 傻瓜启动器安装包：自动安装到 D:\IdiotLaunch，创建 D 盘根目录和桌面快捷方式
; 打开安装包后自动开始安装（跳过所有向导页），仅显示原生进度条
; PrivilegesRequired=lowest 免管理员，适配学校教室电脑

#define MyAppName "傻瓜启动器"
#define MyAppVersion "1.3.0.1"
#define MyAppPublisher "tgcz2011"
#define MyAppExeName "IdiotLaunch.exe"

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
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
Uninstallable=no
UsePreviousAppDir=no
UsePreviousGroup=no
UsePreviousTasks=no
UsePreviousUserInfo=no
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinesesimp"; MessagesFile: "assets\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "教室倒计时一键启动器"

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
  end;
end;
