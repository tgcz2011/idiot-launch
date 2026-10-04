# HANDOFF.md — 傻瓜启动器维护交接

> 最后更新：v3.0.0.0-beta26 之后的一次大整改（窗口管理重写、更新链路去掉 VBS、
> 主题/透明度/日志重构）。本文档描述**当前代码**，不是历史版本的回忆录。

## 一、这是什么

给学校教室电脑用的启动器：一键启动倒计时壁纸、打开早晚读网页、倒计时/秒表、随机抽学生，
自带后台静默更新。目标用户是不会看技术文档的老师，使用场景是有冰点还原、网络受限、
学生可能乱点的公用电脑。

三条设计铁律（改代码前请先接受它们）：

1. **必须装在 D 盘**、安装过程不提问、装完自动开——这是给老师省事，不是懒。
2. **快捷方式会被自动重建**、关闭窗口不退出程序——这是对抗冰点还原和学生误删，不是流氓。
3. **任何后台行为都要在「设置 → 程序在后台做了什么」里如实写出来**——老师有知情权，
   网管也需要能解释"这个进程在干什么"。

## 二、进程与线程模型（最容易踩坑的地方）

```
IdiotLaunch.exe（Flutter 前端，主窗口 + 倒计时/秒表子窗口，同一个进程）
        │  HTTP 127.0.0.1:<随机端口>（端口写在 %TEMP%\idiot_launch_backend_port）
        ▼
IdiotLaunchBackend.exe --server（后端进程）
        ├─ 主线程：ThreadingHTTPServer 提供 /api/*
        ├─ daemon 线程：更新检查/下载、空闲静默更新、快捷方式守护、残留清理、早读时间段刷新
        ├─ 托盘线程：pystray（pystray.Icon.run() 阻塞在这个线程里）
        └─ 悬浮球线程：tkinter mainloop
        │
        ├─ 子进程：IdiotLaunchBackend.exe --countdown-app ...（壁纸/屏保，DETACHED_PROCESS）
        └─ 子进程：IdiotLaunchBackend.exe --morning-browser（早晚读浏览器，DETACHED_PROCESS）
```

要点：

- **前端和后端是两个进程**。前端点 ✕ 只是 `windowManager.hide()`；后端和 daemon 继续跑。
- **安装目录里 `IdiotLaunch.exe` 是 Flutter 前端，`backend\IdiotLaunchBackend.exe` 是后端**。
  壁纸和早晚读浏览器都是**后端 exe** 带着不同参数启动的，所以 `taskkill /IM IdiotLaunchBackend.exe`
  会一次把它们全杀掉（安装/卸载/退出时正是靠这一点）。
- **托盘"退出"必须用 `os._exit(0)`**。`sys.exit()` 在非主线程里只结束那个线程——
  这就是历史 bug「点了退出、图标消失、进程还在」的根因。
- **单实例**有三层：后端启动前先探测已有端口是否活着（`_another_backend_alive`）；
  daemon 用命名互斥量 `IdiotLaunch_Daemon_Single`；前端用 `instance.pid` + `OpenProcess`。
  互斥量判断必须用 `ctypes.WinDLL('kernel32', use_last_error=True)` + `ctypes.get_last_error()`——
  直接用 `windll` 读 `GetLastError()` 可能拿到过期值，会让两个 daemon 同时认为自己是唯一实例，
  表现出来就是同一个 205MB 更新包被并发下载两遍（线上日志里真实出现过）。

### 子窗口（倒计时/秒表）的硬性约束

`desktop_multi_window` 的子窗口由**进程主线程**创建并拥有，而 Dart 的 UI 线程不是窗口线程。
对别的线程拥有的窗口调用 `SendMessage`（WM_CLOSE / WM_SETTEXT）或**不带**
`SWP_ASYNCWINDOWPOS` 的 `SetWindowPos`，会同步等待窗口线程处理消息；
窗口线程处理 WM_CLOSE 时又会回头找 Dart → 两边互等 → 界面"未响应"。

所以 `lib/sub_window.dart` 里：

- 关闭窗口用 `PostMessage`（异步投递）；
- 移动/缩放一律带 `SWP_ASYNCWINDOWPOS`；
- 设标题用 `SendMessageTimeoutW` + `SMTO_ABORTIFHUNG`。

**窗口身份必须由父窗口推下来，不能让子窗口自己找**（beta27 实测事故：同时开倒计时和秒表时，
两个子窗口选中了同一个 HWND —— 拖 A 会移动 B，另一个窗口永远保持插件的
800x600 + 原生标题栏）：

- 父窗口 `_createToolWindow`：串行创建 → 创建前后各枚举一次本进程顶层窗口 →
  差集里那个就是新子窗口的 HWND → 用窗口通道 `invokeMethod('set_hwnd', ...)` 推给子窗口
  （子窗口可能还没注册好通道，要重试）。
- 子窗口在 `main()` 里注册 `setWindowMethodHandler` 收 HWND，拿到之后才 `runApp`
  （`TimerPage(hwnd: ...)`）。
- 窗口用 `hiddenAtLaunch: true` 创建，`SubWindow` 改完样式再自己 `ShowWindow`
  —— 不会先闪一下 800x600 的原生标题栏窗口。
- 拿不到 HWND 时回退到"本进程 + 标题为空"的搜索，并且**无论如何都会让窗口显示出来**
  （宁可样式不对，也不能让用户点了没反应）。

另外：创建子窗口要起一个新的 Flutter 引擎，这一步跑在进程主线程上，主窗口会短暂无响应
（1-2 秒）—— 调用方必须先弹 loading 并在文案里说明，这是"看起来卡死"和"明确告知"的区别。

**不要在别处重复实现这些调用。**

## 三、数据与状态

全部在 `D:\IdiotLaunch\data`（`src/core.py` 的 `UPDATE_DIR`）：

| 文件 | 内容 | 说明 |
|------|------|------|
| `state.json` | 更新状态、daemon 状态、pending 安装包路径、`tray_hint_boot` | 读写都要加 `_state_lock`，多线程读改写会互相覆盖 |
| `settings.json` | `theme` / `auto_update` / `telemetry` / `show_tray_hint` | 前端设置页写入 |
| `command.json` | 前端 → daemon 的命令（原子写 + 读完即删） | |
| `morning_config.json` | 早读班级配置（密码混淆存储） | 另有 `%TEMP%\idiot_launch_morning_config.json`（非持久登录） |
| `morning_api_cache.json` | 早读 token / 挑战 cookie | 退出登录会清空 |
| `daemon.log` | 守护进程日志（256KB 轮转 3 份） | 排障第一现场 |
| `ui.log` | 前端日志（512KB 轮转 1 份） | |
| `backend.log` / `morning.log` / `countdown.log` | 各入口的 logging 输出 | 打包后 stderr 是 None，不写文件就等于没有日志 |
| `telemetry.log` | 上报内容本地留档 | 网络不通时也能查"上报了什么" |
| `IdiotLaunch_Setup_*.exe` | 下载好的更新包 | 安装后会清理，daemon 每小时还会清残留 |

## 四、更新链路（已去掉 VBS）

**旧方案的问题**（务必不要退回去）：用 `wscript` 跑一个 VBS 脚本替换文件。
脚本是 daemon 的子进程，而安装包里的 `taskkill /T` 会顺着进程树**把脚本自己杀掉**，
于是写结果文件、校验、重启、清理全部没执行——线上残留的 `update_result.txt` 永远停在
`status=running`。而且 `/VERYSILENT` 全程无界面，被 SmartScreen 拦下时用户什么都看不到。

**现在的流程**（`src/core.py`）：

1. daemon 每小时（启动后距上次超过 10 分钟也会）查一次版本：
   Supabase `latest_version` 表 → GitHub `/tags` → `/releases` → 302 重定向，逐级兜底。
2. 有新版本 → 后台线程用 aria2 从 11 个源并发下载到 `data\IdiotLaunch_Setup_<版本>.exe`
   → 校验 SHA-256 → 写 `pending_launcher_path` → 托盘弹一次"更新已就绪"。
3. 安装触发方式二选一：
   - 用户点横幅「一键更新」→ `POST /api/update/install` → 后端**先回包**，
     再起线程 `start_update_installer(silent=False)` 用 `/SILENT` 启动安装包
     （显示安装包自带的进度条），然后 `os._exit(0)` 让出文件；
   - 空闲自动更新 → daemon 连续 3 次确认空闲（阈值 10 分钟）后
     用 `/VERYSILENT` 静默启动安装包并退出。
4. 两者都带 `/AutoUpdate=1`。安装脚本 `[Code]` 里 `IsAutoUpdate` 检测到这个参数后，
   在 `ssPostInstall` 阶段把程序重新拉起来。安装包的 `PrepareToInstall` 里
   `taskkill /F /IM` **不带 `/T`**（带 `/T` 会杀掉安装包自己）。

改这块时请重点验证：更新后进程能自动回来、安装包会被清理、失败时不至于让程序再也起不来。

## 五、目录与关键文件

```
run.py                    统一入口：--server / --daemon / --quit / --quit-daemon
                          / --countdown-app / --morning-browser（无参数时弹提示并退出）
src/core.py               版本、设置、日志、状态、早读、壁纸启动、下载、更新、daemon 主循环
src/backend_server.py     HTTP API（见下）、托盘、悬浮球、进程退出
src/morning_config.py     早读配置读写（加解密、原子写、持久/临时两套路径）
src/morning_api_client.py 早读 API（内嵌 AES 过 InfinityFree 挑战；call() 返回 (ok, data, err)）
src/morning_browser.py    早晚读内嵌浏览器（配置只从文件读，绝不放命令行）
src/floating_button.py    悬浮球（左键开、左键拖动、右键菜单）
src/aria2_downloader.py   aria2 JSON-RPC 封装
src/telemetry.py          匿名上报（每日行数上限 + 同类去重 + 本地留档）
countdown_app/            Countdown Desktop 特供版（win32/media/player/main/settings/config/cli）
flutter_app/lib/          前端（main / timer_page / sub_window / api / theme / format / cd_settings_page）
tools/                    版本号与元数据生成、资源生成、单元测试
```

### HTTP API 一览

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/version` | 存活探测（前端 ping 用） |
| GET | `/api/status` | 版本/壁纸状态/登录状态/daemon 活动/下载进度/设置 |
| GET/POST | `/api/settings` | 读取/保存设置 |
| GET | `/api/morning/config` | 早读登录状态与时间段 |
| GET | `/api/morning/students` | 学生名单（失败时 `success=false` + 中文原因） |
| POST | `/api/morning/login` / `logout` / `open` | 登录（先校验后保存）/ 退出登录（连缓存一起清）/ 打开浏览器 |
| GET | `/api/update/status` | 更新状态（含 `pending_ready`、`last_check_at`） |
| POST | `/api/update/check` / `install` | 触发检查 / 一键更新 |
| GET/POST | `/api/cd/config` | 壁纸&屏保配置（POST 返回 `restart_required`） |
| POST | `/api/countdown/start` / `stop` / `custom` / `settings` | 启动/关闭壁纸等 |
| POST | `/api/notify` | 托盘气泡（`once_per_boot=true` 时每次开机只弹一次） |
| POST | `/api/activate` / `/api/activate/clear` | 单实例激活已有窗口 |
| POST | `/api/open-folder` | 资源管理器打开目录 |
| POST | `/api/quit` | 后端整体退出（安装/卸载前调用） |

响应统一 `application/json; charset=utf-8`，`Access-Control-Allow-Origin` 只允许 `http://127.0.0.1`。

## 六、发布流程

```powershell
python tools/bump_version.py 3.0.0.0-beta27   # 同步 core.py / .iss / pubspec / PE 元数据
.\build.ps1 -SkipFlutter                       # 本地快速验证后端与安装包
git tag v3.0.0.0-beta27 && git push origin v3.0.0.0-beta27
```

CI（`.github/workflows/release.yml`）会：

1. 校验 **tag 与 `LAUNCHER_VERSION` 一致**（不一致直接失败——否则会发出"客户端永远收不到更新"的版本）；
2. 生成 PE 元数据 → 跑 `tools/test_core.py` → `flutter analyze` / `flutter test`；
3. PyInstaller 打包后端 → Flutter 构建前端 → ISCC 编译安装包；
4. 计算**按版本号命名的**安装包的 SHA-256，连同 `.sha256` 文件一起上传 Release；
5. 把版本/下载地址/哈希写进 Supabase `latest_version`（客户端只从这里查更新）。

`version_info.txt` / `version_info_backend.txt` **不入库**，构建时生成，避免出现"元数据停留在
某个历史版本"的经典事故。

## 七、已知取舍与待办

- **创建倒计时/秒表窗口时，主窗口会短暂无响应（1-2 秒）**：`desktop_multi_window`
  在进程主线程上创建新的 Flutter 引擎，这一步无法异步化。现在会先弹 loading 并写明
  "会短暂无响应"。想彻底消除只能做引擎预热池（启动时先把两个子窗口建好但隐藏），
  代价是启动更慢、常驻内存更高，暂不做。
- **安装包约 200MB**：PySide6/QtWebEngine + 两个中文字体是大头。想显著变小需要把壁纸/早晚读
  拆成独立可选组件，属于产品决策，暂时不动。
- **早读密码只做了混淆**（XOR+Base64，密钥在代码里）。同一台电脑的其他账号能还原。
  已如实写在设置页；真要加固应改用 Windows DPAPI，但老师把 D 盘拷到另一台电脑后就解不开了，
  需要产品上取舍。
- **桌面壁纸恢复**依赖 `SPI_SETDESKWALLPAPER`，会把"幻灯片/纯色"桌面固定成当前那张静态图。
- **屏保空闲判定**只看键鼠输入，播放教学视频超过阈值也会被屏保盖住（这是屏保的语义，未改）。
- **early-reading 站点**是第三方免费空间，靠 JS 挑战 + 页面结构自动登录；对方改版会导致
  自动登录失效（能打开网页和首页，只是不会自动进班）。
- **死代码已清理**：`src/main.py`（旧 tkinter 界面）、`src/timer_dialog.py`、
  `countdown_app/update.py`（CD 自带更新器）、`IdiotLaunch.spec`、`tools/edge_test*.py` 等。
  如果哪天要恢复旧 GUI，请从 git 历史里取。

## 八、改代码时的检查清单

- [ ] 改了版本号相关文件？跑一遍 `tools/bump_version.py`，别手改。
- [ ] 改了后端接口？同步更新 `flutter_app/lib/api.dart` 和本文件第五节的表格。
- [ ] 碰了子窗口？确认没有新增阻塞式 Win32 调用（见第二节）。
- [ ] 碰了进程退出？确认托盘退出、安装前退出、`--quit` 三条路径都能真的结束进程。
- [ ] 加了后台行为？在「设置 → 程序在后台做了什么」里加一条说明。
- [ ] 提交前：`python tools/test_core.py`、`cd flutter_app; dart analyze; flutter test`。
