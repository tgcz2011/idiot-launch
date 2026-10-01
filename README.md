# Idiot Launch（傻瓜启动器）

专为学校电脑设计的一键启动器：大按钮 + 侧边栏分类导航，点击即用，零配置。

## 功能

- **倒计时**（中考倒计时 / 高考倒计时）— 直接启动内置的 Countdown Desktop（已合并进本项目），按考试类型显示动态壁纸
- **自定义壁纸&屏保** — 启动用户自己配置的壁纸和屏保
- **关闭倒计时** — 通过命名事件通知 Countdown Desktop 优雅退出；未运行时按钮自动变灰不可点击
- **壁纸&屏保设置** — 一键唤起 Countdown Desktop 设置窗口（特供版，不含更新模块）
- **早晚读** — 应用内嵌浏览器打开 `https://zztool.free.nf/morning-reading`，支持班级登录自动进入、悬浮球快捷入口
- **早读设置** — 年级/班级/密码登录（先校验后保存）、持久/非持久登录、退出登录
- **倒计时 / 秒表** — Material Three 风格滚轮选择器，支持全屏模式、结束铃声、记次
- **随机抽学生** — 早读登录后可随机抽取学生（可自定义人数）
- **自动更新** — 守护进程常驻后台，空闲时静默更新；多镜像源 + 哈希校验

Countdown Desktop 代码已合并进本项目（特供版），不再单独安装、不再独立更新。

## 下载与安装

**推荐使用安装包**（`IdiotLaunch_Setup_*.exe`）：

1. 从 [Releases](https://github.com/tgcz2011/idiot-launch/releases) 下载 `IdiotLaunch_Setup_*.exe`。
2. 双击打开，安装程序自动开始（无需点击"下一步"），仅显示原生进度条。
3. 自动安装到 `D:\IdiotLaunch`，并在 **D 盘根目录**和**桌面**创建快捷方式。
4. 安装完成后自动启动。
安装后目录结构：

```
D:\IdiotLaunch\
├── IdiotLaunch.exe          # 启动器主程序
├── _internal\               # Python 运行时 + 资源（含 Countdown Desktop 合并代码）
│   ├── python314.dll
│   ├── _tkinter.pyd
│   ├── countdown_app\       # Countdown Desktop（特供版）
│   └── assets\              # 图标、铃声、语言文件
└── data\                    # 运行数据（state.json、daemon.log、早读配置、下载的更新包）
```

D 盘根目录仅保留一个 `傻瓜启动器.lnk` 快捷方式，不再散落其他文件夹。

> **唯一正式产物是安装包**（v1.5.0.0 起）`IdiotLaunch_Setup_<版本>.exe`：自动安装到 D 盘、创建快捷方式、基本不触发 SmartScreen。
> 自 v1.5.0.0 起 **GitHub Release 不再发布单文件版**（`IdiotLaunch.exe` 仅作为安装包内部 payload 存在）；
> 旧单文件用户仍可在空闲时自动迁移到安装版，存量兼容。
> **v1.7.0.0 起采用 PyInstaller onedir 模式**：安装后 `D:\IdiotLaunch\` 下包含 `IdiotLaunch.exe` + `_internal\` 子目录（Python 运行时、内嵌安装包、图标资源），目录结构与传统安装软件一致，启动更快（无需每次解压到临时目录），且安装后的文件无互联网下载标记，不触发 SmartScreen。

## 自动更新机制

### 守护进程常驻（前后端分离）

v1.3.0.0 起采用前后端分离架构：

- **前端（GUI）**：用户交互界面，关闭后不影响后台。
- **后端（Daemon）**：无窗口守护进程，启动器打开时自动启动，**关闭后继续常驻后台**，单实例运行（命名互斥量 `IdiotLaunch_Daemon_Single`）。
- **通信**：通过 `D:\IdiotLaunch\data\` 下的文件进行 IPC（`state.json` 状态、`command.json` 命令）。

频繁打开/关闭启动器不会中断更新流程，daemon 一直在后台运行。

### Countdown Desktop（已合并，无需单独更新）

自 v1.9.0.0 起，Countdown Desktop 的代码已直接合并进本项目（`countdown_app/` 目录），共享同一个 Python 运行时：

1. **不再单独安装**：启动中考/高考/壁纸设置即用同一个 `IdiotLaunch.exe`，带 `--countdown-app` 参数启动。
2. **不再单独更新**：内嵌特供版在设置"关于"页已移除更新模块，标注"已由傻瓜启动器统一管理"。
3. **配置存 D 盘**：通过环境变量 `COUNTDOWN_CONFIG_DIR=D:\IdiotLaunch\data\countdown` 规避冰点还原。
4. **统一管理**：启动时传入 `--auto-check-update off`，由 Idiot Launch 统一管理更新，避免重复检查。

### Idiot Launch 自身自动更新

1. **后台下载**：daemon 同时检查自身最新 Release，下载到 `D:\IdiotLaunch\data\IdiotLaunch_v<版本>.exe`。
2. **多镜像源 + 动态超时 + SHA-256 校验**：与 Countdown Desktop 更新使用同一套成熟机制（7 镜像源 fallback、动态超时 1x/2x/3x、SHA-256 校验）。
3. **空闲时静默更新（v1.3.1.0）**：daemon 每 30 秒检测系统空闲时间（`GetLastInputInfo` API），当电脑 **10 分钟无键盘/鼠标操作**时，自动触发静默更新：优雅关闭所有 IdiotLaunch 进程 → 静默安装新版 → 只重启 daemon（不启动 GUI，不打扰用户）→ VBS 自删除。整个过程无窗口、无弹窗。
4. **一键更新（v1.8.1.5）**：更新详情对话框里有绿色"立即更新"按钮，下载完成后点击即可立即更新并重启 GUI，不再需要等 10 分钟空闲。
5. **启动时更新（兜底）**：若电脑一直处于使用状态从未空闲，下次启动时仍会检测并应用更新，作为兜底机制。
6. **自适应文件名**：老师可把 exe 改名为任何名字（如"点我.exe"），更新后仍保留该名字。
7. **失败安全**：替换前先备份旧版，替换失败则自动恢复；无论成功失败都启动 daemon，不会丢失程序。

### 更新状态指示器

GUI 右上角有一个小圆圈，实时显示 daemon 活动状态：

- ⚪ 灰色 — 空闲 / 无更新
- 🟠 橙色 — 正在检查更新
- 🔵 蓝色 — 正在下载更新
- 🟣 紫色 — 正在安装更新
- 🟪 深紫 — 静默自我更新中
- 🟢 绿色 — 有更新待应用

点击圆圈弹出详情窗口：当前版本、待更新版本、更新日志、daemon 状态、下载源信息，并可手动触发"立即检查更新"。

### 快捷方式自动重建（流氓软件模式）

启动器每次启动时自动检查以下位置的快捷方式，不存在则立即重建：

- `D:\傻瓜启动器.lnk`（D 盘根目录）
- 当前用户桌面
- 公共桌面（`C:\Users\Public\Desktop`）

即使冰点还原清除了快捷方式，下次启动也会自动加回来。

## 为什么需要这个启动器？

学校电脑普遍安装**冰点还原（Deep Freeze）**，C 盘每次重启后恢复原状：

1. 传统软件装在 C 盘 → 重启后丢失，每次都要重装。
2. 本启动器将一切数据**安装到 D 盘**（`D:\IdiotLaunch`），重启后依然存在。
3. 学生只需双击一个图标，点对应按钮即可，无需知道安装路径、命令行参数等技术细节。

## 运行环境

- Windows 10 / 11（x64）
- D 盘可用（安装约 300 MB，含 Countdown Desktop 合并代码 + PySide6 浏览器运行时）
- 无需管理员权限（安装包 `PrivilegesRequired=lowest`）

## 使用方法

1. 双击桌面或 D 盘根目录的「傻瓜启动器」快捷方式。
2. 左侧分类导航选择功能（倒计时 / 工具 / 早读 / 设置），右侧大按钮点击即用：
   - 「中考倒计时」/「高考倒计时」→ 启动对应倒计时动态壁纸
   - 「关闭倒计时」→ 通知 Countdown Desktop 优雅退出，恢复桌面
   - 「早晚读」→ 内嵌浏览器打开早晚读网页（登录后自动进入班级页面）
   - 「倒计时」/「秒表」→ Material 风格计时工具（支持全屏）
   - 「随机抽学生」→ 早读登录后随机抽取学生
3. 右上角小圆圈显示更新状态，点击查看详情。

> 首次点击倒计时按钮时启动内置 Countdown Desktop（约数秒），无安装等待。

## 工作原理

```
用户点击按钮
    │
    ├─ 倒计时按钮 → IdiotLaunch.exe --countdown-app --exam zhongkao|gaokao
    │                （已有实例则通过命名事件切换考试类型）
    ├─ 壁纸设置   → IdiotLaunch.exe --countdown-app --settings（不启动壁纸）
    ├─ 早晚读     → IdiotLaunch.exe --morning-browser（PySide6 内嵌浏览器，独立进程）
    └─ 关闭倒计时 → OpenEvent(CountdownDesktop_Quit) + SetEvent（优雅退出）
       未运行时按钮自动变灰禁用（轮询互斥量 CountdownDesktop_Single）

后台 Daemon（常驻）
    │
    ├─ 每 1 小时检查 Idiot Launch 自身更新 → 多镜像下载 → 空闲 5 分钟静默安装
    ├─ 文件 IPC：state.json（状态）+ command.json（GUI→daemon 命令）
    └─ 日志：D:\IdiotLaunch\data\daemon.log（自动轮转 100KB）
```

## 开发与构建

技术栈：Python + tkinter（标准库，零第三方运行时依赖）+ PyInstaller 打包 + Inno Setup 安装包。

```powershell
# 本地一键构建（自动 venv + 下载安装包 + PyInstaller + Inno Setup）
.\build.ps1 -Version 1.3.0.0

# 或分步
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 手动下载安装包到 installer\ 目录
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm IdiotLaunch.spec
& "C:\Program Files\Inno Setup 6\ISCC.exe" IdiotLaunch.iss
```

构建产物（v1.5.0.0 起）：
- `dist\IdiotLaunch_Setup_<版本>.exe` — 安装包（50 MB，唯一正式交付形式，自动安装到 D:\IdiotLaunch）
- `dist\IdiotLaunch.exe` — 仅安装包内部 payload（48 MB，不再单独发布）

发布：推送 tag `v<版本>`，GitHub Actions 自动构建并创建 Release（同时上传两个文件）。

## 项目结构

```
idiot-launch/
├── run.py                  入口（无参=GUI，--daemon=后台守护进程）
├── src/
│   ├── __init__.py
│   ├── core.py             核心逻辑：安装/启动/退出/自动更新/daemon/快捷方式/多源下载
│   └── main.py             GUI（tkinter，四大按钮 + 更新指示器 + 状态栏）
├── assets/
│   ├── icon.ico            应用图标（多尺寸）
│   └── icon_source.png     图标源图
├── installer/              Countdown Desktop 安装包（构建时下载，不入库）
├── tools/                  辅助脚本（单元测试 test_core.py 等）
├── build.ps1               本地一键构建
├── IdiotLaunch.spec        PyInstaller 规格（内嵌安装包+图标+版本元数据，noUPX）
├── IdiotLaunch.iss         Inno Setup 安装脚本（自动安装到 D 盘，原生进度条）
├── version_info.txt        PE 版本元数据
├── requirements.txt        依赖（仅 pyinstaller）
├── .github/workflows/release.yml   tag→构建→Release
├── README.md / HANDOFF.md  文档（每次更新强制同步）
└── LICENSE                 GPL-3.0
```

## 版本号规则

`a.b.c.d`：d=小改动/修复，c=小添加，b=大改，a=大添加；去掉点后数值严格递增。

## 内嵌组件

| 组件 | 版本 | 来源 |
|------|------|------|
| Countdown Desktop 安装包 | v3.2.1.1 | [tgcz2011/countdown-desktop](https://github.com/tgcz2011/countdown-desktop) |

## License

GPL-3.0，见 [LICENSE](LICENSE)。
