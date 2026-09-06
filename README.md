# Idiot Launch（傻瓜启动器）

专为学校电脑设计的一键启动器：四个大按钮，点击即用，零配置。

- **中考倒计时** — 自动启动 Countdown Desktop（`--exam zhongkao`），未安装则静默安装到 D 盘
- **高考倒计时** — 自动启动 Countdown Desktop（`--exam gaokao`），未安装则静默安装到 D 盘
- **早晚读** — 在默认浏览器打开 `https://zztool.free.nf/morning-reading`
- **关闭倒计时** — 通过命名事件通知 Countdown Desktop 优雅退出（停壁纸、恢复桌面、退托盘）；未运行时按钮自动变灰不可点击

内嵌 Countdown Desktop v3.2.0.0 安装包，首次使用自动安装，无需手动下载。

## 为什么需要这个启动器？

学校电脑普遍安装**冰点还原（Deep Freeze）**，C 盘每次重启后恢复原状：

1. Countdown Desktop 装在 C 盘 → 重启后丢失，每次都要重装。
2. 本启动器将 Countdown Desktop **强制安装到 D 盘**（`D:\CountdownDesktop`），重启后依然存在。
3. 学生只需双击一个图标，点对应按钮即可，无需知道安装路径、命令行参数等技术细节。

## 运行环境

- Windows 10 / 11（x64 / ARM64）
- D 盘可用（安装 Countdown Desktop 所需，约 150 MB）
- 无需管理员权限（Countdown Desktop 安装包为 per-user 安装）

## 使用方法

1. 从 [Releases](https://github.com/tgcz2011/idiot-launch/releases) 下载 `IdiotLaunch.exe`。
2. 双击运行，出现四个大按钮：
   - 点击「中考倒计时」→ 自动安装（首次）并启动中考倒计时壁纸
   - 点击「高考倒计时」→ 自动安装（首次）并启动高考倒计时壁纸
   - 点击「早晚读」→ 浏览器打开早晚读网页
   - 点击「关闭倒计时」→ 强制退出所有 Countdown Desktop 进程，恢复桌面
3. 状态栏实时显示 Countdown Desktop 安装状态。

> 首次点击倒计时按钮时，会自动执行静默安装（约 10-30 秒），期间按钮暂时不可用，安装完成后自动启动。

## 工作原理

```
用户点击按钮
    │
    ├─ 检测 D:\CountdownDesktop\CountdownDesktop.exe 是否存在
    │   ├─ 存在 → 直接带参启动
    │   └─ 不存在 → 释放内嵌安装包 → /VERYSILENT /DIR=D:\CountdownDesktop 静默安装
    │
    ├─ 倒计时按钮 → CountdownDesktop.exe --exam zhongkao|gaokao
    ├─ 早晚读按钮 → webbrowser.open(https://zztool.free.nf/morning-reading)
    └─ 关闭倒计时 → OpenEvent(CountdownDesktop_Quit) + SetEvent（运行实例自行优雅退出）
       未运行时按钮自动变灰禁用（每 1.5s 轮询互斥量 CountdownDesktop_Single）
```

- **安装检测**：优先检查 `D:\CountdownDesktop`，其次扫描注册表卸载信息与常见安装目录。
- **静默安装**：使用 Inno Setup 标准参数 `/VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR=D:\CountdownDesktop`。
- **带参启动**：Countdown Desktop v3.2.0.0 支持 `--exam` 参数单次覆盖倒计时类型，内置单实例接管，重复点击自动切换。
- **进程独立**：使用 `DETACHED_PROCESS` 启动 Countdown Desktop，关闭启动器不影响倒计时运行。

## 开发与构建

技术栈：Python + tkinter（标准库，零第三方运行时依赖）+ PyInstaller 打包。

```powershell
# 本地一键构建（自动下载安装包 + 打包）
.\build.ps1 -Version 1.0.0.0

# 或分步
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 手动下载安装包到 installer\ 目录
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm IdiotLaunch.spec
```

发布：推送 tag `v<版本>`，GitHub Actions 自动构建并创建 Release。

## 项目结构

```
idiot-launch/
├── run.py                  入口
├── src/
│   ├── __init__.py         资源路径解析
│   ├── core.py             核心逻辑：安装检测/静默安装/带参启动/打开网页
│   └── main.py             GUI（tkinter，三大按钮 + 状态栏）
├── installer/              Countdown Desktop 安装包（构建时下载，不入库）
├── tools/                  辅助脚本
├── build.ps1               本地一键构建
├── IdiotLaunch.spec        PyInstaller 规格（内嵌安装包）
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
| Countdown Desktop 安装包 | v3.2.0.0 | [tgcz2011/countdown-desktop](https://github.com/tgcz2011/countdown-desktop) |

## License

GPL-3.0，见 [LICENSE](LICENSE)。
