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

**窗口拖动的坑：Flutter 不给屏幕绝对坐标**（beta28、beta29 两轮都栽在这，
最后靠真机实测才定位）：

- Flutter 手势给的指针坐标是**相对窗口**的（`position`/`globalPosition` 在子窗口里
  都是视口坐标，不是屏幕坐标）。窗口一跟着指针动，指针相对窗口的位置就跟着变：
  - 用绝对位置算 → 窗口动 30px 又弹回原位。实测（`tools/probe_drag.ps1`）：
    鼠标走 300px，窗口只走 179px，中间来回跳；
  - 用 `delta` 累加 → 解差分方程 `d_k = M_k - d_{k-1}`，稳定收敛到"每步只走一半"。
    实测反向 FAST-BACK 正好 -150px / 期望 -300px。
  这两条都不是算错，是**相对坐标里推不出指针的屏幕绝对位置**，信息不足。
- 正确做法（`SubWindow.dragTarget`，都有单测）：
  1. **鼠标**：拖动开始时 `GetCursorPos` 记下屏幕坐标，之后每次更新再 `GetCursorPos`
     做差 → `origin + (cursorNow - cursorStart)`。屏幕坐标里窗口自己走了多少完全不影响，
     实测 10 步 300px 误差 ≤1px，快速甩动（事件合并）也精确。
  2. **触摸/触控笔**：没有光标坐标，用**重建**：`窗口当前位置 + (局部坐标 - 起点) × dpr`。
     窗口自己动多少就补回多少，反馈被抵消，同样 1:1。
- **不要自己 `SetCapture`/`ReleaseCapture`**：Flutter 的 Windows embedder 已经在
  `WM_LBUTTONDOWN` 时 `SetCapture`、`WM_LBUTTONUP` 时 `ReleaseCapture`
  （`flutter_window.cc`，注释写着 "Capture the pointer in case the user drags
  outside the client area"）。自己再调一次只会把它的捕获还回去 —— beta30 实测踩过：
  拖动开始时 `ReleaseCapture`，快速反向甩动时窗口纹丝不动（事件全投给了别的窗口）。
- 逻辑像素 → 物理像素仍要乘 `devicePixelRatio`（`SubWindow.attach(scale: dpr)`），
  这条单独成立：不乘的话 125% 缩放只走 80%。
- `WM_NCLBUTTONDOWN/HTCAPTION`（`window_manager.startDragging` 那套系统移动循环）
  在 `desktop_multi_window` 的子窗口上**不生效**（实测：消息被处理但模态循环没起来，
  `SendMessageTimeoutW` 立刻返回）。代码里仍然先试一次（别的环境可能可用，
  能用就是最跟手的），失败自动退回上面的逐帧拖动并记一条 info 日志。

**倒计时选时长必须允许鼠标/触摸拖动**（beta29 实测"手指按在滚轮上拖没反应"）：

- Flutter 桌面端默认 `ScrollBehavior.dragDevices` **不含 mouse**（桌面习惯是滚轮），
  而教室里的希沃把手指触摸提升成鼠标消息 → 拖动完全没反应；
- 所以 `widgets/duration_picker.dart` 里显式 `ScrollConfiguration(...dragDevices: 全部指针类型)`；
- 单测必须用 `startGesture(kind: PointerDeviceKind.mouse)` 才抓得到这个 bug
  （`tester.drag` 默认是 touch，会假通过 —— 这个坑真踩过。

**按钮图标的颜色要按"平时状态"校验**（beta29 实测"关闭 × 在浅色模式下看不见"）：
关闭按钮平时用 `onSurfaceVariant`（深灰），只有悬停底色变红时才换成 `onError`；
`onError` 在浅色模式下是白色，平时叠在白底上就是白底白字。
`test/contrast_test.dart` 现在把图标字形也纳入校验（`includeIcons: true`），
故意把 `onError` 换回平时状态时该测试会失败（浅色 1.04:1、深色 1.42:1）。

**真机验证拖动的方法**（比"改完看着像对"可靠得多，值得每次动拖动时跑一遍）：

1. `flutter build windows --debug`，用 `IDIOT_LAUNCH_AUTO_WINDOW=timer`
   （或 `stopwatch`）启动 `build\windows\x64\runner\Debug\IdiotLaunch.exe`，
   3 秒后自动打开工具窗口；
2. 跑 `tools/probe_drag.ps1`（在 `D:\idl`，不进仓库）：把子窗口 `SetWindowPos` 抬到最前
   （否则主窗口会把鼠标事件全吃掉），`mouse_event` 按下 → 分 10 步移动 30px →
   每步读 `GetWindowRect` 和期望值比较 → 松手，再反向甩一次（验证事件合并）；
3. 通过标准：每步误差 ≤ 几 px、`END moved` 与期望一致。
   注意 pwsh 是 DPI-unaware：截图是**物理**像素，`GetWindowRect`/`SetCursorPos` 是
   虚拟化坐标，两者差一个系统缩放（这台机器 1.25）。

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
   下载过程中**每一步进度都要写进 `state.launcher_download`**（`set_download_state`），
   界面横幅的百分比只看这个字段。历史上它只在开始/结束写两次，于是界面永远是 0%
   （用户实测"自动更新下载始终是 0%"）。
   `/api/status`、`/api/update/status` 返回的 `download_progress` 是 **0~1 的小数**
   （前端乘 100 显示；以前后端给 0~100、前端又乘 100）。
   下载被打断（关程序/装更新/断网）后状态会停在 `downloading`，
   `get_download_state()` 用 `updated_at` 超过 `DOWNLOAD_STALE_SECONDS` 判为 `interrupted`，
   daemon 启动时也会清一次，避免界面永远显示"正在后台下载"。
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

### 「更新检查」曾经十几年如一日地静默失败（beta32 修）

用户装机实测：**beta29 坚信自己是最新版**（界面横幅一直是"当前已是最新版本"），
而 Supabase 里 `is_latest=true` 的记录早就是 beta31 了。两个独立原因叠在一起：

1. `_http_json` 给**所有**请求都加了 `Accept: application/vnd.github+json`
   （GitHub 专用媒体类型）。发给 Supabase 的 PostgREST 直接被判 406：
   `PGRST107: None of these media types are available: application/vnd.github+json`。
   主渠道（不限流的那条）从此一次都没成功过。
   GitHub 的 REST API 一样接受 `application/json`，所以统一改成通用 JSON。
2. 打包 workflow 把 `secrets.GITHUB_TOKEN` 写进了 `src/_secrets.py`。
   那是 **Actions 的临时令牌，构建一结束就失效**，却被打进了 exe：
   装机之后每个 GitHub API 调用都 401，兜底渠道也是废的。
   现在只接受可选的长期 `UPDATER_PAT`；没有就按未认证走（60 次/小时够用）。
   另外 `_github_json()` 带 token 失败会**去掉 token 重试一次**。

而 `_http_json` 当年把异常整个吞掉（`except Exception: return None`），
`get_latest_launcher_info()` 又用 None 同时表示"是最新"和"没查成"，
于是界面永远显示"已是最新" —— 一句谎话把两个 bug 一起藏了很久。

现在的规矩（改更新逻辑必须保持）：

- `_http_json` **失败必须记日志**（含主机、HTTP 码、响应体前 200 字），不许静默返回 None。
- `get_latest_launcher_info()` 之后一定读 `last_check_result()`：
  `{ok: True/False/None, detail}`。None = 本进程还没查过。
  只有 `ok is True` 才能对用户说"已是最新"，否则界面说"检查更新失败"。
  daemon 会把结果存进 `state.launcher_check_ok / launcher_check_detail`，
  `/api/status`、`/api/update/status` 透给前端（`check_ok`、`check_detail`）。
- 回归测试在 `tools/test_core.py::TestUpdateCheckChannel`：
  Accept 头不许是 GitHub 专用类型、Supabase 有新版本必须认、全渠道失败必须报
  `ok=False`、Supabase 回答"就是最新"必须报 `ok=True`、token 失效要能降级重试。
- 排查线上"查不到更新"的第一站永远是 `data\daemon.log`：
  现在每次失败都会写清是哪个渠道、什么错。

### 更新链路的健壮性补丁与 β 版试用（v3.0.0.0 后续）

**1. 装完有看门狗了（之前没有）**
`start_update_installer` 现在返回安装包 pid，`apply_launcher_update_if_pending` 会调
`_spawn_relaunch_watchdog(pid)` 起一个**独立的 powershell.exe**：等安装包退出后，
若程序没在跑就把 `D:\IdiotLaunch\IdiotLaunch.exe` 拉起来。
为什么必须用 powershell 而不是自己守：安装包会 `taskkill /F /IM IdiotLaunchBackend.exe`，
任何用这个 exe 跑的守卫都会被一起杀掉。日志落在 `data\update_watchdog.log`。
覆盖三种情况：装成功且安装包已重启（看门狗什么都不做）、装成功但 [Code] 没重启（看门狗拉起）、
装失败/被拦（看门狗把旧程序拉回来，至少不让"点一下更新软件就没了"）。

**2. aria2c 不再变孤儿**
后端退出走 `os._exit(0)`，会绕过 `download_with_aria2` 的 `finally`，
以前会留下继续下载的孤儿 aria2c。现在 `src/aria2_downloader.py` 用
**kill-on-job-close 的 Job Object** 把 aria2c 绑到本进程：本进程一死，Windows 自动带走它。
另外把 pid 写到 `data\aria2.pid`，daemon 启动时 `kill_orphan_aria2` 兜底清理
（只杀映像名确实是 `aria2c.exe` 的那个 pid，不按名字盲杀）。

**3. 下载前先探活镜像**
`DOWNLOAD_MIRRORS` 只是候选池；`download_installer` 先 `pick_working_mirrors(url)`
并发（`Range: bytes=0-0` 只取 1 字节）探测每个前缀，只把**当前真的连得上**的、
按延迟排序的源交给 aria2。死源（ghproxy.com / ghps.cc 这类早已停服的）不再拖慢首包。
全探不通才回退整表，最后仍有 SHA-256 兜底。

**4. β 版试用开关（`beta_trial`）**
`DEFAULT_SETTINGS` 里的 `beta_trial` 是三态：`None` 未选（按构建版本）、`True`、`False`。
渠道由 `effective_beta_channel()` 决定，`get_latest_launcher_info` 用它取代原来的
`is_beta_version(LAUNCHER_VERSION)`。副作用在后端 `/api/settings` 里处理：
- 开（`begin_beta_trial`）：置 `force_check` + `auto_install_ready`，
  立即检查、下载好就装（`apply_launcher_update_if_pending` 见到 `auto_install_ready`
  就跳过空闲判定直接装，显示安装进度条）。
- 关（`end_beta_trial`）：停查 β、丢掉待装的 β 包，并立即检查一次。
  因为 `compare_versions` 里同号正式版 > 预发布版，它会自然等到一个 ≥ 当前主版本的
  正式版出现才升级过去，不会退回更老的正式版。
回归测试：`tools/test_core.py::TestBetaTrialChannel`。

### 3.0.1.0-beta1 追加的健壮性 / 体验补丁

- **单实例改用命名互斥量**（`flutter_app/lib/main.dart`）：原来用 `instance.pid` + `OpenProcess`
  判"是否已有实例"，PID 会被系统复用 → 误判。现在用 `CreateMutexW("Global\IdiotLaunch_SingleInstance")`
  + `GetLastError()==183`，更可靠；互斥量句柄持有到进程结束。`instance.pid` 仍然写（后端结束前端时要用）。
  互斥量创建失败时回退老的 PID 逻辑。
- **快捷方式改为目录监听**（`src/core.py::_start_shortcut_watcher` / `_watch_one_dir`）：
  用 `ReadDirectoryChangesW` 监听 D 盘根目录和公共桌面，被删即刻补（对抗冰点还原更及时），
  不再每 30 秒轮询。监听启动失败会自动退回原来的 30 秒轮询；有监听时保留 5 分钟低频兜底。
- **下载不再误判为"已中断"**（`src/core.py::get_download_state`）：只要下载线程还活着就不判死。
  系统休眠 / 主循环卡顿会让 `updated_at` 长时间不动，之前会被误报。
- **前端单次轮询 + 变更才重建**（`flutter_app/lib/main.dart::_pollStatus`）：`/api/status` 已含更新字段
  （补了 `pending_version`），不再每 5 秒串行打两个接口；状态没变化就不 `setState`（整页重画）。
- **界面更"活"**：`theme.dart` 支持传入种子色，`main.dart` 读 Windows 强调色
  （`HKCU\...\DWM\ColorizationColor`）当种子；`BigButton` 重做（悬停抬起 / 按下回缩 / 彩色投影 / 水波纹）；
  侧边导航改为自绘（选中项有会动的圆角药丸背景，参考 FlClash）；切页与更新横幅加了过渡动画。
  对比度回归测试（`contrast_test.dart`）不受影响。
- `IdiotLaunch.iss`：`SolidCompression=yes`（安装包更小）。

### 3.0.1.0-beta1 之后的体验 / 健壮性改动

- **倒计时启动加载态对齐**：`/api/status` 新增 `countdown_ready`；countdown 进程把壁纸
  挂上桌面后写 `data/countdown/wallpaper.ready`（`countdown_app/player.py`）；
  前端 `_launchWallpaper` 轮询到 ready 才收起"正在启动…"动画（之前后端一返回就收，
  动画一闪而过、壁纸还在慢悠悠地起）。
- **秒表窗口**改为紧凑横向长方形（660×200，像希沃白板），记次改为横向滚动的小胶囊。
- **精度**：倒计时本就精确到秒；秒表 `formatStopwatch` 改为 `mm:ss.mmm`（毫秒），
  主显示与计次一致。
- **去掉多余提示文字**：时长选择器的"上下拖动数字选时间…"、秒表的空态提示都删了；
  倒计时只在"暂停/超时"时显示状态词（运行时不再显示"倒计时中"）。
- **首次关闭**只用 Windows 通知（`notifyTray`），删掉了应用内"已最小化到托盘"对话框。
- **单实例唤起**：再次点快捷方式时，已最小化的主窗口会先 `restore()` 再 show/focus
  （之前只 `show()`，被最小化的窗口唤不起来）。
- **遥测补短板**：`backend_server._install_crash_reporting()` 挂上
  `sys.excepthook` / `threading.excepthook`，未捕获异常会上报（之前 `report_error`
  定义了却没人调用）；daemon 主循环异常也上报；`update_check` 事件带上 `check_detail`
  （失败原因），不再只看到"失败了"。

### 3.0.1.0-beta2：切页动效 + 工具窗口预热

- **切页改为 shared-axis**：页面区用 `animations` 包的 `PageTransitionSwitcher` +
  `SharedAxisTransition(horizontal)`（右进左出淡入），更接近 FlClash 的手感。
- **工具窗口预热池**（`main.dart`）：子窗口每次点击都要在主线程新建 Flutter 引擎
  （1-2 秒，期间主窗口"未响应"）。现在启动后 4 秒在后台建好一个**隐藏**的预热窗口
  （`arguments="$pid:prewarm"`），点「倒计时/秒表」时只发一条 `use` 消息让它变身并显示，
  主线程不再现场建引擎。复用失败/没有预热窗口时回退到原来的 `_createToolWindow`，
  行为与之前一致。  子窗口侧 `_PrewarmHost` 负责等待 `set_hwnd`（父窗口推 HWND）与 `use`。

### 计时 / 秒表体验修复（在 beta2 之后）

- **倒计时支持精确到秒**：`DurationPicker` 新增 `showSeconds` + 秒滚轮（`TimerPage` 打开），
  显示 `hh:mm:ss`（避免 "00:30" 到底指 30 秒还是 30 分）。
- **秒表窗口布局修复**：窗口改 700×260，时间行与记次行高度**写死**（不再被压没），
  记次是横向滚动的胶囊。之前 660×200 太矮，记次那一行被挤没了。
- **全屏重做（倒计时 & 秒表）**：全屏时**隐藏标题栏**，只留"大号时间 + 操作 + 退出全屏键
  （Esc 也能退）"；时间用 `FittedBox` 铺满并随窗口放大（之前全屏字不放大）。见
  `_buildFullscreen` / `_toggleFullscreen` / `_exitFullscreen`。
- **全屏时压住 countdown 屏保**：计时/秒表全屏时用一个命名互斥量
  `IdiotLaunch_ToolFullscreen` 告诉 countdown"别弹屏保"（壁纸不受影响）。
  启动器侧见 `flutter_app/lib/fullscreen_guard.dart`（全屏 acquire、退出/关窗/崩溃 release）；
  countdown 侧见 `countdown_app/main.py::_tool_fullscreen_active`（`_idle_tick` 里判断）。
- 回归测试：`duration_picker_test` 增加"秒滚轮 + hh:mm:ss"。

### 真全屏 + 早晚读全屏 + 导航栏按钮修复

- **真全屏**：`sub_window.toggleFullscreen` 进入全屏时用 **HWND_TOPMOST** 置顶，
  才能真正盖住任务栏（之前只把窗口铺到 `rcMonitor`，而任务栏也是 topmost，
  照样压在上面 —— 就是"伪全屏"，看着跟最大化没区别）；退出时恢复 z 序
  （开了"置顶"保持置顶，否则还原）。
- **计时/秒表全屏保留最上方操作键**：全屏布局改回顶部带 `_WindowBar`
  （置顶/全屏/最小化/关闭 都在），中间大号时间铺满，底部操作键。
- **早晚读浏览器加"全屏"键**：`morning_browser._toggle_fullscreen`（`showFullScreen`
  /`showNormal`，Esc 退出），工具栏保留所以随时能操作/退出。
- **侧边导航按钮修形**：`_NavRail` 的 Column 加 `crossAxisAlignment: stretch` ——
  之前按钮宽度只按内容（图标/字）撑，得到的是又窄又高的"竖起来的椭圆"，
  既不好看也不好点。现在铺满轨道宽度，是正常的圆角矩形。
- 顺带修了一个**测试污染**：`TestUpdateChannelSelection` 现在隔离真实
  `settings.json`（用户开过「β 版试用」会让"正式版只认 stable"的用例失真）。

### 回退预热池 + 页面填满 + 窗口尺寸收敛

- **工具窗口预热池回退**：真机实测没改善（用户反馈"反而更不流畅"），
  恢复成"点击时按需创建 + 顶部加载动画"。`_prewarmOne` / `_openTool` /
  `_PrewarmedWindow` / `_PrewarmHost` / `main()` 里的 `prewarm` 分支全部删除。
- **工具页 / 早读页改为 `_section` 卡片**（和设置页一致），内容铺满整宽，
  不再挤在左上角一小块。按钮在卡片内居中。
- **窗口尺寸收敛**：主窗口按屏幕可用区算尺寸（`screen_retriever.getPrimaryDisplay()`），
  最小尺寸降到 640×460；早晚读窗口（`morning_browser`）同样按屏幕收敛并居中。
  避免小屏 / 开了缩放时窗口比屏幕还高、标题栏和关闭键点不到。

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
| GET | `/api/status` | 版本/壁纸状态/登录状态/daemon 活动/下载进度（`download_progress` 为 **0~1 小数**）/`check_ok`+`check_detail`（上次更新检查到底成没成）/设置 |
| GET/POST | `/api/settings` | 读取/保存设置 |
| GET | `/api/morning/config` | 早读登录状态与时间段 |
| GET | `/api/morning/students` | 学生名单（失败时 `success=false` + 中文原因） |
| POST | `/api/morning/login` / `logout` / `open` | 登录（先校验后保存）/ 退出登录（连缓存一起清）/ 打开浏览器 |
| GET | `/api/update/status` | 更新状态：`pending_ready`、`last_check_at`、`latest_version`、`check_ok`（True=查到结论 / False=渠道都连不上 / None=还没查过）、`check_detail`、`downloading`、`download_status`、`download_version`、`download_progress`（**0~1 小数**） |
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

**渠道规则（发正式版前必看）**：

- 版本名含 `beta/alpha/rc/pre` → `channel=beta`，CI 把**同渠道**的旧记录 `is_latest` 置 false；
  客户端里 beta 版查"所有渠道的 `is_latest`"，挑版本号最高的那条。
- 否则 → `channel=stable`，CI 把**所有渠道**的旧记录 `is_latest` 置 false（正式版压过 beta）。
  正式版客户端只认 `channel=stable`，不会被拉去装 beta。
- 为什么 beta 版要查所有渠道：以前它只查 `channel=beta`，正式版发布后那条 beta 记录
  `is_latest` 还是 true，查询返回它自己 → 判成"已是最新" → **beta 装机版永远升不到正式版**。
  同时，装机版要"看到"正式版还依赖 CI 那一步把 beta 记录的 `is_latest` 清掉
  （老客户端不认新规则，只能靠这个）。回归测试见
  `tools/test_core.py::TestUpdateChannelSelection`。

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
- **壁纸/屏保选本地文件用官方 `file_selector` 插件**（`CdSettingsDialog` 的「浏览…」）。
  它会给 Windows 构建多带一个 `file_selector_windows_plugin.dll`（安装包自带，不用额外处理）。
  想省掉这个依赖就得自己 FFI 调 `GetOpenFileNameW`，struct 布局容易出错，不划算。
- **文字颜色一律显式写**。`TextStyle(fontSize: xx)` 的 `color` 是 null，
  一旦继承链断开就会变成看不见的文字（beta27 真实出现过："标题栏和壁纸设置的字体看不见"）。
  防回归：`test/contrast_test.dart` 会把控件真的渲染出来，
  逐个取 RichText 实际生效的颜色按 WCAG 校验对比度（浅色/深色各一遍，含按钮图标字形）。
  图标颜色要按**平时状态**校验：只有悬停才成立的颜色（比如浅色模式下的 `onError` 白）
  平时叠在底色上就是看不见。

## 八、改代码时的检查清单

- [ ] 改了版本号相关文件？跑一遍 `tools/bump_version.py`，别手改。
- [ ] 改了后端接口？同步更新 `flutter_app/lib/api.dart` 和本文件第五节的表格。
- [ ] 碰了子窗口？确认没有新增阻塞式 Win32 调用（见第二节）；
      拖动只能走 `SubWindow.dragTarget`（鼠标用 `GetCursorPos`，触摸用重建坐标），
      **不要**相信 Flutter 给的指针坐标是屏幕坐标（第二节有实测数据）；
      改了拖动就跑一遍 `tools/probe_drag.ps1` 真机验证。
- [ ] 改了滚轮/拖动交互？单测要用 `PointerDeviceKind.mouse` 再测一遍
      （默认 touch 测试会漏掉 `dragDevices` 不含 mouse 这个坑）。
- [ ] 写了新的 `TextStyle(...)`？显式带 `color`（见第七节最后一条）。
- [ ] 碰了进程退出？确认托盘退出、安装前退出、`--quit` 三条路径都能真的结束进程。
- [ ] 加了后台行为？在「设置 → 程序在后台做了什么」里加一条说明。
- [ ] 提交前：`python tools/test_core.py`、`cd flutter_app; dart analyze; flutter test`。
