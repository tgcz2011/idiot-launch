# HANDOFF.md — Idiot Launch 交接文档

> 最后更新: 2026-09-12（v1.2.0.1，修复自我更新状态被覆盖的严重 bug + 安装返回值检查 + 重装 None 保护）

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
| **v1.1.0.0** | 同上 | 完整自动更新体系（c 升）：①启动时版本检测，本地旧于内嵌则删目录重装；②关闭窗口启动 `--daemon` 无窗口守护进程，查 GitHub 最新版并后台下载（6h 间隔、10min 超时）；③下载完成后等 Countdown Desktop 退出，删旧目录静默装新版；④启动时补装待更新；⑤状态存 `D:\CountdownDesktop_Updates\state.json` 不被冰点还原清除；⑥`EMBEDDED_VERSION` 常量统一管理内嵌版本，INSTALLER_REL 自动拼接 |
| **v1.1.1.0** | 同上 | 新增安装进度弹窗 ProgressDialog（c 升）：置顶、无关闭按钮、居中、indeterminate 进度条动画；所有耗时操作（安装/启动/关闭/更新）均弹窗提示，防止教室电脑性能差导致老师误以为卡死；弹窗文字按操作类型区分（首次安装提示 10-30 秒）；启动时待更新安装也弹窗 |
| **v1.1.2.0** | 同上 | 版本元数据 + 强制 noUPX（c 升）：①新增 version_info.txt，注入完整 PE 元数据（CompanyName=tgcz2011、FileDescription、ProductName、LegalCopyright、FileVersion 等），SmartScreen 对有完整元数据的程序更宽容；②spec 中 upx=True→upx=False，build.ps1 和 CI 均加 --noupx 参数，不使用 UPX 压缩壳（UPX 加壳是病毒常用手段，易触发杀软/SmartScreen 误报）；③修正 CI release body 中过时的 v3.2.0.0 版本号 |
| **v1.2.0.0** | 同上 | Idiot Launch 自身后台静默更新（b 升，大改）：①daemon 同时检查自身 GitHub 最新 Release，有新版下载到 D:\CountdownDesktop_Updates\IdiotLaunch_v<ver>.exe 并标记 pending_launcher_update；②下次启动时 run.py 在 GUI 创建前调用 apply_launcher_update_if_pending()，生成隐藏 VBScript（wscript //B 完全无窗口）→ 启动 VBS → sys.exit；③VBS 每 500ms 重试 CopyFile 覆盖旧 exe（最多 15 秒），成功后删下载文件、启动新版、自删除；④用户体验：程序闪一下关闭，1-2 秒后自动重开为新版，原位置替换，保持单文件；⑤失败安全：替换失败旧 exe 不受影响，下次启动再试；新版运行时 _cleanup_stale_launcher_pending 自动清理过期状态；⑥仅 frozen 模式生效，开发模式跳过；⑦LAUNCHER_VERSION 常量移到 core.py 作为单一来源，main.py 导入使用；⑧state.json 新增 launcher_last_check / pending_launcher_path / pending_launcher_version |
| **v1.2.0.1** | 同上 | 代码审查修复（d 升）：①**严重 bug 修复**：daemon_run() 调用 _check_and_download_launcher_update() 后未刷新 state 变量，后续 save_state(state) 用旧变量覆盖文件，导致 launcher 自我更新的 pending_launcher_path 状态丢失、自我更新形同虚设；修复为调用后重新 load_state()；②_wait_and_install() 不检查 install_from_path() 返回值，安装器成功但 exe 未写入（慢硬盘）时误判成功并清理状态；修复为返回 False 时保留状态下次重试；③ensure_installed() 重装分支缺少 None 检查，重装失败时返回 None 导致 launch_countdown() 中 Popen([None,...]) 崩溃；修复为加 None 检查抛 RuntimeError；④start_daemon() 开发模式下死代码清理（exe 变量设而不用），重构为 if/else 清晰分支 |

## 三、架构

```
IdiotLaunch.exe（单文件，PyInstaller onefile）
  ├─ tkinter GUI：四个大按钮 + 状态栏（关闭窗口→启动 daemon）
  ├─ core.find_installed_path()    检测安装（D盘优先 → 注册表 → 常见目录）
  ├─ core.get_installed_version()  读注册表 DisplayVersion / exe 文件版本
  ├─ core.install_from_path()      删除旧目录 → Inno /VERYSILENT /DIR=D:\CountdownDesktop
  ├─ core.launch_countdown()       CountdownDesktop.exe --exam zhongkao|gaokao（DETACHED_PROCESS）
  ├─ core.open_morning_reading()   webbrowser.open(https://zztool.free.nf/morning-reading)
  ├─ core.is_running()             互斥量 CountdownDesktop_Single 检测是否在运行
  ├─ core.quit_countdown()         OpenEvent(CountdownDesktop_Quit) + SetEvent → 优雅退出
  └─ 自动更新（v1.1.0.0）：
       core.daemon_run()            --daemon 守护进程：查GitHub→下载→等退出→静默安装
       core.start_daemon()          GUI关闭时启动 IdiotLaunch.exe --daemon（CREATE_NO_WINDOW）
       core.get_latest_version_info()  GitHub API 查询最新 release
       core.download_installer()    下载到 D:\CountdownDesktop_Updates\（.part→rename）
       core.load_state/save_state() state.json 持久化（D盘，不被冰点还原）
       core.install_pending_if_idle()  GUI启动时补装待更新
  └─ 启动器自我更新（v1.2.0.0）：
       core.get_latest_launcher_info()   GitHub API 查询 idiot-launch 最新 release
       core._check_and_download_launcher_update()  daemon中下载新版exe到UPDATE_DIR
       core.has_pending_launcher_update()   检查是否有待替换的更新
       core.apply_launcher_update_if_pending()  启动时生成VBS→退出→VBS覆盖旧exe→启动新版→自删除
       core._cleanup_stale_launcher_pending()  清理已过期的待更新记录
       LAUNCHER_VERSION 常量（core.py单一来源，main.py导入）
内嵌资源：_MEIPASS/installer/CountdownDesktop_Setup_<EMBEDDED_VERSION>.exe
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
14. **旧版不支持退出事件**：若运行的是旧版 Countdown Desktop（无 `CountdownDesktop_Quit` 事件），`OpenEventW` 返回 NULL，抛 RuntimeError 提示版本过旧。学校环境统一装最新版不存在此问题。

### 自动更新（v1.1.0.0）

15. **三层更新策略**：①内嵌保底版本（开箱即用，不等下载）；②关闭 GUI 后启动 `--daemon` 无窗口进程后台查 GitHub+下载；③下载完等 Countdown Desktop 退出后静默安装。三者结合保证既开箱即用又能自动跟进最新版。
16. **状态文件放 D 盘**：`D:\CountdownDesktop_Updates\state.json` 记录 last_check / pending_version / pending_installer / download_complete。C 盘冰点还原不影响 D 盘，重启后待安装更新依然有效。
17. **daemon 生命周期**：GUI 关闭时 `start_daemon()` 用 `DETACHED_PROCESS|CREATE_NO_WINDOW` 启动 `IdiotLaunch.exe --daemon`。daemon 流程：有待安装→等退出→安装→退出；无待安装且距上次检查<6h→直接退出；需检查→查GitHub→有新版→下载→等退出→安装；无新版→退出。最多等 2 小时，超时保留状态下次处理。
18. **下载容错**：`.part` 临时文件下载，完成后 rename；校验 Content-Length；失败不崩溃，状态保留下次重试。超时 10 分钟适配 GitHub 不稳定。
19. **安装前删旧目录**：`install_from_path()` 先 `shutil.rmtree(D:\CountdownDesktop)` 再运行 Inno Setup，确保干净升级（用户明确要求"删除原文件夹"）。需确保 Countdown Desktop 未运行（daemon 等退出后才装）。
20. **版本号比较**：`parse_version()` 容错处理 `v` 前缀和不足 4 段的版本号，`compare_versions()` 返回 -1/0/1。本地版本从注册表 DisplayVersion 读取，回退到 exe 文件版本信息（VerQueryValueW）。
21. **EMBEDDED_VERSION 单一来源**：core.py 中 `EMBEDDED_VERSION` 常量是内嵌版本的唯一真相，`INSTALLER_REL` 用 f-string 自动拼接文件名。升级内嵌版本只需改这一个常量 + 放新安装包 + 更新 build.ps1/release.yml 的下载 URL。
22. **启动时补装**：`_check_pending_update_on_start()` 在 GUI 启动时后台检查，若有待安装更新且 Countdown Desktop 未运行，立即安装（daemon 可能因倒计时一直开着没来得及装）。
23. **version_info.txt 发版必更**：每次发版必须同步更新 `version_info.txt` 中的 `filevers`、`prodvers`、`FileVersion`、`ProductVersion` 四处版本号，与 `main.py` 的 VERSION 保持一致。该文件注入 PE 元数据（公司名/产品名/版权），降低 SmartScreen 误报。spec 中 `version='version_info.txt'` 引用，`upx=False` 强制不压缩。
24. **单文件自我更新的两阶段方案**：Windows 不允许覆盖正在运行的 exe，因此采用"后台下载 + 启动时替换"两阶段。daemon 只负责下载和标记待更新，不尝试替换自己；替换在下次启动时由 VBScript 完成。VBScript 用 `wscript //B` 完全无窗口运行（bat 会闪黑框），每 500ms 重试 CopyFile（最多 15 秒）等待旧进程释放文件锁，成功后启动新版并自删除。
25. **自我更新不清除 pending 状态**：apply_launcher_update_if_pending() 退出前不清除 pending_launcher_path/version。如果 VBS 替换失败，下次启动再试；如果替换成功，新版运行时 LAUNCHER_VERSION 已更新，_cleanup_stale_launcher_pending() 检测到 pending 版本 <= 当前版本，自动清理文件和状态。这避免了"清除状态后替换失败导致永远丢失更新"的问题。
26. **自我更新仅 frozen 模式**：所有自我更新函数（has_pending_launcher_update、apply_launcher_update_if_pending、_check_and_download_launcher_update）开头都检查 `getattr(sys, "frozen", False)`，开发模式下直接返回。开发模式下 sys.executable 是 python.exe 而非 IdiotLaunch.exe，不能做自我替换。
27. **LAUNCHER_VERSION 单一来源**：版本号从 main.py 移到 core.py 的 LAUNCHER_VERSION 常量，main.py 用 `from src.core import LAUNCHER_VERSION` 导入。core.py 中的自我更新函数需要比较版本号，放在 core.py 避免循环导入（core.py 不 import main.py）。

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
├── build.ps1                   本地一键构建（venv + 下载安装包 + PyInstaller --noupx）
├── IdiotLaunch.spec            PyInstaller 规格（onefile + datas 内嵌 + upx=False + version 元数据）
├── version_info.txt            PE 版本元数据（公司名/产品名/版权/版本号，发版必更）
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

a=大添加 b=大改 c=小添加 d=小改动；去掉 `.` 后数值必须严格大于上一版本。当前最高已发布 tag：v1.2.0.1。

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
