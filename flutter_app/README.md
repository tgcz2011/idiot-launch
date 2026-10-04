# 傻瓜启动器 · Flutter 前端

后端是 Python（`../src`），前端只负责界面：主窗口、倒计时/秒表子窗口、设置页。

## 目录

| 文件 | 作用 |
|------|------|
| `lib/main.dart` | 入口、单实例、主界面（更新横幅 / 壁纸 / 工具 / 早读 / 设置） |
| `lib/timer_page.dart` | 倒计时与秒表（独立子窗口，含预设、全屏、置顶、快捷键） |
| `lib/sub_window.dart` | 子窗口的原生控制。**所有 Win32 调用都必须走这里**（非阻塞实现，避免"未响应"） |
| `lib/api.dart` | 后端 HTTP API 封装（含类型兜底，后端返回 int/null 都不会让界面崩） |
| `lib/theme.dart` | 浅色/深色主题（字号比 Material 默认大一档，便于讲台远距离观看） |
| `lib/format.dart` | 时间格式化（有单元测试 `test/format_test.dart`） |
| `lib/cd_settings_page.dart` | 壁纸&屏保设置（写的是 `countdown_app` 的 config.json） |
| `lib/app_log.dart` | 前端日志（写到 `D:\IdiotLaunch\data\ui.log`，自动轮转） |
| `lib/widgets/` | 自定义标题栏、大按钮 |

## 开发与验证

```powershell
flutter pub get
flutter analyze          # 必须零 issue
flutter test
flutter build windows --release
```

调试时前端需要后端在跑：`python ../run.py --server`（端口文件在
`%TEMP%\idiot_launch_backend_port`，`api.dart` 会自动读；后端没起时前端也会自己拉起它）。

## 注意

- 子窗口（倒计时/秒表）和主窗口在**同一个进程**里，但是不同的 Flutter 引擎/线程。
  从 Dart 线程直接 `SendMessage` 或同步 `SetWindowPos` 会死锁 → 统一用 `sub_window.dart`。
- 窗口 ✕ 是"最小化到托盘"（`windowManager.setPreventClose(true)` + `onWindowClose`），
  真正的退出由后端托盘菜单负责。
- 改界面后请顺手确认深色主题下的显示效果（老师办公室的电脑经常是深色模式）。
