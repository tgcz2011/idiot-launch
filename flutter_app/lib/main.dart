import 'dart:async';
import 'dart:ffi' as ffi;
import 'dart:io';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import 'api.dart';
import 'app_log.dart';
import 'cd_settings_page.dart';
import 'sub_window.dart';
import 'theme.dart';
import 'timer_page.dart';
import 'update_banner.dart';
import 'widgets/big_button.dart';
import 'widgets/title_bar.dart';

// Windows API：判断 PID 是否还活着（单实例用）
final ffi.DynamicLibrary _kernel32 = ffi.DynamicLibrary.open('kernel32.dll');
typedef _OpenProcessNative = ffi.IntPtr Function(ffi.Uint32, ffi.Int32, ffi.Uint32);
typedef _OpenProcessDart = int Function(int, int, int);
final _OpenProcessDart _openProcess =
    _kernel32.lookupFunction<_OpenProcessNative, _OpenProcessDart>('OpenProcess');
typedef _CloseHandleNative = ffi.Int32 Function(ffi.IntPtr);
typedef _CloseHandleDart = int Function(int);
final _CloseHandleDart _closeHandle =
    _kernel32.lookupFunction<_CloseHandleNative, _CloseHandleDart>('CloseHandle');

bool _processExists(int pid) {
  const int processQueryLimitedInformation = 0x1000;
  final handle = _openProcess(processQueryLimitedInformation, 0, pid);
  if (handle == 0) return false;
  _closeHandle(handle);
  return true;
}

bool _isFirstInstance = false;

Future<void> _ensureSingleInstance() async {
  final pidFile = r'D:\IdiotLaunch\data\instance.pid';
  try {
    final dir = Directory(r'D:\IdiotLaunch\data');
    if (!dir.existsSync()) dir.createSync(recursive: true);

    if (File(pidFile).existsSync()) {
      final existing = int.tryParse(File(pidFile).readAsStringSync().trim());
      if (existing != null && existing != pid && _processExists(existing)) {
        _isFirstInstance = false;
        // 通知已有实例把窗口显示出来
        try {
          await ApiService().activateWindow().timeout(const Duration(seconds: 3));
          await Future<void>.delayed(const Duration(milliseconds: 600));
        } catch (_) {}
        return;
      }
    }
    File(pidFile).writeAsStringSync(pid.toString());
    _isFirstInstance = true;
  } catch (e, s) {
    AppLog.error('单实例检测失败', e, s);
    _isFirstInstance = true;
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  AppLog.info('main() 开始 pid=$pid');

  // ---- 子窗口入口分发 ----
  // 父窗口创建子窗口时传 arguments = "<pid>:<kind>"，并用窗口通道把子窗口
  // 自己的 HWND 推过来。用 HWND 而不是"自己枚举找窗口"，是为了让同时打开的
  // 倒计时/秒表绝不会互相抢错窗口（历史 bug：拖 A 动 B、另一个窗口保持 800x600）。
  try {
    final controller = await WindowController.fromCurrentEngine();
    final args = controller.arguments.toString();
    final parts = args.split(':');
    if (parts.length >= 2 && parts[0] == pid.toString()) {
      final kind = parts[1];
      if (kind == 'timer' || kind == 'stopwatch') {
        AppLog.setWindowTag(kind == 'timer' ? 1 : 2);

        final hwndCompleter = Completer<int>();
        try {
          await controller.setWindowMethodHandler((call) async {
            if (call.method == 'set_hwnd') {
              final a = call.arguments;
              final h = (a is Map) ? a['hwnd'] : null;
              if (h is int && !hwndCompleter.isCompleted) {
                hwndCompleter.complete(h);
              }
            }
            return null;
          });
        } catch (e) {
          AppLog.warn('注册窗口通道失败（将回退到自动查找）: $e');
        }

        int hwnd = 0;
        try {
          hwnd = await hwndCompleter.future.timeout(const Duration(seconds: 4));
          AppLog.info('$kind: 收到 HWND $hwnd');
        } catch (_) {
          AppLog.warn('$kind: 未收到 HWND，回退到自动查找');
        }

        Future<void> nativeShow() async {
          try {
            await controller.show();
          } catch (e) {
            AppLog.warn('$kind: 兜底显示失败: $e');
          }
        }

        runApp(_SubWindowApp(
          home: kind == 'timer'
              ? TimerPage(hwnd: hwnd, nativeShow: nativeShow)
              : StopwatchPage(hwnd: hwnd, nativeShow: nativeShow),
        ));
        return;
      }
    }
  } catch (e) {
    AppLog.info('fromCurrentEngine 异常（按主窗口继续）: $e');
  }

  await windowManager.ensureInitialized();
  await _ensureSingleInstance();
  if (!_isFirstInstance) {
    AppLog.info('已有实例在运行，本进程退出');
    exit(0);
  }

  const windowOptions = WindowOptions(
    size: Size(860, 620),
    minimumSize: Size(760, 560),
    center: true,
    backgroundColor: Colors.transparent,
    skipTaskbar: false,
    titleBarStyle: TitleBarStyle.hidden,
    title: '傻瓜启动器',
  );
  await windowManager.waitUntilReadyToShow(windowOptions, () async {
    await windowManager.show();
    await windowManager.focus();
  });

  runApp(const IdiotLaunchApp());
  AppLog.info('main() 结束');
}

/// 子窗口用同一个主题（含深色），但不带主窗口的窗口管理逻辑。
class _SubWindowApp extends StatelessWidget {
  const _SubWindowApp({required this.home});

  final Widget home;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: home,
    );
  }
}

class IdiotLaunchApp extends StatefulWidget {
  const IdiotLaunchApp({super.key});

  @override
  State<IdiotLaunchApp> createState() => _IdiotLaunchAppState();
}

class _IdiotLaunchAppState extends State<IdiotLaunchApp> {
  ThemeMode _themeMode = ThemeMode.system;

  void _applyThemeMode(ThemeMode mode) {
    if (_themeMode == mode) return;
    setState(() => _themeMode = mode);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '傻瓜启动器',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: _themeMode,
      home: MainPage(onThemeModeChanged: _applyThemeMode),
    );
  }
}

class MainPage extends StatefulWidget {
  const MainPage({super.key, required this.onThemeModeChanged});

  final ValueChanged<ThemeMode> onThemeModeChanged;

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> with WindowListener {
  final ApiService _api = ApiService();

  int _selectedIndex = 0;
  Map<String, dynamic> _status = <String, dynamic>{};
  Map<String, dynamic> _updateStatus = <String, dynamic>{};

  bool _cdRunning = false;
  bool _morningLoggedIn = false;
  String _morningClass = '';
  bool _backendAlive = true;

  Timer? _pollTimer;
  bool _busy = false;       // 有 loading 弹窗时避免重复触发
  bool _closing = false;
  bool _checkingUpdate = false;

  @override
  void initState() {
    super.initState();
    AppLog.info('主界面 initState');
    try {
      windowManager.addListener(this);
      windowManager.setPreventClose(true);
      _initBackend();
      _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) => _pollStatus());
      // 开发/验收用：设 IDIOT_LAUNCH_AUTO_WINDOW=timer|stopwatch 启动，
      // 3 秒后自动打开工具窗口。子窗口的拖动/DPI 只能靠真机验证
      // （见 HANDOFF 第二节"真机验证拖动的方法"），手动点是脚本做不到的。
      // 不设这个环境变量就完全没影响。
      final auto = Platform.environment['IDIOT_LAUNCH_AUTO_WINDOW'] ?? '';
      if (auto == 'timer' || auto == 'stopwatch') {
        Future<void>.delayed(
            const Duration(seconds: 3), () => _createToolWindow(auto));
      }
    } catch (e, s) {
      AppLog.error('initState 异常', e, s);
    }
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    _pollTimer?.cancel();
    super.dispose();
  }

  // ================= 窗口关闭：最小化到托盘 =================
  @override
  void onWindowClose() async {
    if (_closing) return;
    _closing = true;
    try {
      bool firstTimeThisBoot = false;
      try {
        final r = await _api.notifyTray(
          '傻瓜启动器还在后台运行',
          '窗口已最小化到托盘。右键托盘图标可以重新打开或彻底退出。',
          oncePerBoot: true,
        );
        firstTimeThisBoot = ApiService.asBool(r['shown']);
      } catch (e) {
        AppLog.warn('托盘提示失败: $e');
      }

      if (firstTimeThisBoot && mounted) {
        // 每个开机周期只提示一次，避免每次关窗都打扰
        _showTrayHintDialog();
        await Future<void>.delayed(const Duration(milliseconds: 2600));
        final nav = _hintNavigator;
        if (nav != null && nav.canPop()) {
          nav.pop();
        }
      }
    } finally {
      await windowManager.hide();
      _closing = false;
    }
  }

  NavigatorState? _hintNavigator;

  void _showTrayHintDialog() {
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) {
        // 用 NavigatorState 关闭，避免跨 async gap 使用 BuildContext
        _hintNavigator = Navigator.of(ctx);
        return AlertDialog(
          icon: const Icon(Icons.minimize, size: 36),
          title: const Text('已最小化到托盘'),
          content: const Text(
            '傻瓜启动器仍在后台运行（负责自动更新和早晚读悬浮球）。\n\n'
            '需要重新打开：双击桌面图标，或右键任务栏右下角的托盘图标。\n'
            '需要彻底退出：右键托盘图标 → 退出（结束后台）。',
            style: TextStyle(height: 1.6),
          ),
        );
      },
    );
  }

  // ================= 后端与状态 =================
  Future<void> _initBackend() async {
    try {
      await _api.ensureBackend();
    } catch (e, s) {
      AppLog.error('后端启动失败', e, s);
      if (mounted) {
        _showError('后台服务未启动',
            '程序界面可以打开，但倒计时、早晚读等功能需要后台服务。\n\n'
            '已尝试自动启动但超时：$e\n\n'
            '可以在「设置 → 打开日志」查看 ui.log 与 daemon.log。');
      }
    }
    await _pollStatus();
  }

  Future<void> _pollStatus() async {
    try {
      final s = await _api.getStatus();
      final u = await _api.getUpdateStatus();
      if (!mounted) return;

      if (s['activate_requested'] == true) {
        await windowManager.show();
        await windowManager.focus();
        try {
          await _api.clearActivate();
        } catch (_) {}
      }

      final theme = ApiService.asString(s['settings']?['theme']);
      widget.onThemeModeChanged(switch (theme) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      });

      setState(() {
        _backendAlive = true;
        _status = s;
        _updateStatus = u;
        _cdRunning = ApiService.asBool(s['countdown_running']);
        _morningLoggedIn = ApiService.asBool(s['morning_logged_in']);
        _morningClass = ApiService.asString(s['morning_class']);
      });
    } catch (e) {
      // 后端掉线：明确告诉用户，而不是继续显示过期状态
      if (mounted && _backendAlive) {
        setState(() => _backendAlive = false);
        AppLog.warn('状态轮询失败: $e');
      }
    }
  }

  // ================= 通用 UI 辅助 =================
  Future<T?> _withLoading<T>(String text, Future<T> Function() action,
      {String? errorTitle}) async {
    if (_busy) return null;
    setState(() => _busy = true);
    _showLoadingDialog(text);
    try {
      final result = await action();
      if (mounted) Navigator.of(context, rootNavigator: true).pop();
      return result;
    } catch (e, s) {
      if (mounted) Navigator.of(context, rootNavigator: true).pop();
      AppLog.error('操作失败: $text', e, s);
      _showError(errorTitle ?? '操作失败', _friendlyError(e));
      return null;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// 把异常翻译成老师能看懂的话。
  String _friendlyError(Object e) {
    final text = e.toString();
    if (text.contains('SocketException') ||
        text.contains('Connection refused') ||
        text.contains('ClientException')) {
      return '连接不上后台服务。可以稍等几秒重试；如果一直不行，'
          '请在「设置 → 打开日志」里把 daemon.log 发给管理员。';
    }
    if (text.contains('TimeoutException')) {
      return '操作超时，可能是网络或服务器较慢，请稍后重试。';
    }
    return text;
  }

  void _showLoadingDialog(String text) {
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        content: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const SizedBox(
                width: 26, height: 26,
                child: CircularProgressIndicator(strokeWidth: 3)),
            const SizedBox(width: 20),
            Flexible(child: Text(text, style: const TextStyle(fontSize: 16))),
          ],
        ),
      ),
    );
  }

  void _showError(String title, String msg) {
    if (!mounted) return;
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: SingleChildScrollView(
            child: Text(msg, style: const TextStyle(height: 1.5))),
        actions: <Widget>[
          TextButton(
              onPressed: () => Navigator.pop(context), child: const Text('知道了')),
        ],
      ),
    );
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  // ================= 壁纸 =================
  Future<void> _startCountdown(String exam) async {
    final label = exam == 'zhongkao' ? '中考' : '高考';
    final ok = await _withLoading<bool>(
        '正在启动$label倒计时…', () => _api.startCountdown(exam),
        errorTitle: '启动失败');
    if (ok == true) {
      setState(() => _cdRunning = true);
      _toast('已启动$label倒计时，桌面稍后会出现倒计时壁纸');
      _pollStatus();
    }
  }

  Future<void> _startCustomWallpaper() async {
    final ok = await _withLoading<bool>(
        '正在启动自定义壁纸&屏保…', _api.startCustomWallpaper,
        errorTitle: '启动失败');
    if (ok == true) {
      setState(() => _cdRunning = true);
      _toast('已启动自定义壁纸&屏保');
      _pollStatus();
    }
  }

  Future<void> _stopCountdown() async {
    final ok = await _withLoading<bool>('正在关闭壁纸，请稍候…', _api.stopCountdown,
        errorTitle: '关闭失败');
    if (ok == true) {
      setState(() => _cdRunning = false);
      _toast('已关闭壁纸，桌面已恢复');
      _pollStatus();
    } else if (ok == false) {
      _showError('关闭失败', '倒计时没有在 8 秒内退出，可以再点一次「关闭壁纸」。');
    }
  }

  void _openSettings() {
    showDialog<void>(context: context, builder: (_) => const CdSettingsDialog());
  }

  // ================= 早读 =================
  Future<void> _openMorning() async {
    await _withLoading<void>('正在打开早晚读窗口…', _api.openMorningBrowser,
        errorTitle: '打开失败');
  }

  Future<void> _showMorningLogin() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => const _MorningLoginDialog(),
    );
    if (ok == true) {
      await _pollStatus();
      _toast('登录成功');
    }
  }

  Future<void> _showRandomStudent() async {
    final students = await _withLoading<List<Map<String, dynamic>>>(
        '正在获取学生名单…', _api.getMorningStudents,
        errorTitle: '获取名单失败');
    if (students == null) return;
    if (students.isEmpty) {
      _showError('暂时无法抽学生',
          '学生名单是空的。常见原因：网络不通、账号权限不足，或本班还没有录入学生。');
      return;
    }
    if (!mounted) return;

    final countCtrl = TextEditingController(text: '1');
    showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('随机抽学生'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('共 ${students.length} 名学生',
                  style: TextStyle(
                      fontSize: 15,
                      color: Theme.of(ctx).colorScheme.onSurfaceVariant)),
              const SizedBox(height: 14),
              TextField(
                controller: countCtrl,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: '抽取人数（最多 ${students.length}）',
                  border: const OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: <Widget>[
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            FilledButton(
              onPressed: () {
                final n = int.tryParse(countCtrl.text) ?? 1;
                if (n < 1) {
                  setDialogState(() {});
                  _showError('提示', '抽取人数至少为 1');
                  return;
                }
                if (n > students.length) {
                  _showError('提示', '抽取人数不能超过总人数（${students.length} 人）');
                  return;
                }
                final shuffled = <Map<String, dynamic>>[...students]..shuffle();
                final picked = shuffled.take(n).toList();
                Navigator.pop(ctx);
                _showPickedResult(picked, students);
              },
              child: const Text('开始抽取'),
            ),
          ],
        ),
      ),
    );
  }

  void _showPickedResult(
      List<Map<String, dynamic>> picked, List<Map<String, dynamic>> all) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Row(
          children: <Widget>[
            const Icon(Icons.emoji_events, color: Colors.amber, size: 28),
            const SizedBox(width: 8),
            Text('抽到的学生（${picked.length} 人）'),
          ],
        ),
        content: SizedBox(
          width: 340,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: picked.asMap().entries.map((entry) {
                final idx = entry.key;
                final s = entry.value;
                final name = ApiService.asString(s['name'] ?? s['student_name']);
                final no = ApiService.asString(s['student_no'] ?? s['no']);
                final scheme = Theme.of(ctx).colorScheme;
                return Container(
                  margin: const EdgeInsets.symmetric(vertical: 5),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  decoration: BoxDecoration(
                    color: idx == 0
                        ? Colors.amber.withValues(alpha: 0.18)
                        : scheme.primaryContainer.withValues(alpha: 0.35),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                        color: idx == 0 ? Colors.amber : scheme.outlineVariant,
                        width: idx == 0 ? 2 : 1),
                  ),
                  child: Row(
                    children: <Widget>[
                      Container(
                        width: 34, height: 34,
                        decoration: BoxDecoration(
                          color: idx == 0 ? Colors.amber : scheme.primary,
                          borderRadius: BorderRadius.circular(17),
                        ),
                        alignment: Alignment.center,
                        child: Text('${idx + 1}',
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                fontSize: 15)),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(name.isEmpty ? '未知' : name,
                            style: const TextStyle(
                                fontSize: 20, fontWeight: FontWeight.w700)),
                      ),
                      if (no.isNotEmpty)
                        Text('学号 $no',
                            style: TextStyle(
                                fontSize: 14, color: scheme.onSurfaceVariant)),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _reroll(all);
            },
            child: const Text('再抽一次'),
          ),
          FilledButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('确定')),
        ],
      ),
    );
  }

  /// 再抽一次：用已有名单，不再重新联网（原来每次都重新请求，网络慢时很卡）。
  void _reroll(List<Map<String, dynamic>> all) {
    if (all.isEmpty) return;
    final shuffled = <Map<String, dynamic>>[...all]..shuffle();
    _showPickedResult(shuffled.take(1).toList(), all);
  }

  // ================= 更新 =================
  Future<void> _checkUpdate() async {
    if (_checkingUpdate) return;
    setState(() => _checkingUpdate = true);
    // 用"上次检查时间有没有变化"判断这次检查是否真的完成了，
    // 而不是猜 daemon 的活动状态（历史上这里完全没有结果提示）。
    final beforeCheck = ApiService.asDouble(_updateStatus['last_check_at']);
    bool finished = false;
    try {
      await _api.checkUpdate();
      for (int i = 0; i < 25; i++) {
        await Future<void>.delayed(const Duration(seconds: 1));
        await _pollStatus();
        if (!mounted) return;
        final now = ApiService.asDouble(_updateStatus['last_check_at']);
        final ready = ApiService.asBool(_updateStatus['pending_ready']);
        final downloading = ApiService.asBool(_updateStatus['downloading']);
        if (now != beforeCheck || ready || downloading) {
          finished = true;
          break;
        }
      }
    } catch (e) {
      if (mounted) _showError('检查更新失败', _friendlyError(e));
      if (mounted) setState(() => _checkingUpdate = false);
      return;
    } finally {
      if (mounted) setState(() => _checkingUpdate = false);
    }

    if (!mounted) return;
    final ready = ApiService.asBool(_updateStatus['pending_ready']);
    final downloading = ApiService.asBool(_updateStatus['downloading']);
    final dlVersion = ApiService.asString(_updateStatus['download_version']);
    final latest = ApiService.asString(_updateStatus['latest_version']);
    final pending = ApiService.asString(_updateStatus['pending_version']);
    final current = ApiService.asString(_status['version']);
    if (ready) {
      _toast('发现新版本 v$pending，已下载完成，点上方「一键更新」即可安装');
    } else if (downloading) {
      _toast('发现新版本 v$dlVersion，正在后台下载，完成后可一键更新');
    } else if (finished && latest.isEmpty) {
      _toast('已是最新版本（v$current）');
    } else if (latest.isNotEmpty) {
      _toast('发现新版本 v$latest，即将开始后台下载');
    } else {
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('检查更新没完成'),
          content: const Text(
            '25 秒内没有拿到结果，通常是教室网络访问不了更新服务器。\n\n'
            '可以稍后再点一次「检查更新」；平时不影响倒计时和早晚读的使用。',
            style: TextStyle(height: 1.6),
          ),
          actions: <Widget>[
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('知道了')),
          ],
        ),
      );
    }
  }

  Future<void> _installUpdate() async {
    final version = ApiService.asString(_updateStatus['pending_version']);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('现在更新？'),
        content: Text(
          '将更新到 v$version。\n\n'
          '更新过程中程序会自动关闭，屏幕上会出现安装进度条（安装包自带），'
          '装完会自动重新打开，大约需要 1-3 分钟。\n\n'
          '请先确认现在的倒计时/早晚读可以中断。',
          style: const TextStyle(height: 1.6),
        ),
        actions: <Widget>[
          TextButton(
              onPressed: () => Navigator.pop(ctx, false), child: const Text('稍后')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true), child: const Text('立即更新')),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      final r = await _api.installUpdate();
      if (!ApiService.asBool(r['success'])) {
        _showError('无法开始更新', ApiService.asString(r['message']));
        return;
      }
      _showError('正在更新',
          '更新程序已启动，本窗口马上会关闭。\n安装完成后会自动重新打开。');
    } catch (e) {
      // 进程可能已经被安装程序关掉，连接中断属于预期
      AppLog.info('一键更新请求结束: $e');
    }
  }

  // ================= 界面 =================
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: <Widget>[
          const CustomTitleBar(title: '傻瓜启动器'),
          if (!_backendAlive)
            MaterialBanner(
              backgroundColor: Theme.of(context).colorScheme.errorContainer,
              leading: const Icon(Icons.cloud_off),
              content: const Text('后台服务未运行，功能可能不可用（会自动重试）'),
              actions: <Widget>[
                TextButton(onPressed: _initBackend, child: const Text('重试')),
              ],
            ),
          Expanded(
            child: Row(
              children: <Widget>[
                NavigationRail(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: (i) => setState(() => _selectedIndex = i),
                  labelType: NavigationRailLabelType.all,
                  minWidth: 78,
                  destinations: const <NavigationRailDestination>[
                    NavigationRailDestination(
                        icon: Icon(Icons.wallpaper_outlined),
                        selectedIcon: Icon(Icons.wallpaper),
                        label: Text('壁纸')),
                    NavigationRailDestination(
                        icon: Icon(Icons.handyman_outlined),
                        selectedIcon: Icon(Icons.handyman),
                        label: Text('工具')),
                    NavigationRailDestination(
                        icon: Icon(Icons.menu_book_outlined),
                        selectedIcon: Icon(Icons.menu_book),
                        label: Text('早读')),
                    NavigationRailDestination(
                        icon: Icon(Icons.settings_outlined),
                        selectedIcon: Icon(Icons.settings),
                        label: Text('设置')),
                  ],
                ),
                const VerticalDivider(thickness: 1, width: 1),
                Expanded(child: _buildPage()),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPage() {
    switch (_selectedIndex) {
      case 0:
        return _buildWallpaperPage();
      case 1:
        return _buildToolsPage();
      case 2:
        return _buildMorningPage();
      default:
        return _buildSettingsPage();
    }
  }

  // ---------- 更新横幅 ----------
  Widget _buildUpdateBanner() {
    final scheme = Theme.of(context).colorScheme;
    final ready = ApiService.asBool(_updateStatus['pending_ready']);
    final downloading = ApiService.asBool(_updateStatus['downloading']);
    // 后端给的是 0~1 的小数（历史 bug：后端给 0~100，这里又乘了 100）
    final progress =
        ApiService.asDouble(_updateStatus['download_progress']).clamp(0.0, 1.0);
    final pending = ApiService.asString(_updateStatus['pending_version']);
    final dlVersion = ApiService.asString(_updateStatus['download_version']);
    final dlStatus = ApiService.asString(_updateStatus['download_status']);
    final latest = ApiService.asString(_updateStatus['latest_version']);
    final current = ApiService.asString(_status['version']);
    final activity = ApiService.asString(_updateStatus['daemon_activity']);
    // 后端如实上报"这次到底查成没查成"：null = 还没查过，true = 查到了结论，
    // false = 渠道都连不上（此时 latest 为空并不代表已是最新）
    final checkOk = _updateStatus['check_ok'] is bool
        ? _updateStatus['check_ok'] as bool
        : null;
    final checkDetail = ApiService.asString(_updateStatus['check_detail']);
    final shownVersion = dlVersion.isNotEmpty
        ? dlVersion
        : (latest.isNotEmpty ? latest : pending);

    // 说什么话交给纯函数（可单测，见 test/update_banner_test.dart）：
    // 只有 checkOk == true 才允许说"已是最新"。
    final copy = updateBannerCopy(
      ready: ready,
      downloading: downloading,
      progress: progress,
      pending: pending,
      shownVersion: shownVersion,
      latest: latest,
      downloadStatus: dlStatus,
      checking: _checkingUpdate || activity == 'checking',
      current: current,
      checkOk: checkOk,
      checkDetail: checkDetail,
      lastCheckText: _lastCheckText(),
    );

    late final Widget leading;
    final title = copy.title;
    final subtitle = copy.subtitle;
    List<Widget> actions = <Widget>[];

    switch (copy.kind) {
      case UpdateBannerKind.ready:
        leading = Icon(Icons.system_update_alt, size: 30, color: scheme.primary);
        actions = <Widget>[
          FilledButton.icon(
            onPressed: _installUpdate,
            icon: const Icon(Icons.download_done, size: 20),
            label: const Text('一键更新'),
          ),
        ];
      case UpdateBannerKind.downloading:
        leading = SizedBox(
          width: 30,
          height: 30,
          child: CircularProgressIndicator(
              value: progress > 0.005 ? progress : null, strokeWidth: 3),
        );
      case UpdateBannerKind.hasUpdate:
      case UpdateBannerKind.downloadFailed:
        final failed = copy.kind == UpdateBannerKind.downloadFailed;
        leading = Icon(failed ? Icons.error_outline : Icons.system_update,
            size: 30, color: failed ? scheme.error : scheme.primary);
        actions = <Widget>[
          TextButton(
            onPressed: _checkingUpdate ? null : _checkUpdate,
            child:
                Text(_checkingUpdate ? '请稍候…' : (failed ? '立即重试' : '立即下载')),
          ),
        ];
      case UpdateBannerKind.checking:
        leading = const SizedBox(
            width: 30,
            height: 30,
            child: CircularProgressIndicator(strokeWidth: 3));
      case UpdateBannerKind.checkFailed:
      case UpdateBannerKind.neverChecked:
        final failed = copy.kind == UpdateBannerKind.checkFailed;
        leading = Icon(failed ? Icons.cloud_off : Icons.help_outline,
            size: 30, color: failed ? scheme.error : scheme.onSurfaceVariant);
        actions = <Widget>[
          TextButton(
            onPressed: _checkingUpdate ? null : _checkUpdate,
            child: Text(_checkingUpdate ? '检查中…' : '检查更新'),
          ),
        ];
      case UpdateBannerKind.upToDate:
        leading = Icon(Icons.verified, size: 30, color: Colors.green.shade600);
        actions = <Widget>[
          TextButton(
            onPressed: _checkingUpdate ? null : _checkUpdate,
            child: Text(_checkingUpdate ? '检查中…' : '检查更新'),
          ),
        ];
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: <Widget>[
            leading,
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(title,
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w700)),
                  if (subtitle.isNotEmpty) ...<Widget>[
                    const SizedBox(height: 4),
                    Text(subtitle,
                        style: TextStyle(
                            fontSize: 14, color: scheme.onSurfaceVariant)),
                  ],
                ],
              ),
            ),
            ...actions,
          ],
        ),
      ),
    );
  }

  String _lastCheckText() {
    final ts = ApiService.asDouble(_updateStatus['last_check_at']);
    if (ts <= 0) return '还没有检查过更新';
    final t = DateTime.fromMillisecondsSinceEpoch((ts * 1000).round());
    final diff = DateTime.now().difference(t);
    String ago;
    if (diff.inMinutes < 1) {
      ago = '刚刚';
    } else if (diff.inHours < 1) {
      ago = '${diff.inMinutes} 分钟前';
    } else if (diff.inDays < 1) {
      ago = '${diff.inHours} 小时前';
    } else {
      ago = '${diff.inDays} 天前';
    }
    return '上次检查：$ago';
  }

  // ---------- 壁纸页 ----------
  Widget _buildWallpaperPage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _buildUpdateBanner(),
          Text('壁纸 & 屏保', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 6),
          Text('点一下就启动，桌面会出现倒计时壁纸',
              style: TextStyle(
                  fontSize: 14,
                  color: Theme.of(context).colorScheme.onSurfaceVariant)),
          const SizedBox(height: 16),
          Wrap(
            spacing: 14,
            runSpacing: 14,
            children: <Widget>[
              BigButton(
                  icon: Icons.school,
                  label: '中考倒计时',
                  color: Colors.blue,
                  onPressed: _busy ? null : () => _startCountdown('zhongkao')),
              BigButton(
                  icon: Icons.school_outlined,
                  label: '高考倒计时',
                  color: Colors.purple,
                  onPressed: _busy ? null : () => _startCountdown('gaokao')),
              BigButton(
                  icon: Icons.image_outlined,
                  label: '自定义壁纸',
                  color: Colors.teal,
                  onPressed: _busy ? null : _startCustomWallpaper),
              BigButton(
                  icon: Icons.tune,
                  label: '壁纸设置',
                  color: Colors.grey,
                  onPressed: _openSettings),
              BigButton(
                icon: Icons.stop_circle_outlined,
                label: '关闭壁纸',
                color: Colors.red,
                onPressed: (_cdRunning && !_busy) ? _stopCountdown : null,
                disabledHint: _cdRunning ? null : '当前没有运行中的壁纸',
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ---------- 工具页 ----------
  bool _creatingWindow = false;

  /// 创建倒计时/秒表子窗口。
  ///
  /// 为什么要这么麻烦：
  ///  * 子窗口由插件在**同一进程**里新建，创建时要起一个新的 Flutter 引擎，
  ///    这一步发生在进程主线程上，所以主窗口会短暂无响应 —— 必须先把 loading
  ///    弹出来，用户才知道是在加载而不是卡死。
  ///  * 窗口以 hiddenAtLaunch=true 创建（否则会先闪一个 800x600 的原生标题栏窗口），
  ///    创建前后对比本进程顶层窗口即可确定地拿到它的 HWND，再推给子窗口，
  ///    由子窗口改完样式后自己显示。
  Future<void> _createToolWindow(String kind) async {
    if (_creatingWindow) return;
    _creatingWindow = true;
    final label = kind == 'timer' ? '倒计时' : '秒表';
    setState(() => _busy = true);
    _showLoadingDialog('正在打开$label窗口…\n\n第一次打开需要 1-2 秒，这期间主界面会短暂无响应，属正常现象。');
    try {
      // 先让 loading 画出来，再去做会阻塞主线程的创建
      await Future<void>.delayed(const Duration(milliseconds: 80));
      final before = listProcessWindows(visibleOnly: false).toSet();

      final controller = await WindowController.create(WindowConfiguration(
        arguments: '$pid:$kind',
        hiddenAtLaunch: true,
      ));

      // 找出刚出现的那个顶层窗口 = 我们的子窗口
      int hwnd = 0;
      for (int i = 0; i < 30 && hwnd == 0; i++) {
        for (final h in listProcessWindows(visibleOnly: false)) {
          if (!before.contains(h)) {
            hwnd = h;
            break;
          }
        }
        if (hwnd == 0) {
          await Future<void>.delayed(const Duration(milliseconds: 50));
        }
      }
      AppLog.info('创建$label窗口: id=${controller.windowId} hwnd=$hwnd');

      if (hwnd != 0) {
        // 子窗口的 Dart 侧可能还没注册好通道，失败就重试
        for (int i = 0; i < 20; i++) {
          try {
            await controller
                .invokeMethod<void>('set_hwnd', <String, dynamic>{'hwnd': hwnd});
            break;
          } catch (e) {
            if (i >= 19) {
              AppLog.warn('推送 HWND 失败，子窗口会自行查找: $e');
            }
            await Future<void>.delayed(const Duration(milliseconds: 150));
          }
        }
      } else {
        AppLog.warn('未能识别新建的$label窗口，子窗口将自行查找');
      }
    } catch (e, s) {
      AppLog.error('创建$label窗口失败', e, s);
      if (mounted) _showError('打开$label失败', _friendlyError(e));
    } finally {
      if (mounted) Navigator.of(context, rootNavigator: true).pop();
      _creatingWindow = false;
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _buildToolsPage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('工具', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 6),
          Text('独立小窗口，可以置顶/全屏，讲台上用',
              style: TextStyle(
                  fontSize: 14,
                  color: Theme.of(context).colorScheme.onSurfaceVariant)),
          const SizedBox(height: 16),
          Wrap(
            spacing: 14,
            runSpacing: 14,
            children: <Widget>[
              BigButton(
                icon: Icons.timer_outlined,
                label: '倒计时',
                color: Colors.teal,
                onPressed: _busy ? null : () => _createToolWindow('timer'),
              ),
              BigButton(
                icon: Icons.timer_10_select,
                label: '秒表',
                color: Colors.indigo,
                onPressed: _busy ? null : () => _createToolWindow('stopwatch'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ---------- 早读页 ----------
  Widget _buildMorningPage() {
    final scheme = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('早晚读', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          Card(
            child: ListTile(
              leading: Icon(
                  _morningLoggedIn ? Icons.check_circle : Icons.login,
                  color: _morningLoggedIn ? Colors.green : scheme.onSurfaceVariant,
                  size: 30),
              title: Text(_morningLoggedIn ? '已登录：$_morningClass' : '未登录'),
              subtitle: Text(_morningLoggedIn
                  ? '登录信息保存在 D 盘，重启后仍在'
                  : '登录后早晚读页面会自动进入班级'),
              trailing: _morningLoggedIn
                  ? TextButton(
                      onPressed: () async {
                        await _api.morningLogout();
                        await _pollStatus();
                        _toast('已退出登录');
                      },
                      child: const Text('退出登录'))
                  : FilledButton(
                      onPressed: _showMorningLogin, child: const Text('登录')),
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 14,
            runSpacing: 14,
            children: <Widget>[
              BigButton(
                  icon: Icons.menu_book,
                  label: '打开早晚读',
                  color: Colors.teal,
                  onPressed: _busy ? null : _openMorning),
              BigButton(
                icon: Icons.people_alt_outlined,
                label: '随机抽学生',
                color: Colors.amber,
                onPressed: (_morningLoggedIn && !_busy) ? _showRandomStudent : null,
                disabledHint: _morningLoggedIn ? null : '需要先登录早晚读账号',
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ---------- 设置页 ----------
  Widget _buildSettingsPage() {
    final scheme = Theme.of(context).colorScheme;
    final settings = (_status['settings'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{};
    final themeMode = switch (ApiService.asString(settings['theme'])) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      _ => ThemeMode.system,
    };
    final autoUpdate = settings['auto_update'] != false;
    final telemetry = settings['telemetry'] != false;
    final version = ApiService.asString(_status['version']);

    return ListView(
      padding: const EdgeInsets.all(20),
      children: <Widget>[
        Text('设置', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),

        // ---- 外观 ----
        _section('外观', <Widget>[
          const ListTile(
            leading: Icon(Icons.brightness_6),
            title: Text('主题'),
            subtitle: Text('深色主题适合光线较暗的教室；跟随系统则与 Windows 设置一致'),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: SegmentedButton<ThemeMode>(
              segments: const <ButtonSegment<ThemeMode>>[
                ButtonSegment<ThemeMode>(
                    value: ThemeMode.system,
                    label: Text('跟随系统'),
                    icon: Icon(Icons.brightness_auto)),
                ButtonSegment<ThemeMode>(
                    value: ThemeMode.light,
                    label: Text('浅色'),
                    icon: Icon(Icons.light_mode)),
                ButtonSegment<ThemeMode>(
                    value: ThemeMode.dark,
                    label: Text('深色'),
                    icon: Icon(Icons.dark_mode)),
              ],
              selected: <ThemeMode>{themeMode},
              onSelectionChanged: (s) async {
                final mode = s.first;
                widget.onThemeModeChanged(mode);
                try {
                  await _api.saveSettings(<String, dynamic>{
                    'theme': switch (mode) {
                      ThemeMode.light => 'light',
                      ThemeMode.dark => 'dark',
                      ThemeMode.system => 'system',
                    }
                  });
                  await _pollStatus();
                } catch (e) {
                  AppLog.warn('保存主题失败: $e');
                }
              },
            ),
          ),
        ]),

        // ---- 更新 ----
        _section('更新', <Widget>[
          SwitchListTile(
            secondary: const Icon(Icons.system_update),
            title: const Text('空闲时自动安装更新'),
            subtitle: const Text(
                '开启后：新版本仍会在后台自动下载，并在电脑空闲 10 分钟以上时自动安装。\n'
                '关闭后：仍然后台下载（这样点「一键更新」立刻可用），但不会自动安装。'),
            value: autoUpdate,
            onChanged: (v) async {
              try {
                await _api.saveSettings(<String, dynamic>{'auto_update': v});
                await _pollStatus();
                _toast(v ? '已开启自动更新' : '已关闭自动更新（仍可手动一键更新）');
              } catch (e) {
                _showError('保存失败', _friendlyError(e));
              }
            },
          ),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: Text('当前版本 v$version'),
            subtitle: Text(_lastCheckText()),
          ),
          ListTile(
            leading: const Icon(Icons.refresh),
            title: const Text('立即检查更新'),
            trailing: _checkingUpdate
                ? const SizedBox(
                    width: 22, height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2.5))
                : const Icon(Icons.chevron_right),
            onTap: _checkingUpdate ? null : _checkUpdate,
          ),
        ]),

        // ---- 隐私 ----
        _section('隐私', <Widget>[
          SwitchListTile(
            secondary: const Icon(Icons.insights),
            title: const Text('匿名运行统计'),
            subtitle: const Text(
                '上报内容：程序版本、Windows 版本、错误类型（不含班级、姓名、密码等任何个人信息）。'
                '用于定位老师们遇到的问题是普遍问题还是个别问题。关闭后不再上报。'),
            value: telemetry,
            onChanged: (v) async {
              try {
                await _api.saveSettings(<String, dynamic>{'telemetry': v});
                await _pollStatus();
                _toast(v ? '已开启匿名统计，感谢反馈' : '已关闭匿名统计');
              } catch (e) {
                _showError('保存失败', _friendlyError(e));
              }
            },
          ),
        ]),

        // ---- 你可能不知道的后台行为 ----
        _section('程序在后台做了什么', <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Text(
              '以下行为都是刻意设计的，写在这里是为了让老师和网管心里有数：\n\n'
              '1. 关闭窗口后程序不退出，继续在托盘里运行（自动更新和早读悬浮球需要它）。'
              '想彻底退出：右键托盘图标 → 退出（结束后台）。\n'
              '2. 后台守护进程会定时检查更新；空闲较久时会静默安装新版本，'
              '安装时程序会短暂关闭再自动打开。\n'
              '3. 桌面和 D 盘根目录的「傻瓜启动器」快捷方式如果被删掉，'
              '程序会在 30 秒内自动重建（用来对抗冰点还原）。\n'
              '4. 早晚读的班级密码保存在 D:\\IdiotLaunch\\data 下（做过混淆处理，'
              '但同一台电脑的其他账号可以读到）。公用电脑建议不要勾选「记住登录」。\n'
              '5. 所有数据都在 D:\\IdiotLaunch\\data，C 盘被冰点还原不会影响它。',
              style: TextStyle(
                  fontSize: 14, height: 1.8, color: scheme.onSurfaceVariant),
            ),
          ),
        ]),

        // ---- 维护 ----
        _section('维护', <Widget>[
          ListTile(
            leading: const Icon(Icons.folder_open),
            title: const Text('打开数据目录'),
            subtitle: Text(ApiService.asString(_status['data_dir'])),
            onTap: () => _api.openFolder(ApiService.asString(_status['data_dir'])),
          ),
          ListTile(
            leading: const Icon(Icons.description_outlined),
            title: const Text('打开日志目录'),
            subtitle: const Text('排查问题时把这里的日志发给管理员'),
            onTap: () => _api.openFolder(ApiService.asString(_status['data_dir'])),
          ),
          ListTile(
            leading: const Icon(Icons.power_settings_new, color: Colors.red),
            title: const Text('彻底退出程序'),
            subtitle: const Text('停止后台更新、悬浮球和早晚读浏览器'),
            onTap: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('退出程序？'),
                  content: const Text(
                      '将停止后台更新守护、早晚读悬浮球和早晚读窗口，并恢复桌面壁纸。\n'
                      '下次使用请重新双击桌面图标。'),
                  actions: <Widget>[
                    TextButton(
                        onPressed: () => Navigator.pop(ctx, false),
                        child: const Text('取消')),
                    FilledButton(
                        onPressed: () => Navigator.pop(ctx, true),
                        child: const Text('退出')),
                  ],
                ),
              );
              if (ok != true) return;
              try {
                await _api.quitAll();
              } catch (_) {}
              await windowManager.destroy();
            },
          ),
        ]),

        // ---- 关于 ----
        _section('关于', <Widget>[
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('傻瓜启动器'),
            subtitle: Text('v$version · Flutter 前端 + Python 后端\n'
                '免费开源软件（GPL-3.0），内嵌 Countdown Desktop 特供版'),
            isThreeLine: true,
          ),
        ]),

        const SizedBox(height: 24),
        Center(
          child: Text('数据目录：${ApiService.asString(_status['data_dir'])}',
              style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
        ),
        const SizedBox(height: 12),
      ],
    );
  }

  Widget _section(String title, List<Widget> children) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 8),
            child: Text(title,
                style: Theme.of(context).textTheme.titleMedium),
          ),
          Card(child: Column(children: children)),
        ],
      ),
    );
  }
}

/// 早晚读登录对话框。
///
/// 独立成 StatefulWidget（而不是用 StatefulBuilder 塞在方法里）：
/// 登录状态需要跨 async gap 保存，写在一起容易出现"先引用后声明"的问题。
class _MorningLoginDialog extends StatefulWidget {
  const _MorningLoginDialog();

  @override
  State<_MorningLoginDialog> createState() => _MorningLoginDialogState();
}

class _MorningLoginDialogState extends State<_MorningLoginDialog> {
  final ApiService _api = ApiService();
  final TextEditingController _classCtrl = TextEditingController();
  final TextEditingController _pwdCtrl = TextEditingController();

  String _grade = '初三';
  bool _persistent = true;
  bool _loggingIn = false;
  String? _error;

  static const List<String> _grades = <String>[
    '初一', '初二', '初三', '高一', '高二', '高三'
  ];
  static const Map<String, String> _gradeMap = <String, String>{
    '初一': '7', '初二': '8', '初三': '9', '高一': '10', '高二': '11', '高三': '12'
  };

  @override
  void dispose() {
    _classCtrl.dispose();
    _pwdCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final classNum = _classCtrl.text.trim();
    if (classNum.isEmpty) {
      setState(() => _error = '请填写班级号');
      return;
    }
    if (_pwdCtrl.text.isEmpty) {
      setState(() => _error = '请填写班级密码');
      return;
    }
    setState(() {
      _loggingIn = true;
      _error = null;
    });
    try {
      // 后端的报错分得比较细（网络故障 / 密码错误），原样显示给老师
      final r = await _api.morningLogin(
          _gradeMap[_grade] ?? '9', classNum, _pwdCtrl.text, _persistent);
      if (!mounted) return;
      if (ApiService.asBool(r['success'])) {
        Navigator.pop(context, true);
      } else {
        final msg = ApiService.asString(r['error']);
        setState(() {
          _loggingIn = false;
          _error = msg.isEmpty ? '登录失败，请检查账号密码' : msg;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loggingIn = false;
        _error = '登录失败：$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('早晚读登录'),
      content: SizedBox(
        width: 400,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              DropdownButtonFormField<String>(
                initialValue: _grade,
                decoration: const InputDecoration(labelText: '年级'),
                items: _grades
                    .map((g) => DropdownMenuItem<String>(value: g, child: Text(g)))
                    .toList(),
                onChanged: _loggingIn
                    ? null
                    : (v) => setState(() => _grade = v ?? '初三'),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _classCtrl,
                enabled: !_loggingIn,
                decoration: const InputDecoration(labelText: '班级号（如 01）'),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _pwdCtrl,
                obscureText: true,
                enabled: !_loggingIn,
                decoration: const InputDecoration(labelText: '班级密码'),
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 6),
              CheckboxListTile(
                value: _persistent,
                dense: true,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                onChanged: _loggingIn
                    ? null
                    : (v) => setState(() => _persistent = v ?? true),
                title: const Text('记住登录（重启后保留）'),
                subtitle: const Text('不勾选则关机后失效；勾选会把密码保存在 D 盘（做过混淆）'),
              ),
              const SizedBox(height: 6),
              Text(
                '先选年级，再填班级号：初中 01-14，高中 01-11\n'
                '初始密码：admin + 班级号（一班 = admin01），可在教师管理界面修改',
                style: TextStyle(
                    fontSize: 13, height: 1.6, color: scheme.onSurfaceVariant),
              ),
              if (_error != null) ...<Widget>[
                const SizedBox(height: 12),
                Text(_error!,
                    style: TextStyle(fontSize: 14, color: scheme.error)),
              ],
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _loggingIn ? null : () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: _loggingIn ? null : _submit,
          child: _loggingIn
              ? const SizedBox(
                  width: 20, height: 20,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.white))
              : const Text('登录'),
        ),
      ],
    );
  }
}
