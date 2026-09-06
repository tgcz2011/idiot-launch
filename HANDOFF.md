# HANDOFF.md — Idiot Launch 交接文档

> 最后更新: 2026-09-06（v1.0.0.3，内嵌 Countdown Desktop 升级至 v3.2.1.1）

## 一、需求（用户原始要求）

1. 制作一个傻瓜式启动器软件，代码托管到 GitHub（仓库 `tgcz2011/idiot-launch`），使用规范提交过程。
2. 交接文档、README 等规范参考 `tgcz2011/countdown-desktop` 仓库。
3. 将 Countdown Desktop 的安装包**内嵌**到本软件中。
4. 用户点击「中考倒计时」→ 带参数命令启动 Countdown Desktop（`--exam zhongkao`）；未安装则用安装包静默安装。
5. 点击「高考倒计时」→ 同理（`--exam gaokao`）。
6. 点击「早晚读」→ 打开网页 `zztool.free.nf/morning-reading`。
7. 学校电脑装了冰点还原，C 盘会重置，**Countdown Desktop 必须安装到 D 盘**。

## 二、版本历史

| 版本 | 技术 | 结论 |
|------|------|------|
| **v1.0.0.0** | Python + tkinter + PyInstaller | 初始版本，三按钮 + 内嵌安装包 + D 盘静默安装 |
| **v1.0.0.1** | 同上 | 新增「关闭倒计时」按钮：taskkill /F /T 终止进程树 + 桌面刷新（d 升） |
| **v1.0.0.2** | 同上 | 关闭按钮改用 Countdown Desktop 命名事件 `CountdownDesktop_Quit` 优雅退出（不再 taskkill 强杀）；未运行时按钮自动变灰禁用（每 1.5s 轮询互斥量 `CountdownDesktop_Single`）；HoverButton 新增 disabled 视觉态（d 升） |
| **v1.0.0.3** | 同上 | 内嵌 Countdown Desktop 安装包从 v3.2.0.0 升级至 v3.2.1.1；同步更新 core.py/spec/build.ps1/release.yml/README/HANDOFF 中所有版本引用（d 升） |

## 三、架构

```
IdiotLaunch.exe（单文件，PyInstaller onefile）
  ├─ tkinter GUI：四个大按钮 + 状态栏
  ├─ core.find_installed_path()  检测安装（D盘优先 → 注册表 → 常见目录）
  ├─ core.silent_install()       释放内嵌安装包 → Inno /VERYSILENT /DIR=D:\CountdownDesktop
  ├─ core.launch_countdown()     CountdownDesktop.exe --exam zhongkao|gaokao（DETACHED_PROCESS）
  ├─ core.open_morning_reading() webbrowser.open(https://zztool.free.nf/morning-reading)
  ├─ core.is_running()           互斥量 CountdownDesktop_Single 检测是否在运行（比 tasklist 可靠）
  └─ core.quit_countdown()       OpenEvent(CountdownDesktop_Quit) + SetEvent → 运行实例自行优雅退出；轮询互斥量释放（8s 超时）
内嵌资源：_MEIPASS/installer/CountdownDesktop_Setup_3.2.1.1.exe
```

### 安装检测优先级

1. `D:\CountdownDesktop\CountdownDesktop.exe`（我们指定的路径）
2. 注册表 `HKCU/HKLM\...\Uninstall` 中含 "countdown" 的项 → `InstallLocation` / `DisplayIcon`
3. 常见目录：`%LOCALAPPDATA%\Programs\CountdownDesktop\`、`%PROGRAMFILES%\CountdownDesktop\`

### 静默安装参数

Inno Setup 标准参数：
- `/VERYSILENT` — 完全无界面
- `/NORESTART` — 不重启
- `/SUPPRESSMSGBOXES` — 抑制所有消息框
- `/DIR=D:\CountdownDesktop` — 强制安装到 D 盘

Countdown Desktop 安装包本身 `PrivilegesRequired=lowest`，无需管理员权限；内置 WebView2 Bootstrapper，缺失时自动静默安装。

### 带参启动

- `CountdownDesktop.exe --exam zhongkao` — 中考倒计时（壁纸+屏保统一使用 `countdown-junior` 页面）
- `CountdownDesktop.exe --exam gaokao` — 高考倒计时（壁纸+屏保统一使用 `countdown` 页面）
- Countdown Desktop v3.2.1.1 内置单实例接管：已有实例运行时，新启动自动通知旧实例退出并接管，后启动者覆盖先启动者效果。
- 使用 `DETACHED_PROCESS`（0x00000008）创建子进程，启动器关闭不影响倒计时运行。

## 四、踩过的错误 / 经验

### 内嵌大文件与 Git

1. **安装包不入库**：Countdown Desktop 安装包约 39 MB，不提交到 Git（`.gitignore` 排除 `installer/*.exe`）。构建时由 `build.ps1` 或 GitHub Actions 自动从 countdown-desktop Releases 下载。PyInstaller 在打包时将其作为 `datas` 内嵌进 exe。

### tkinter 打包

2. **tkinter 是标准库**：无需额外 pip 安装，PyInstaller 自动识别。`requirements.txt` 仅含 `pyinstaller`。
3. **`console=False`**：GUI 程序必须关闭控制台，否则会弹出黑色命令行窗口。

### 学校环境适配

4. **D 盘强制安装**：Inno Setup 的 `/DIR=` 参数可覆盖 `DefaultDirName`，即使安装包默认装到 `{autopf}`（用户目录，通常在 C 盘），也能强制装到 D 盘。
5. **冰点还原**：C 盘重启后重置，D 盘通常不受保护。安装路径、配置文件（Countdown Desktop 的 `%APPDATA%` 配置在 C 盘，会被重置——但倒计时类型通过 `--exam` 参数每次启动时指定，不依赖持久化配置）。
6. **无需管理员**：Countdown Desktop 安装包 `PrivilegesRequired=lowest`，学生账号也能安装。

### 进程管理

7. **DETACHED_PROCESS**：如果用普通 `subprocess.Popen`，启动器退出时子进程可能收到 CTRL_CLOSE_EVENT。使用 `creationflags=DETACHED_PROCESS` 让子进程完全独立。
8. **单实例接管**：Countdown Desktop 自己处理单实例，启动器无需检测是否已在运行，直接带参启动即可切换类型。

### 一键关闭（v1.0.0.1 → v1.0.0.2 演进）

9. **v1.0.0.1 用 taskkill /F /T**：简单粗暴，但强杀可能导致壁纸窗口残留、桌面白屏，且用户明确要求用 Countdown Desktop 自带的优雅退出机制。
10. **v1.0.0.2 改用命名事件**：Countdown Desktop 运行时创建命名事件 `CountdownDesktop_Quit`（手动重置、初始无信号），主进程 QTimer 每 250ms 轮询 `WaitForSingleObject(h, 0)`，收到信号后调用 `quit()`——停壁纸/屏保、`refresh_desktop_wallpaper()` 恢复桌面、删 PID、退托盘。启动器只需 `OpenEventW(EVENT_MODIFY_STATE, False, "CountdownDesktop_Quit")` + `SetEvent` + `CloseHandle`，不启动额外进程、不依赖已安装 exe 版本。
11. **退出确认**：SetEvent 后轮询互斥量 `CountdownDesktop_Single`（每 250ms，最多 8s），互斥量释放即说明实例已退出。超时返回 False（不做强杀兜底，遵循用户"不要粗暴"要求）。
12. **运行状态检测用互斥量不用 tasklist**：`CreateMutexW("CountdownDesktop_Single")` 后 `GetLastError()==183(ERROR_ALREADY_EXISTS)` 即表示有实例在运行，比解析 tasklist 输出更快更可靠。
13. **按钮变灰机制**：GUI 每 1.5s 后台线程调 `is_running()`，通过 `root.after` 回主线程更新 `btn_kill.set_enabled(running)`。HoverButton 新增 `_enabled` 状态：禁用时绘浅灰 `#bdc3c7`、文字 `#ecf0f1`、cursor=arrow、解绑点击；加载中（`_loading`）时所有按钮统一禁用。
14. **旧版不支持退出事件**：若运行的是旧版 Countdown Desktop（无 `CountdownDesktop_Quit` 事件），`OpenEventW` 返回 NULL，抛 RuntimeError 提示版本过旧。学校环境统一装 v3.2.1.1 不存在此问题。

## 五、项目结构

```
idiot-launch/
├── run.py                      入口（调用 src.main.main）
├── src/
│   ├── __init__.py             resource_path（打包资源路径解析）
│   ├── core.py                 核心逻辑（安装检测/静默安装/带参启动/打开网页）
│   └── main.py                 GUI（tkinter，HoverButton 三按钮 + 状态栏 + 后台线程）
├── installer/
│   └── CountdownDesktop_Setup_3.2.1.1.exe  （构建时下载，gitignore）
├── tools/                      辅助脚本（预留）
├── build.ps1                   本地一键构建（venv + 下载安装包 + PyInstaller）
├── IdiotLaunch.spec            PyInstaller 规格（onefile + datas 内嵌安装包）
├── requirements.txt            pyinstaller
├── .gitignore                  排除 venv/build/dist/installer/*.exe
├── .github/workflows/release.yml   tag→构建→Release
├── README.md                   用户文档
├── HANDOFF.md                  本文档（每次更新强制同步）
└── LICENSE                     GPL-3.0
```

## 六、toolchain

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | 开发机 3.14；CI 3.12 | tkinter 标准库 |
| PyInstaller | 6.x | onefile 打包，内嵌安装包 |
| git / gh | 已登录 tgcz2011 | 推送与 release |
| GitHub Actions | windows-latest | 自动构建发布 |

## 七、构建与发布

```powershell
# 本地构建
.\build.ps1 -Version 1.0.0.0
# 产物：dist\IdiotLaunch.exe

# 发布
git add -A
git commit -m "v1.0.0.0: initial release"
git tag v1.0.0.0
git push origin main v1.0.0.0
# GitHub Actions 自动构建并创建 Release
```

## 八、版本规则

a=大添加 b=大改 c=小添加 d=小改动；去掉 `.` 后数值必须严格大于上一版本。当前最高已发布 tag：v1.0.0.3。

## 九、已知限制 / 待办

1. **D 盘不存在时报错**：若电脑无 D 盘，静默安装会失败。未来可增加自动回退到 C 盘或让用户选择路径。
2. **安装包版本固定**：当前内嵌 v3.2.1.1，升级 Countdown Desktop 版本需更新 `INSTALLER_REL`、`build.ps1`、`release.yml` 和 README 中的版本号。
3. **无自动更新**：启动器本身不检查更新，需手动下载新版。
4. **早晚读用系统默认浏览器**：学校电脑默认浏览器可能被组策略锁定，若无法打开需手动复制链接。
5. **tkinter 界面较朴素**：功能优先，未使用 PySide6 等高级 UI 框架（保持零运行时依赖、打包体积小）。

## 十、验证方法备忘

```powershell
# 1. 源码运行（需先下载安装包到 installer\）
python run.py

# 2. 构建后运行
.\dist\IdiotLaunch.exe

# 3. 验证静默安装（手动测试）
.\installer\CountdownDesktop_Setup_3.2.1.1.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR=D:\CountdownDesktop
# 检查 D:\CountdownDesktop\CountdownDesktop.exe 是否存在

# 4. 验证带参启动
D:\CountdownDesktop\CountdownDesktop.exe --exam zhongkao
D:\CountdownDesktop\CountdownDesktop.exe --exam gaokao
```
