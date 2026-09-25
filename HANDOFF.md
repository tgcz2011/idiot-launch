# HANDOFF.md — Idiot Launch 交接文档

> 最后更新: 2026-09-24（v1.4.0.0，前后端分离 daemon 常驻 + 多镜像源下载 fallback + Inno Setup 安装包 + 快捷方式自动重建 + 更新状态指示器 + 自定义图标）

## 一、需求（用户原始要求）

1. 制作一个傻瓜式启动器软件，代码托管到 GitHub（仓库 `tgcz2011/idiot-launch`），使用规范提交过程。
2. 交接文档、README 等规范参考 `tgcz2011/countdown-desktop` 仓库。
3. 将 Countdown Desktop 的安装包**内嵌**到本软件中。
4. 用户点击「中考倒计时」→ 带参数命令启动 Countdown Desktop（`--exam zhongkao`）；未安装则用安装包静默安装。
5. 点击「高考倒计时」→ 同理（`--exam gaokao`）。
6. 点击「早晚读」→ 打开网页 `zztool.free.nf/morning-reading`。
7. 学校电脑装了冰点还原，C 盘会重置，**Countdown Desktop 必须安装到 D 盘**。
8. 一键关闭 Countdown Desktop（用命名事件优雅退出，不 taskkill；未运行时按钮变灰）。
9. Countdown Desktop 自动更新（内嵌保底 + 后台下载 + 退出时静默安装）。
10. 启动器自身自动更新（单文件、后台静默、原位置替换、支持任意文件名）。
11. 安装过程有进度弹窗，防止老师误以为卡死。
12. 版本元数据 + noUPX 降低 SmartScreen 误报。
13. 多镜像源下载 fallback（GitHub 直连 → gh-proxy → ghfast → ghproxy），超时 15 分钟。
14. 前后端分离：daemon 常驻后台，GUI 频繁开关不中断更新。
15. 快捷方式自动重建（D 盘根目录 + 桌面，"流氓软件"模式）。
16. Inno Setup 安装包（自动安装到 D 盘，原生进度条，基本不弹 SmartScreen）。
17. GUI 右上角更新状态小圆圈，点击显示详情。
18. 自定义图标（用户提供手指点击图案）。

## 二、版本历史

| 版本 | 技术 | 结论 |
|------|------|------|
| **v1.0.0.0** | Python + tkinter + PyInstaller | 初始版本，三按钮 + 内嵌安装包 + D 盘静默安装 |
| **v1.0.0.1** | 同上 | 新增「关闭倒计时」按钮：taskkill /F /T 终止进程树 + 桌面刷新（d 升） |
| **v1.0.0.2** | 同上 | 关闭按钮改用 Countdown Desktop 命名事件 `CountdownDesktop_Quit` 优雅退出；未运行时按钮自动变灰禁用（每 1.5s 轮询互斥量 `CountdownDesktop_Single`）；HoverButton 新增 disabled 视觉态（d 升） |
| **v1.0.0.3** | 同上 | 内嵌 Countdown Desktop 安装包从 v3.2.0.0 升级至 v3.2.1.1（d 升） |
| **v1.1.0.0** | 同上 | 完整自动更新体系（c 升）：内嵌保底 + 关闭后 daemon 后台下载 + 退出时静默安装 + 启动时补装 + D 盘状态持久化 |
| **v1.1.1.0** | 同上 | 新增安装进度弹窗 ProgressDialog（c 升）：置顶、无关闭按钮、indeterminate 进度条 |
| **v1.1.2.0** | 同上 | 版本元数据 + 强制 noUPX（c 升）：version_info.txt 注入 PE 元数据，spec 中 upx=False |
| **v1.2.0.0** | 同上 | Idiot Launch 自身后台静默更新（b 升）：daemon 下载新版 + 启动时 VBS 替换 + 原位置原文件名 + 失败安全 |
| **v1.2.0.1** | 同上 | 代码审查修复（d 升）：daemon 状态丢失 bug、安装返回值检查、None 检查 |
| **v1.2.0.2** | 同上 | 全面代码审查（d 升）：VBS 替换失败恢复旧版、OpenMutexW 替代 CreateMutexW 消除竞态 |
| **v1.2.0.3** | 同上 | 自适应文件名（d 升）：VBS 改用 UTF-16 LE BOM 编码支持中文路径，用户可任意改名不影响更新 |
| **v1.3.0.0** | 同上 + Inno Setup | **前后端分离 + 安装包 + 多源下载 + 快捷方式 + 更新指示器（b 升，大改）**| **v1.4.0.1** | 同上 | 快捷方式守护移到 daemon 循环顶部（d 升）：原实现 ensure_shortcuts() 在下载函数之后，下载阻塞期间快捷方式无法恢复；修复后实测删除 D盘+桌面快捷方式 35 秒内自动重建 |
| **v1.8.0.1** | 同上 | 修复 v1.8.0.0 中"壁纸设置"按钮未创建的 bug：①main.py 添加 btn_settings 按钮（紫色 #8e44ad）和 on_settings() 方法；②窗口高度从 660 增至 780 以容纳第 5 个按钮；③29 项测试全过 |
| **v1.8.0.0** | 同上 | 新增"壁纸设置"按钮 + 内嵌 Countdown Desktop 升至 v3.2.3.0（b 升）：①core.py 加 launch_settings()，调用 CountdownDesktop.exe --settings；②main.py 加紫色"壁纸设置"按钮（BTN_SETTINGS=#8e44ad）；③Countdown Desktop v3.2.3.0 新增 --settings 参数和 CountdownDesktop_ShowSettings 命名事件：已有实例运行时发事件弹出设置（不关闭倒计时、不接管），无实例时启动并自动弹出设置；④build.ps1 从 core.py 动态读取 EMBEDDED_VERSION（Select-String），spec 也动态读取，避免升级时手动同步；⑤29 项测试全过 |
| **v1.7.0.0** | 同上 | onedir 模式 + 目录归拢（b 升）：①PyInstaller 从 onefile 改 onedir，安装后 D:\IdiotLaunch\ 下有 IdiotLaunch.exe + _internal\ 子目录（Python 运行时+内嵌安装包+资源），像传统安装软件，启动更快（无需每次解压到 %TEMP%），安装后文件无 Zone.Identifier 不触发 SmartScreen；②Countdown Desktop 安装目录从 D:\CountdownDesktop 归拢到 D:\IdiotLaunch\CountdownDesktop，D 盘根目录只留傻瓜启动器.lnk；③新增 _migrate_old_countdown_dir() 自动迁移旧目录（ensure_installed 开头调用）；④spec 加 exclude_binaries=True + COLLECT；⑤Inno Setup [Files] 改 recursesubdirs 打包整个目录；⑥build.ps1/CI 产物验证路径改 dist\IdiotLaunch\IdiotLaunch.exe；⑦29 项测试全过 |
| **v1.6.0.1** | 同上 | 已存在完整安装包分支也做哈希校验（d 升）：原"大小匹配直接标记 pending/跳过下载"分支绕过校验，若本地文件被破坏会直接待更新；现该分支也 verify_sha256，不通过删除并重新下载 |
| **v1.6.0.0** | 同上 | 哈希校验 + UI 重做（b 升）：①GitHub Release 发布时用 Get-FileHash 计算安装包 SHA-256 写入 release body（steps.hash.outputs.sha256）；本地 get_latest_* 从 API asset.digest 取哈希，两个下载 worker（launcher/countdown）下载完成后 verify_sha256 校验，不匹配删除安装包、拒绝更新并重新下载（无 digest 的旧 release 跳过校验兼容）；②右上角指示器重做为环形进度条：背景环+进度环+中心内容（空闲=淡灰环+灰点，下载中=蓝环+实时百分比，待更新=绿环+↑），daemon monitor 传 progress；③_download_single 每 512KB 上报下载进度百分比；④29 项单元测试 |
| **v1.5.0.0** | 同上 | 产品形态与并发架构大改（b 升）：①Countdown Desktop 更新流程全线程化——下载/等待退出(最长2h)/静默安装都在后台线程执行，daemon 主循环永不被阻塞（原 _wait_and_install 最长阻塞 2h、下载同步阻塞）；②主循环末尾不再覆盖后台 downloading/updating/installing/waiting 状态；③**弃用单文件版**：GitHub Release 只发安装包（files 只留 IdiotLaunch_Setup_*.exe），IdiotLaunch.exe 仅作安装包 payload；④Inno Setup 覆盖安装加固：CloseApplications=yes + CloseApplicationsFilter=IdiotLaunch.exe + RestartApplications=yes（手动升级时自动关停旧进程、装完恢复启动），删除无用的 [Tasks] 死代码；⑤build.ps1 支持 Inno Setup 7；⑥27 项单元测试 |
| **v1.4.0.2** | 同上 | 下载线程化（d 升）：①Idiot Launch 安装包下载放后台线程，不阻塞 daemon 循环（快捷方式守护/命令响应/Countdown 更新检查不被拖住）；②直连源 60s 短超时快速失败切镜像（原所有源统一 900s，慢速直连会白等 15 分钟）；③DOWNLOAD_MIRRORS 结构改为 (前缀, 超时) 元组 |
| **v1.4.0.0** | 同上 | 自我更新改为安装包模式（b 升）：①自我更新不再替换单文件，改为下载 `IdiotLaunch_Setup_<版本>.exe` 并 /VERYSILENT 静默安装到 D:\IdiotLaunch；②便携版用户自动迁移到安装版（检测 sys.executable != LAUNCHER_INSTALL_EXE 时下载安装包完成迁移）；③get_latest_launcher_info 只匹配安装包资产；④快捷方式守护加入 daemon 循环（每 30 秒检查 D 盘根目录+桌面，缺失即重建），真正实现"流氓软件"模式；⑤ensure_shortcuts 优先指向安装版；⑥GUI 便携版提示（检测到已安装版本时提醒用快捷方式打开）；⑦25 项单元测试 |
| **v1.3.1.0** | 同上 | 空闲时静默自我更新（c 升）：①daemon 用 GetLastInputInfo API 检测系统空闲时间，10 分钟无操作即触发静默更新；②VBS 优雅关闭所有进程（taskkill 不带/F）→ 备份旧 exe→替换→只重启 daemon 不启动 GUI→自删除，全程无窗口无弹窗；③启动时更新保留为兜底机制；④新增 get_idle_seconds()、apply_launcher_update_idle()、IDLE_THRESHOLD=600 常量；⑤更新指示器新增"updating"深紫色状态；⑥22 项单元测试：①daemon 从"一次性执行后退出"改为 while True 常驻循环，通过命名互斥量 `IdiotLaunch_Daemon_Single` 保证单实例；GUI 启动时即启动 daemon（不再等关闭），关闭后 daemon 继续后台运行；②文件 IPC：`state.json` 的 daemon 字段传递状态（activity/progress/detail/timestamp/pid），`command.json` 传递 GUI→daemon 命令（如 check_updates）；③多镜像源下载：DOWNLOAD_MIRRORS 列表（直连→gh-proxy.com→ghfast.top→ghproxy.net），每源 3 次重试，重试间隔 30 秒，超时从 600s 改为 900s（15 分钟）；④快捷方式自动重建：ensure_shortcuts() 在 frozen 模式下确保 D:\傻瓜启动器.lnk、用户桌面、公共桌面三个位置存在，用 PowerShell WScript.Shell COM 创建；⑤Inno Setup 安装包 IdiotLaunch.iss：DefaultDirName=D:\IdiotLaunch，DisableDirPage/DisableReadyPage/DisableFinishedPage=yes，CurPageChanged 自动跳过欢迎页直接安装（保留原生进度条），PrivilegesRequired=lowest，Uninstallable=no，安装后创建 D 盘根目录+桌面快捷方式并自动启动；⑥更新状态指示器 UpdateIndicator：GUI 右上角 Canvas 小圆圈，颜色随 daemon 活动变化（灰=空闲/橙=检查/蓝=下载/紫=安装/绿=有更新），点击弹出 UpdateDetailDialog 显示版本/更新日志/daemon 状态/下载源/手动检查按钮；⑦自定义图标 assets/icon.ico（多尺寸 16/32/48/64/128/256，用户提供手指点击图案去白底生成），spec 加 icon 参数，安装包 SetupIconFile 引用；⑧daemon 日志 log_daemon() 写 D:\IdiotLaunch\data\daemon.log，自动轮转 100KB；⑨CI 增加 choco install innosetup + ISCC 编译 + 同时上传 exe 和安装包；⑩build.ps1 自动检测 ISCC.exe 并编译安装包 |

## 三、架构

```
IdiotLaunch.exe（单文件，PyInstaller onefile）或 IdiotLaunch_Setup.exe（Inno Setup 安装包）
  │
  ├─ 前端 GUI（tkinter）：
  │   ├─ 四个大按钮（中考/高考/早晚读/关闭倒计时）
  │   ├─ 右上角 UpdateIndicator（更新状态小圆圈，点击→UpdateDetailDialog）
  │   ├─ 状态栏（安装状态 + daemon 活动）
  │   ├─ 启动时：start_daemon() 确保 daemon 运行 + ensure_shortcuts() 确保快捷方式
  │   └─ 关闭时：daemon 已常驻，仅作安全网确认
  │
  ├─ 后端 Daemon（--daemon，无窗口，while True 常驻）：
  │   ├─ _acquire_daemon_mutex() 单实例（命名互斥量 IdiotLaunch_Daemon_Single）
  │   ├─ 主循环：处理 command.json 命令 → 检查 launcher 更新 → 检查 pending 安装
  │   │   → 每 6 小时检查 Countdown Desktop 更新 → 多源下载 → 等退出 → 静默安装
  │   ├─ set_daemon_status() 写 state.json 的 daemon 字段（GUI 读取显示）
  │   ├─ log_daemon() 写 daemon.log（自动轮转 100KB）
  │   └─ 睡眠 30 秒/轮，期间每 5 秒检查一次 command.json
  │
  ├─ 文件 IPC（D:\IdiotLaunch\data\）：
  │   ├─ state.json    — 持久化状态（last_check, pending_installer, pending_launcher_path, daemon{}）
  │   ├─ command.json  — GUI→daemon 命令（如 {"cmd":"check_updates"}），daemon 读取后删除
  │   └─ daemon.log    — daemon 运行日志
  │
  ├─ 核心功能（core.py）：
  │   ├─ find_installed_path()    检测安装（D盘优先 → 注册表 → 常见目录）
  │   ├─ get_installed_version()  读注册表 DisplayVersion / exe 文件版本
  │   ├─ install_from_path()      删除旧目录 → Inno /VERYSILENT /DIR=D:\CountdownDesktop
  │   ├─ launch_countdown()       CountdownDesktop.exe --exam zhongkao|gaokao（DETACHED_PROCESS）
  │   ├─ open_morning_reading()   webbrowser.open(https://zztool.free.nf/morning-reading)
  │   ├─ is_running()             OpenMutexW(CountdownDesktop_Single) 检测运行
  │   ├─ quit_countdown()         OpenEvent(CountdownDesktop_Quit) + SetEvent → 优雅退出
  │   ├─ download_installer()     多源循环下载（直连→3镜像，每源3次重试，900s超时）
  │   ├─ ensure_shortcuts()       D盘根目录+桌面快捷方式自动重建（PowerShell COM）
  │   └─ 自动更新体系（见下方）
  │
  └─ 内嵌资源：_MEIPASS/installer/CountdownDesktop_Setup_<EMBEDDED_VERSION>.exe
              _MEIPASS/assets/icon.ico
```

### 自动更新体系

**Countdown Desktop 更新**：
1. daemon 每 6 小时调 `get_latest_version_info()` 查 GitHub API
2. 有新版 → 后台线程 `download_installer()` 多源下载到 `D:\IdiotLaunch\data\`（不阻塞主循环）
3. 下载完成 → 标记 `pending_installer` + `download_complete=True`
4. 后台线程 `_countdown_install_worker()` 等 Countdown Desktop 退出（最多 2 小时）→ 删旧目录 → 静默安装（主循环照常运行）
5. GUI 启动时 `install_pending_if_idle()` 补装（daemon 可能因倒计时一直开着没装）

**Idiot Launch 自身更新**：
1. daemon 每 6 小时调 `get_latest_launcher_info()` 查自身 GitHub API
2. 有新版 → `download_installer()` 多源下载到 `D:\IdiotLaunch\data\IdiotLaunch_v<ver>.exe`
3. 标记 `pending_launcher_path` + `pending_launcher_version`
4. 下次启动时 `apply_launcher_update_if_pending()` 生成 UTF-16 LE BOM 编码的 VBS → 退出 → VBS 覆盖旧 exe → 启动新版 → 自删除
5. `_cleanup_stale_launcher_pending()` 自动清理已过期（版本<=当前）的待更新记录

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

### 带参启动

- `CountdownDesktop.exe --exam zhongkao` — 中考倒计时
- `CountdownDesktop.exe --exam gaokao` — 高考倒计时
- Countdown Desktop v3.2.1.1 内置单实例接管，重复点击自动切换。
- 使用 `DETACHED_PROCESS`（0x00000008）创建子进程，启动器关闭不影响倒计时运行。

### 多镜像源下载

```python
DOWNLOAD_MIRRORS = [
    "",                          # GitHub 直连
    "https://gh-proxy.com/",     # 镜像 1
    "https://ghfast.top/",       # 镜像 2（实测最快）
    "https://ghproxy.net/",      # 镜像 3
]
```
- 每个源超时 900 秒（15 分钟）
- 全部源失败后重试，最多 3 轮，轮间间隔 30 秒
- `.part` 临时文件下载，完成后 rename，校验 Content-Length

### Inno Setup 安装包（v1.3.0.0 新增）

- `DefaultDirName=D:\IdiotLaunch`，`DisableDirPage=yes`（不允许改路径）
- `DisableReadyPage=yes` + `DisableFinishedPage=yes` + `CurPageChanged` 自动跳过欢迎页
- 用户双击安装包后直接开始安装，仅显示原生进度条（无需点"下一步"）
- `PrivilegesRequired=lowest` 免管理员
- `Uninstallable=no`（学校环境不需要卸载）
- 安装后自动创建 D 盘根目录快捷方式（Pascal Code 中 WScript.Shell）+ 桌面快捷方式（[Icons] 段）
- 安装完成后自动启动 IdiotLaunch.exe
- `SetupIconFile=assets\icon.ico` 安装包图标

## 四、踩过的错误 / 经验

### 内嵌大文件与 Git

1. **安装包不入库**：Countdown Desktop 安装包约 39 MB，不提交到 Git（`.gitignore` 排除 `installer/*.exe`）。构建时由 `build.ps1` 或 GitHub Actions 自动下载。

### tkinter 打包

2. **tkinter 是标准库**：无需额外 pip 安装，PyInstaller 自动识别。`requirements.txt` 仅含 `pyinstaller`。
3. **`console=False`**：GUI 程序必须关闭控制台。

### 学校环境适配

4. **D 盘强制安装**：Inno Setup 的 `/DIR=` 参数可覆盖默认路径。
5. **冰点还原**：C 盘重启后重置，D 盘通常不受保护。安装路径、更新状态、daemon 日志均在 D 盘。
6. **无需管理员**：Countdown Desktop 和 Idiot Launch 安装包均 `PrivilegesRequired=lowest`。

### 进程管理

7. **DETACHED_PROCESS**：让子进程完全独立于启动器。
8. **单实例接管**：Countdown Desktop 自己处理单实例。

### 一键关闭

9. **命名事件优雅退出**：`OpenEventW(CountdownDesktop_Quit)` + `SetEvent`，不 taskkill。
10. **OpenMutexW 而非 CreateMutexW**：后者会创建互斥量，微秒级窗口内 Countdown Desktop 启动会误判已有实例。
11. **按钮变灰**：GUI 每 1.5s 后台线程调 `is_running()`，回主线程更新按钮状态。

### 自动更新

12. **三层更新策略**：内嵌保底 + daemon 后台下载 + 退出时静默安装。
13. **daemon 常驻（v1.3.0.0）**：从"一次性执行后退出"改为 while True 循环。GUI 启动时即启动 daemon，关闭后继续运行。单实例通过命名互斥量保证。频繁开关 GUI 不影响更新。
14. **文件 IPC（v1.3.0.0）**：daemon 状态写 state.json 的 daemon 字段（带 timestamp，GUI 端 5 分钟过期判定），命令通过 command.json 传递（daemon 读取后删除）。比命名管道/套接字简单可靠，且 D 盘持久化。
15. **多源下载（v1.3.0.0）**：GitHub 直连在校园网极慢（实测 ~55KB/s，48MB 需 15 分钟），镜像源 ghfast.top 实测最快。4 个源循环 + 3 轮重试 + 900s 超时 = 最坏情况 4×3×15min = 3 小时，但实际通常第一个镜像就成功。
16. **快捷方式自动重建（v1.3.0.0）**：ensure_shortcuts() 每次启动检查 D 盘根目录+用户桌面+公共桌面。用 PowerShell `WScript.Shell` COM 创建 .lnk。frozen 模式才执行（开发模式跳过）。即使冰点还原清除快捷方式，下次启动自动加回。
17. **Inno Setup 自动安装（v1.3.0.0）**：`CurPageChanged` 中检测 `wpWelcome` 时自动调用 `NextButton.OnClick`，配合所有页面 Disable，实现"打开即装"但保留进度条。用户实测安装包形式基本不弹 SmartScreen。
18. **Inno Setup 7 兼容性**：`ArchitecturesInstallIn64BitMode=x64` 在 IS7 中已弃用，改用 `x64compatible`。`GetDriveType` 不是内置函数，用 `DirExists('D:\')` 替代。
19. **状态文件放 D 盘**：冰点还原不影响。
20. **下载容错**：`.part` 临时文件 + Content-Length 校验 + 失败保留状态。
21. **安装前删旧目录**：`shutil.rmtree` 确保干净升级。
22. **版本号比较**：`parse_version()` 容错处理 `v` 前缀和不足 4 段。
23. **EMBEDDED_VERSION 单一来源**：升级内嵌版本只需改常量 + 放新安装包 + 更新下载 URL。
24. **version_info.txt 发版必更**：四处版本号（filevers/prodvers/FileVersion/ProductVersion）必须同步。
25. **单文件自我更新两阶段**：后台下载 + 启动时 VBS 替换。VBS 用 `wscript //B` 无窗口，UTF-16 LE BOM 编码支持中文路径。
26. **自我更新不清除 pending**：替换成功后新版运行时 `_cleanup_stale_launcher_pending` 自动清理。
27. **自我更新仅 frozen 模式**：开发模式下 `sys.executable` 是 python.exe，不能做自我替换。
28. **LAUNCHER_VERSION 单一来源**：放在 core.py 避免循环导入。
29. **更新状态指示器（v1.3.0.0）**：Canvas 绘制圆圈，颜色映射 daemon activity。有 pending 更新时强制绿色。点击弹出详情窗口，包含手动检查更新按钮（通过 send_command("check_updates") 通知 daemon）。
30. **自定义图标（v1.3.0.0）**：用户提供手指点击图片，Pillow 去白底 + 裁剪 + 生成多尺寸 ICO。spec 加 `icon='assets/icon.ico'`，datas 加 `("assets", "assets")` 确保运行时 iconbitmap 能找到。

## 五、项目结构

```
idiot-launch/
├── run.py                      入口（无参=GUI，--daemon=守护进程；GUI前先检查自我更新）
├── src/
│   ├── __init__.py             resource_path（打包资源路径解析）
│   ├── core.py                 核心逻辑（安装/启动/退出/自动更新/daemon/快捷方式/多源下载/日志）
│   └── main.py                 GUI（tkinter，四按钮 + UpdateIndicator + UpdateDetailDialog + 状态栏）
├── assets/
│   ├── icon.ico                应用图标（多尺寸 16/32/48/64/128/256）
│   └── icon_source.png         图标源图（用户提供）
├── installer/
│   └── CountdownDesktop_Setup_3.2.1.1.exe  （构建时下载，gitignore）
├── tools/
│   └── test_core.py            单元测试（20 项）
├── build.ps1                   本地一键构建（venv + 下载 + PyInstaller + Inno Setup）
├── IdiotLaunch.spec            PyInstaller 规格（onefile + 内嵌安装包+图标 + upx=False + version 元数据）
├── IdiotLaunch.iss             Inno Setup 安装脚本（自动安装到 D 盘，原生进度条）
├── version_info.txt            PE 版本元数据（发版必更四处版本号）
├── requirements.txt            pyinstaller
├── .gitignore                  排除 venv/build/dist/installer/*.exe
├── .github/workflows/release.yml   tag→构建（PyInstaller + Inno Setup）→Release（双文件上传）
├── README.md                   用户文档
├── HANDOFF.md                  本文档（每次更新强制同步）
└── LICENSE                     GPL-3.0
```

## 六、toolchain

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | 开发机 3.14；CI 3.12 | tkinter 标准库 |
| PyInstaller | 6.x | onefile 打包，内嵌安装包+图标 |
| Inno Setup | 7.x | 安装包编译（ISCC.exe） |
| Pillow | 开发用 | 图标处理（去白底、生成 ICO） |
| git / gh | 已登录 tgcz2011 | 推送与 release |
| GitHub Actions | windows-latest | 自动构建发布（choco 装 innosetup） |

## 七、构建与发布

```powershell
# 本地构建（自动 venv + 下载安装包 + PyInstaller + Inno Setup）
.\build.ps1 -Version 1.3.0.0
# 产物：dist\IdiotLaunch.exe（48MB）+ dist\IdiotLaunch_Setup_1.3.0.0.exe（50MB）

# 发布
git add -A
git commit -m "v1.3.0.0: daemon常驻 + 多源下载 + Inno Setup安装包 + 快捷方式重建 + 更新指示器"
git tag v1.3.0.0
git push origin main v1.3.0.0
# GitHub Actions 自动构建并创建 Release（同时上传 exe 和安装包）
```

## 八、版本规则

a=大添加 b=大改 c=小添加 d=小改动；去掉 `.` 后数值必须严格大于上一版本。当前最高已发布 tag：v1.3.2.0（v1.4.0.0 发布中）。

## 九、已知限制 / 待办

1. **D 盘不存在时报错**：安装包会弹窗提示并中止；单文件版静默安装失败。
2. **安装包版本固定**：当前内嵌 v3.2.1.1，升级需更新常量 + 安装包 + 下载 URL。
3. **早晚读用系统默认浏览器**：学校电脑可能被组策略锁定。
4. **tkinter 界面较朴素**：功能优先，保持零运行时依赖。
5. **daemon 无 GUI 退出入口**：daemon 设计为常驻后台，用户无法从 GUI 停止 daemon（如需停止需任务管理器结束 IdiotLaunch.exe 进程）。这是有意设计——保证更新不中断。
6. **快捷方式重建仅在启动时**：如果运行期间快捷方式被删除，需重启启动器才会重建。未来可在 daemon 循环中加入定期检查。
7. **GitHub API 速率限制**：未认证请求 60 次/小时/IP。daemon 每 6 小时检查一次（两个项目各一次），远低于限制。学校多台电脑共用公网 IP 时可能触发，但 6 小时间隔足够宽松。

## 十、验证方法备忘

```powershell
# 1. 单元测试
python tools/test_core.py

# 2. 源码运行（需先下载安装包到 installer\）
python run.py

# 3. 构建后运行
.\dist\IdiotLaunch.exe

# 4. 安装包测试（自动安装到 D:\IdiotLaunch）
.\dist\IdiotLaunch_Setup_1.3.0.0.exe
# 检查 D:\IdiotLaunch\IdiotLaunch.exe、D:\傻瓜启动器.lnk、桌面快捷方式

# 5. 验证静默安装 Countdown Desktop
.\installer\CountdownDesktop_Setup_3.2.1.1.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR=D:\CountdownDesktop

# 6. 验证带参启动
D:\CountdownDesktop\CountdownDesktop.exe --exam zhongkao
D:\CountdownDesktop\CountdownDesktop.exe --exam gaokao

# 7. 验证 daemon 常驻
# 启动 IdiotLaunch 后关闭 GUI，任务管理器中应仍有 IdiotLaunch.exe 进程
# 查看 D:\IdiotLaunch\data\daemon.log

# 8. 验证多源下载
# 断开 GitHub 直连（修改 hosts），daemon 应自动 fallback 到镜像源
```
