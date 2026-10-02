import 'dart:async';
import 'dart:io';
import 'dart:ffi' as ffi;
import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';
import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'api.dart';
import 'timer_page.dart';
import 'cd_settings_page.dart';

// Windows API 进程检测（dart:ffi）
final ffi.DynamicLibrary _kernel32 = ffi.DynamicLibrary.open('kernel32.dll');
typedef OpenProcessNative = ffi.IntPtr Function(ffi.Uint32, ffi.Int32, ffi.Uint32);
typedef OpenProcessDart = int Function(int, int, int);
final _openProcess = _kernel32.lookupFunction<OpenProcessNative, OpenProcessDart>('OpenProcess');
typedef CloseHandleNative = ffi.Int32 Function(ffi.IntPtr);
typedef CloseHandleDart = int Function(int);
final _closeHandle = _kernel32.lookupFunction<CloseHandleNative, CloseHandleDart>('CloseHandle');

bool _processExists(int pid) {
  const PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
  final handle = _openProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
  if (handle == 0) return false;
  _closeHandle(handle);
  return true;
}

// 单实例：PID 文件 + FFI 进程检测
bool _isFirstInstance = false;

Future<void> _ensureSingleInstance() async {
  final pidFile = r'D:\IdiotLaunch\data\instance.pid';
  try {
    final dir = Directory(r'D:\IdiotLaunch\data');
    if (!dir.existsSync()) dir.createSync(recursive: true);

    if (File(pidFile).existsSync()) {
      final existingPid = int.tryParse(File(pidFile).readAsStringSync().trim());
      if (existingPid != null && _processExists(existingPid)) {
        _isFirstInstance = false;
        // 通知已有实例激活窗口
        try {
          final api = ApiService();
          await api.activateWindow();
        } catch (_) {}
        return;
      }
    }
    File(pidFile).writeAsStringSync(pid.toString());
    _isFirstInstance = true;
  } catch (_) {
    _isFirstInstance = true;
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();

  // 多窗口入口分发：用 WindowController.fromCurrentEngine 获取 arguments
  try {
    final controller = await WindowController.fromCurrentEngine();
    if (controller.arguments == 'timer') {
      windowManager.waitUntilReadyToShow(
        const WindowOptions(size: Size(360, 480), minimumSize: Size(300, 400), center: true, title: '倒计时', titleBarStyle: TitleBarStyle.hidden),
        () async { await windowManager.show(); await windowManager.focus(); },
      );
      runApp(MaterialApp(debugShowCheckedModeBanner: false, theme: _timerTheme(), home: const Scaffold(body: TimerPage())));
      return;
    }
    if (controller.arguments == 'stopwatch') {
      windowManager.waitUntilReadyToShow(
        const WindowOptions(size: Size(360, 520), minimumSize: Size(300, 400), center: true, title: '秒表', titleBarStyle: TitleBarStyle.hidden),
        () async { await windowManager.show(); await windowManager.focus(); },
      );
      runApp(MaterialApp(debugShowCheckedModeBanner: false, theme: _timerTheme(), home: const Scaffold(body: StopwatchPage())));
      return;
    }
  } catch (_) {
    // 主窗口没有 fromCurrentEngine，忽略
  }

  await _ensureSingleInstance();
  if (!_isFirstInstance) {
    Process.killPid(pid);
    return;
  }

  WindowOptions windowOptions = const WindowOptions(
    size: Size(780, 520),
    minimumSize: Size(640, 420),
    center: true,
    backgroundColor: Colors.transparent,
    skipTaskbar: false,
    titleBarStyle: TitleBarStyle.hidden,
    title: '傻瓜启动器',
  );
  windowManager.waitUntilReadyToShow(windowOptions, () async {
    await windowManager.show();
    await windowManager.focus();
  });

  runApp(const IdiotLaunchApp());
}

class IdiotLaunchApp extends StatelessWidget {
  const IdiotLaunchApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '傻瓜启动器',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1A73E8),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        fontFamily: 'NotoSansSC',
        textTheme: const TextTheme(
          titleLarge: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
          titleMedium: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          titleSmall: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
          bodyLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
          bodyMedium: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
          bodySmall: TextStyle(fontSize: 13, fontWeight: FontWeight.w400),
          labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
          labelMedium: TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
          labelSmall: TextStyle(fontSize: 12, fontWeight: FontWeight.w400),
        ),
        listTileTheme: const ListTileThemeData(
          titleTextStyle: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: Colors.black87),
          subtitleTextStyle: TextStyle(fontSize: 13, fontWeight: FontWeight.w400, color: Colors.black54),
        ),
      ),
      home: const MainPage(),
    );
  }
}

ThemeData _timerTheme() {
  return ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1A73E8)),
    useMaterial3: true,
    fontFamily: 'NotoSansSC',
    textTheme: const TextTheme(
      titleLarge: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
      titleMedium: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      bodyMedium: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
      bodySmall: TextStyle(fontSize: 12, fontWeight: FontWeight.w400),
    ),
  );
}

// 自定义标题栏（隐藏原生标题栏后使用）
class CustomTitleBar extends StatelessWidget {
  final String title;
  final bool showMaximize;
  const CustomTitleBar({super.key, required this.title, this.showMaximize = true});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 32,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(bottom: BorderSide(color: Colors.grey.withOpacity(0.2), width: 1)),
      ),
      child: Row(
        children: [
          // 拖动区域
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onPanStart: (_) => windowManager.startDragging(),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(
                  children: [
                    Icon(Icons.touch_app, size: 16, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(width: 8),
                    Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                  ],
                ),
              ),
            ),
          ),
          // 最小化
          _TitleBarButton(
            icon: Icons.remove,
            onPressed: () => windowManager.minimize(),
          ),
          if (showMaximize)
            _TitleBarButton(
              icon: Icons.check_box_outline_blank,
              onPressed: () async {
                if (await windowManager.isMaximized()) {
                  windowManager.unmaximize();
                } else {
                  windowManager.maximize();
                }
              },
            ),
          _TitleBarButton(
            icon: Icons.close,
            isClose: true,
            onPressed: () => windowManager.close(),
          ),
        ],
      ),
    );
  }
}

class _TitleBarButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onPressed;
  final bool isClose;
  const _TitleBarButton({required this.icon, required this.onPressed, this.isClose = false});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 46,
      height: 32,
      child: InkWell(
        onTap: onPressed,
        hoverColor: isClose ? Colors.red.withOpacity(0.8) : Colors.grey.withOpacity(0.15),
        child: Icon(icon, size: 16, color: isClose ? null : Colors.grey[700]),
      ),
    );
  }
}

class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  int _selectedIndex = 0;
  final ApiService _api = ApiService();
  Map<String, dynamic> _status = {};
  Map<String, dynamic> _updateStatus = {};
  bool _cdRunning = false;
  bool _morningLoggedIn = false;
  String _morningClass = '';
  Timer? _pollTimer;
  bool _checkingUpdate = false;
  bool _startingCd = false;
  bool _showVersionCard = true;

  static const _pages = [
    NavigationRailDestination(
      icon: Icon(Icons.wallpaper_outlined),
      selectedIcon: Icon(Icons.wallpaper),
      label: Text('壁纸&屏保'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.handyman_outlined),
      selectedIcon: Icon(Icons.handyman),
      label: Text('工具'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.menu_book_outlined),
      selectedIcon: Icon(Icons.menu_book),
      label: Text('早读'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.settings_outlined),
      selectedIcon: Icon(Icons.settings),
      label: Text('设置'),
    ),
  ];

  @override
  void initState() {
    super.initState();
    _initBackend();
    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) => _pollStatus());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _initBackend() async {
    try {
      await _api.ensureBackend();
      await _pollStatus();
    } catch (e) {}
  }

  Future<void> _pollStatus() async {
    try {
      final s = await _api.getStatus();
      final u = await _api.getUpdateStatus();
      if (mounted) {
        // 检查是否有激活窗口请求
        if (s['activate_requested'] == true) {
          windowManager.show();
          windowManager.focus();
          try { await _api.clearActivate(); } catch (_) {}
        }
        setState(() {
          _status = s;
          _updateStatus = u;
          _cdRunning = s['countdown_running'] ?? false;
          _morningLoggedIn = s['morning_logged_in'] ?? false;
          _morningClass = s['morning_class'] ?? '';
        });
      }
    } catch (_) {}
  }

  Future<void> _startCountdown(String exam) async {
    setState(() => _startingCd = true);
    _showLoadingDialog('正在启动${exam == 'zhongkao' ? '中考' : '高考'}倒计时...');
    try {
      await _api.startCountdown(exam);
      setState(() => _cdRunning = true);
      if (mounted) Navigator.pop(context); // 关闭 loading
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已启动${exam == 'zhongkao' ? '中考' : '高考'}倒计时')),
        );
      }
    } catch (e) {
      if (mounted) Navigator.pop(context);
      _showError('启动失败', e.toString());
    } finally {
      if (mounted) setState(() => _startingCd = false);
    }
  }

  Future<void> _startCustomWallpaper() async {
    setState(() => _startingCd = true);
    _showLoadingDialog('正在启动自定义壁纸&屏保...');
    try {
      await _api.startCustomWallpaper();
      setState(() => _cdRunning = true);
      if (mounted) Navigator.pop(context);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('已启动自定义壁纸&屏保')),
        );
      }
    } catch (e) {
      if (mounted) Navigator.pop(context);
      _showError('启动失败', e.toString());
    } finally {
      if (mounted) setState(() => _startingCd = false);
    }
  }

  void _showLoadingDialog(String text) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        content: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(width: 20),
            Text(text),
          ],
        ),
      ),
    );
  }

  Future<void> _stopCountdown() async {
    try {
      await _api.stopCountdown();
      setState(() => _cdRunning = false);
    } catch (e) {
      _showError('关闭失败', e.toString());
    }
  }

  void _openSettings() {
    showDialog(
      context: context,
      builder: (_) => const CdSettingsDialog(),
    );
  }

  Future<void> _openMorning() async {
    try {
      await _api.openMorningBrowser();
    } catch (e) {
      _showError('打开早读失败', e.toString());
    }
  }

  Future<void> _checkUpdate() async {
    setState(() => _checkingUpdate = true);
    try {
      await _api.checkUpdate();
      await Future.delayed(const Duration(seconds: 2));
      await _pollStatus();
      if (mounted) {
        final hasUpdate = _updateStatus['has_update'] ?? false;
        final pending = _updateStatus['pending_version'] ?? '';
        if (hasUpdate) {
          showDialog(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('发现新版本'),
              content: Text('当前版本：v${_status['version'] ?? '?'}\n最新版本：$pending\n\n将在后台静默下载，下载完成后空闲时自动更新。'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('知道了')),
                FilledButton(onPressed: () async { Navigator.pop(ctx); await _api.installUpdate(); }, child: const Text('立即更新')),
              ],
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('已是最新版本（v${_status['version'] ?? '?'}）')),
          );
        }
      }
    } catch (e) {
      _showError('检查更新失败', e.toString());
    } finally {
      if (mounted) setState(() => _checkingUpdate = false);
    }
  }

  void _showError(String title, String msg) {
    if (!mounted) return;
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: Text(msg),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('确定'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          const CustomTitleBar(title: '傻瓜启动器'),
          Expanded(
            child: Row(
              children: [
                NavigationRail(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: (i) => setState(() => _selectedIndex = i),
                  labelType: NavigationRailLabelType.all,
                  minWidth: 68,
                  destinations: _pages,
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
      case 3:
        return _buildSettingsPage();
      default:
        return const SizedBox.shrink();
    }
  }

  // ========== 壁纸&屏保页 ==========
  Widget _buildWallpaperPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_showVersionCard)
            _buildUpdateIndicator()
          else
            Align(
              alignment: Alignment.topRight,
              child: IconButton(
                icon: Icon(
                  (_updateStatus['has_update'] ?? false) ? Icons.update : Icons.check_circle_outline,
                  color: (_updateStatus['has_update'] ?? false) ? Colors.orange : Colors.green,
                  size: 22,
                ),
                tooltip: '查看更新状态',
                onPressed: () => setState(() => _showVersionCard = true),
              ),
            ),
          if (_showVersionCard) const SizedBox(height: 16),
          Text('壁纸 & 屏保', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _bigButton(Icons.school, '中考倒计时', Colors.blue, _startingCd ? null : () => _startCountdown('zhongkao')),
              _bigButton(Icons.school_outlined, '高考倒计时', Colors.purple, _startingCd ? null : () => _startCountdown('gaokao')),
              _bigButton(Icons.image_outlined, '自定义壁纸&屏保', Colors.teal, _startingCd ? null : _startCustomWallpaper),
              _bigButton(Icons.settings, '壁纸&屏保设置', Colors.grey, _openSettings),
              _bigButton(
                Icons.stop_circle_outlined,
                '关闭壁纸',
                Colors.red,
                _cdRunning ? _stopCountdown : null,
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ========== 工具页 ==========
  Widget _buildToolsPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('工具', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _bigButton(Icons.timer_outlined, '倒计时', Colors.teal, () async {
                await WindowController.create(const WindowConfiguration(arguments: 'timer', hiddenAtLaunch: false));
              }),
              _bigButton(Icons.timer_10_select, '秒表', Colors.indigo, () async {
                await WindowController.create(const WindowConfiguration(arguments: 'stopwatch', hiddenAtLaunch: false));
              }),
            ],
          ),
        ],
      ),
    );
  }

  Widget _bigButton(IconData icon, String label, Color color, VoidCallback? onPressed) {
    final disabled = onPressed == null;
    return SizedBox(
      width: 150,
      height: 92,
      child: Material(
        color: disabled ? Colors.grey[200] : color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(14),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 32, color: disabled ? Colors.grey : color),
              const SizedBox(height: 6),
              Text(label, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: disabled ? Colors.grey : Colors.black87)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildUpdateIndicator() {
    final hasUpdate = _updateStatus['has_update'] ?? false;
    final downloading = _updateStatus['downloading'] ?? false;
    final progress = (_updateStatus['download_progress'] ?? 0.0) as double;
    final pending = _updateStatus['pending_version'] ?? '';

    IconData leadingIcon;
    Color leadingColor;
    if (downloading) {
      leadingIcon = Icons.download;
      leadingColor = Colors.blue;
    } else if (hasUpdate) {
      leadingIcon = Icons.update;
      leadingColor = Colors.orange;
    } else {
      leadingIcon = Icons.check_circle_outline;
      leadingColor = Colors.green;
    }

    return Card(
      child: ListTile(
        leading: downloading
            ? SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  value: progress > 0 ? progress : null,
                  strokeWidth: 2.5,
                  color: Colors.blue,
                ),
              )
            : _checkingUpdate
                ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2.5))
                : Icon(leadingIcon, color: leadingColor),
        title: Text(
          downloading ? '正在下载更新 $pending...' : (hasUpdate ? '新版本待更新：$pending' : '当前 v${_status['version'] ?? '?'}'),
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
        ),
        subtitle: downloading
            ? Text('${(progress * 100).toStringAsFixed(0)}%', style: TextStyle(fontSize: 11, color: Colors.grey[600]))
            : null,
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (hasUpdate && !downloading)
              TextButton(onPressed: () => _api.checkUpdate(), child: const Text('立即更新')),
            IconButton(
              icon: const Icon(Icons.close, size: 18),
              tooltip: '收起',
              onPressed: () => setState(() => _showVersionCard = false),
            ),
          ],
        ),
        onTap: () => _showUpdateDetail(),
      ),
    );
  }

  void _showUpdateDetail() {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('更新详情'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('当前版本：v${_status['version'] ?? '?'}'),
            const SizedBox(height: 8),
            Text('待更新版本：${_updateStatus['pending_version'] ?? '无'}'),
            const SizedBox(height: 8),
            Text('下载进度：${((_updateStatus['download_progress'] ?? 0) * 100).toStringAsFixed(1)}%'),
            const SizedBox(height: 8),
            Text('守护进程：${_status['daemon_running'] == true ? '运行中' : '已停止'}'),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('关闭')),
          FilledButton(
            onPressed: _checkingUpdate ? null : () async { await _checkUpdate(); if (mounted) Navigator.pop(context); },
            child: Text(_checkingUpdate ? '检查中...' : '检查更新'),
          ),
        ],
      ),
    );
  }

  // ========== 早读页 ==========
  Widget _buildMorningPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('早晚读', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          Card(
            child: ListTile(
              leading: Icon(_morningLoggedIn ? Icons.check_circle : Icons.login, color: _morningLoggedIn ? Colors.green : Colors.grey),
              title: Text(_morningLoggedIn ? '已登录：$_morningClass' : '未登录'),
              subtitle: Text(_morningLoggedIn ? '可使用随机抽学生等功能' : '登录后可使用完整功能'),
              trailing: _morningLoggedIn
                  ? TextButton(onPressed: () async { await _api.morningLogout(); await _pollStatus(); }, child: const Text('退出登录'))
                  : TextButton(onPressed: _showMorningLogin, child: const Text('登录')),
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _bigButton(Icons.menu_book, '打开早晚读', Colors.teal, _openMorning),
              _bigButton(
                Icons.people_alt_outlined,
                '随机抽学生',
                Colors.amber,
                _morningLoggedIn ? _showRandomStudent : null,
              ),
            ],
          ),
          if (!_morningLoggedIn)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('随机抽学生和打开早晚读需要登录后使用', style: TextStyle(fontSize: 12, color: Colors.grey[600])),
            ),
        ],
      ),
    );
  }

  void _showMorningLogin() {
    String selectedGrade = '初三';
    final classCtrl = TextEditingController();
    final pwdCtrl = TextEditingController();
    bool persistent = true;
    bool loggingIn = false;

    const grades = ['初一', '初二', '初三', '高一', '高二', '高三'];
    const gradeMap = {'初一': '7', '初二': '8', '初三': '9', '高一': '10', '高二': '11', '高三': '12'};

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('早晚读登录'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              DropdownButtonFormField<String>(
                value: selectedGrade,
                decoration: const InputDecoration(labelText: '年级'),
                items: grades.map((g) => DropdownMenuItem(value: g, child: Text(g))).toList(),
                onChanged: loggingIn ? null : (v) => setDialogState(() => selectedGrade = v ?? '初三'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: classCtrl,
                enabled: !loggingIn,
                decoration: const InputDecoration(labelText: '班级号（如 01）'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: pwdCtrl,
                obscureText: true,
                enabled: !loggingIn,
                decoration: const InputDecoration(labelText: '班级密码'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Checkbox(
                    value: persistent,
                    onChanged: loggingIn ? null : (v) => setDialogState(() => persistent = v ?? true),
                  ),
                  const Text('持久登录（重启后保留）'),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                '先选年级，再填班级号：初中 01-14，高中 01-11\n初始密码：admin + 班级号（一班 = admin01）\n密码可在教师管理界面修改',
                style: TextStyle(fontSize: 11, color: Colors.grey[600]),
              ),
              if (loggingIn) ...[
                const SizedBox(height: 16),
                Row(
                  children: [
                    const SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    const SizedBox(width: 12),
                    Text('正在登录，服务器响应可能较慢…', style: TextStyle(fontSize: 13, color: Colors.grey[600])),
                  ],
                ),
              ],
            ],
          ),
          actions: [
            TextButton(
              onPressed: loggingIn ? null : () => Navigator.pop(ctx),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: loggingIn
                  ? null
                  : () async {
                      final gradeNum = gradeMap[selectedGrade] ?? '9';
                      final classNum = classCtrl.text.trim();
                      if (classNum.isEmpty) {
                        ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(content: Text('请填写班级号')));
                        return;
                      }
                      setDialogState(() => loggingIn = true);
                      try {
                        final ok = await _api.morningLoginWithGrade(gradeNum, classNum, pwdCtrl.text, persistent);
                        if (ok && ctx.mounted) {
                          Navigator.pop(ctx);
                          await _pollStatus();
                          if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('登录成功')));
                        } else {
                          if (ctx.mounted) {
                            setDialogState(() => loggingIn = false);
                            ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(content: Text('账号或密码错误')));
                          }
                        }
                      } catch (e) {
                        if (ctx.mounted) {
                          setDialogState(() => loggingIn = false);
                          ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text('登录失败：$e')));
                        }
                      }
                    },
              child: loggingIn
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Text('登录'),
            ),
          ],
        ),
      ),
    );
  }

  void _showRandomStudent() async {
    try {
      final students = await _api.getMorningStudents();
      if (students.isEmpty) {
        _showError('无法抽学生', '学生列表为空');
        return;
      }
      final countCtrl = TextEditingController(text: '1');
      showDialog(
        context: context,
        builder: (ctx) => StatefulBuilder(
          builder: (ctx, setDialogState) => AlertDialog(
            title: const Text('随机抽学生'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('共 ${students.length} 名学生', style: TextStyle(fontSize: 14, color: Colors.grey[600])),
                const SizedBox(height: 12),
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
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
              FilledButton(
                onPressed: () {
                  final n = int.tryParse(countCtrl.text) ?? 1;
                  if (n < 1) {
                    showDialog(context: ctx, builder: (_) => AlertDialog(title: const Text('提示'), content: const Text('抽取人数至少为 1'), actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('确定'))]));
                    return;
                  }
                  if (n > students.length) {
                    showDialog(context: ctx, builder: (_) => AlertDialog(title: const Text('提示'), content: Text('抽取人数不能超过总人数（${students.length}人）'), actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('确定'))]));
                    return;
                  }
                  final shuffled = [...students]..shuffle();
                  final picked = shuffled.take(n).toList();
                  Navigator.pop(ctx);
                  // 美化结果展示
                  showDialog(
                    context: context,
                    builder: (_) => AlertDialog(
                      title: Row(
                        children: [
                          const Icon(Icons.emoji_events, color: Colors.amber),
                          const SizedBox(width: 8),
                          Text('抽到的学生（${picked.length}人）'),
                        ],
                      ),
                      content: Container(
                        width: 300,
                        constraints: const BoxConstraints(maxHeight: 400),
                        child: SingleChildScrollView(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: picked.asMap().entries.map((entry) {
                              final idx = entry.key;
                              final dynamic s = entry.value;
                              String name = '未知';
                              String no = '';
                              if (s is Map) {
                                name = (s['name'] ?? s['student_name'] ?? '未知').toString();
                                final n = s['student_no'] ?? s['no'];
                                no = n?.toString() ?? '';
                              } else {
                                name = s.toString();
                              }
                              return Container(
                                margin: const EdgeInsets.symmetric(vertical: 4),
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                decoration: BoxDecoration(
                                  color: idx == 0 ? Colors.amber.withOpacity(0.15) : Colors.blue.withOpacity(0.08),
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(
                                    color: idx == 0 ? Colors.amber : Colors.blue.withOpacity(0.3),
                                    width: idx == 0 ? 2 : 1,
                                  ),
                                ),
                                child: Row(
                                  children: [
                                    Container(
                                      width: 32, height: 32,
                                      decoration: BoxDecoration(
                                        color: idx == 0 ? Colors.amber : Colors.blue,
                                        borderRadius: BorderRadius.circular(16),
                                      ),
                                      alignment: Alignment.center,
                                      child: Text('${idx + 1}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14)),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Text(name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                                    ),
                                    if (no.isNotEmpty) Text('学号 $no', style: TextStyle(fontSize: 13, color: Colors.grey[500])),
                                  ],
                                ),
                              );
                            }).toList(),
                          ),
                        ),
                      ),
                      actions: [
                        TextButton(
                          onPressed: () {
                            Navigator.pop(context);
                            _showRandomStudent(); // 再抽一次
                          },
                          child: const Text('再抽一次'),
                        ),
                        FilledButton(onPressed: () => Navigator.pop(context), child: const Text('确定')),
                      ],
                    ),
                  );
                },
                child: const Text('开始抽取'),
              ),
            ],
          ),
        ),
      );
    } catch (e) {
      _showError('获取学生列表失败', e.toString());
    }
  }

  // ========== 设置页 ==========
  Widget _buildSettingsPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('设置', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.info_outline),
                  title: const Text('关于'),
                  subtitle: Text('傻瓜启动器 v${_status['version'] ?? '?'}\nFlutter 前端 + Python 后端'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.update),
                  title: Text(_checkingUpdate ? '正在检查更新...' : '检查更新'),
                  trailing: _checkingUpdate ? const CircularProgressIndicator() : const Icon(Icons.chevron_right),
                  onTap: _checkingUpdate ? null : _checkUpdate,
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.code),
                  title: const Text('开源许可证'),
                  subtitle: const Text('GPL-3.0 · 内嵌 Countdown Desktop\n鸣谢：豆包 AI 辅助开发'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// 工具弹窗容器
class _ToolDialog extends StatelessWidget {
  final String title;
  final Widget child;
  const _ToolDialog({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Dialog(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: SizedBox(
          width: 440,
          height: 520,
          child: child,
        ),
      ),
    );
  }
}
