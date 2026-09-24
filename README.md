# Idiot Launch（傻瓜启动器）

专为学校电脑设计的一键启动器：四个大按钮，点击即用，零配置。

- **中考倒计时** — 自动启动 Countdown Desktop（`--exam zhongkao`），未安装则静默安装到 D 盘
- **高考倒计时** — 自动启动 Countdown Desktop（`--exam gaokao`），未安装则静默安装到 D 盘
- **早晚读** — 在默认浏览器打开 `https://zztool.free.nf/morning-reading`
- **关闭倒计时** — 通过命名事件通知 Countdown Desktop 优雅退出；未运行时按钮自动变灰不可点击

内嵌 Countdown Desktop v3.2.1.1 安装包，首次使用自动安装，无需手动下载。

## 下载与安装

**推荐使用安装包**（`IdiotLaunch_Setup_*.exe`）：

1. 从 [Releases](https://github.com/tgcz2011/idiot-launch/releases) 下载 `IdiotLaunch_Setup_*.exe`。
2. 双击打开，安装程序自动开始（无需点击"下一步"），仅显示原生进度条。
3. 自动安装到 `D:\IdiotLaunch`，并在 **D 盘根目录**和**桌面**创建快捷方式。
4. 安装完成后自动启动。

> **唯一正式产物是安装包**（v1.5.0.0 起）`IdiotLaunch_Setup_<版本>.exe`：自动安装到 D 盘、创建快捷方式、基本不触发 SmartScreen。
> 自 v1.5.0.0 起 **GitHub Release 不再发布单文件版**（`IdiotLaunch.exe` 仅作为安装包内部 payload 存在）；
> 旧单文件用户仍可在空闲时自动迁移到安装版，存量兼容。

## 自动更新机制

### 守护进程常驻（前后端分离）

v1.3.0.0 起采用前后端分离架构：

- **前端（GUI）**：用户交互界面，关闭后不影响后台。
- **后端（Daemon）**：无窗口守护进程，启动器打开时自动启动，**关闭后继续常驻后台**，单实例运行（命名互斥量 `IdiotLaunch_Daemon_Single`）。
- **通信**：通过 `D:\IdiotLaunch\data\` 下的文件进行 IPC（`state.json` 状态、`command.json` 命令）。

频繁打开/关闭启动器不会中断更新流程，daemon 一直在后台运行。

### Countdown Desktop 自动更新

1. **内嵌保底版本**：每个发行版内嵌一个 Countdown Desktop 安装包，首次使用开箱即用。
2. **后台检查下载**：daemon 每 6 小时检查 GitHub 最新版，发现新版后后台下载。
3. **多镜像源 fallback**：下载依次尝试 GitHub 直连 → gh-proxy.com → ghfast.top → ghproxy.net，每个源超时 15 分钟，最多重试 3 轮，适配校园不稳定网络。
4. **倒计时退出时静默更新**：下载完成后等待 Countdown Desktop 退出，退出后删除旧目录并静默安装新版。
5. **启动时补装**：若倒计时一直开着，下次启动时若已下载且未运行则立即补装。
6. **状态持久化**：`D:\IdiotLaunch\data\state.json` 记录所有状态，冰点还原不影响。

### Idiot Launch 自身自动更新

1. **后台下载**：daemon 同时检查自身最新 Release，下载到 `D:\IdiotLaunch\data\IdiotLaunch_v<版本>.exe`。
2. **空闲时静默更新（v1.3.1.0）**：daemon 每 30 秒检测系统空闲时间（`GetLastInputInfo` API），当电脑 **10 分钟无键盘/鼠标操作**时，自动触发静默更新：优雅关闭所有 IdiotLaunch 进程 → 备份旧 exe → 替换为新版 → 只重启 daemon（不启动 GUI，不打扰用户）→ VBS 自删除。整个过程无窗口、无弹窗。
3. **启动时更新（兜底）**：若电脑一直处于使用状态从未空闲，下次启动时仍会检测并应用更新（生成 VBS → 退出 → 替换 → 重启），作为兜底机制。
4. **自适应文件名**：老师可把 exe 改名为任何名字（如"点我.exe"），更新后仍保留该名字。
5. **失败安全**：替换前先备份旧版为 `.bak`，替换失败则自动恢复；无论成功失败都启动 daemon，不会丢失程序。

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

1. Countdown Desktop 装在 C 盘 → 重启后丢失，每次都要重装。
2. 本启动器将 Countdown Desktop **强制安装到 D 盘**（`D:\CountdownDesktop`），重启后依然存在。
3. 学生只需双击一个图标，点对应按钮即可，无需知道安装路径、命令行参数等技术细节。

## 运行环境

- Windows 10 / 11（x64）
- D 盘可用（安装 Countdown Desktop 约 150 MB，Idiot Launch 约 60 MB）
- 无需管理员权限（安装包 `PrivilegesRequired=lowest`）

## 使用方法

1. 双击桌面或 D 盘根目录的「傻瓜启动器」快捷方式。
2. 出现四个大按钮：
   - 点击「中考倒计时」→ 自动安装（首次）并启动中考倒计时壁纸
   - 点击「高考倒计时」→ 自动安装（首次）并启动高考倒计时壁纸
   - 点击「早晚读」→ 浏览器打开早晚读网页
   - 点击「关闭倒计时」→ 通知 Countdown Desktop 优雅退出，恢复桌面
3. 状态栏实时显示 Countdown Desktop 安装状态。
4. 右上角小圆圈显示更新状态，点击查看详情。

> 首次点击倒计时按钮时，会自动执行静默安装（约 10-30 秒），期间显示进度弹窗，安装完成后自动启动。

## 工作原理

```
用户点击按钮
    │
    ├─ 检测 D:\CountdownDesktop\CountdownDesktop.exe 是否存在
    │   ├─ 存在 → 版本检查（低于内嵌版则删旧重装）→ 直接带参启动
    │   └─ 不存在 → 释放内嵌安装包 → /VERYSILENT /DIR=D:\CountdownDesktop 静默安装
    │
    ├─ 倒计时按钮 → CountdownDesktop.exe --exam zhongkao|gaokao (DETACHED_PROCESS)
    ├─ 早晚读按钮 → webbrowser.open(https://zztool.free.nf/morning-reading)
    └─ 关闭倒计时 → OpenEvent(CountdownDesktop_Quit) + SetEvent（优雅退出）
       未运行时按钮自动变灰禁用（每 1.5s 轮询互斥量 CountdownDesktop_Single）

后台 Daemon（常驻）
    │
    ├─ 每 6 小时检查 Countdown Desktop 更新 → 多源下载 → 等退出 → 静默安装
    ├─ 每 6 小时检查 Idiot Launch 自身更新 → 下载安装包 → 空闲 10 分钟静默安装（迁移到安装版）
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
