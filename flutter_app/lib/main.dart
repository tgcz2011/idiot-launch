import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';
import 'api.dart';
import 'timer_page.dart';

// 单实例：PID 文件 + 进程检查
bool _isFirstInstance = false;

Future<void> _ensureSingleInstance() async {
  final pidFile = r'D:\IdiotLaunch\data\instance.pid';
  try {
    final dir = Directory(r'D:\IdiotLaunch\data');
    if (!dir.existsSync()) dir.createSync(recursive: true);

    if (File(pidFile).existsSync()) {
      final existingPid = int.tryParse(File(pidFile).readAsStringSync().trim());
      if (existingPid != null) {
        // 用 tasklist 检查该 PID 是否仍在运行
        final result = Process.runSync('tasklist', ['/FI', 'PID eq $existingPid', '/NH']);
        if (result.stdout.toString().contains('$existingPid')) {
          _isFirstInstance = false;
          return;
        }
      }
    }
    // 没有运行中的实例，写入当前 PID
    File(pidFile).writeAsStringSync(pid.toString());
    _isFirstInstance = true;
  } catch (_) {
    _isFirstInstance = true; // 出错时保守认为是第一个实例
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();
  await _ensureSingleInstance();
  if (!_isFirstInstance) {
    // 已有实例运行，强制退出当前进程（Windows 上 exit() 可能被 engine 拦截）
    Process.killPid(pid);
    return;
  }

  WindowOptions windowOptions = const WindowOptions(
    size: Size(780, 520),
    minimumSize: Size(640, 420),
    center: true,
    backgroundColor: Colors.transparent,
    skipTaskbar: false,
    titleBarStyle: TitleBarStyle.normal,
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
      ),
      home: const MainPage(),
    );
  }
}

class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  int _selectedIndex = 0; // 默认壁纸&屏保页
  final ApiService _api = ApiService();
  Map<String, dynamic> _status = {};
  Map<String, dynamic> _updateStatus = {};
  bool _cdRunning = false;
  bool _morningLoggedIn = false;
  String _morningClass = '';
  Timer? _pollTimer;

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
    } catch (e) {
      // 后端启动失败，静默处理
    }
  }

  Future<void> _pollStatus() async {
    try {
      final s = await _api.getStatus();
      final u = await _api.getUpdateStatus();
      if (mounted) {
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
    try {
      await _api.startCountdown(exam);
      setState(() => _cdRunning = true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已启动${exam == 'zhongkao' ? '中考' : '高考'}倒计时')),
        );
      }
    } catch (e) {
      _showError('启动失败', e.toString());
    }
  }

  Future<void> _stopCountdown() async {
    try {
      await _api.stopCountdown();
      setState(() => _cdRunning = false);
    } catch (e) {
      _showError('关闭失败', e.toString());
    }
  }

  Future<void> _openSettings() async {
    try {
      await _api.openCountdownSettings();
    } catch (e) {
      _showError('打开设置失败', e.toString());
    }
  }

  Future<void> _openMorning() async {
    try {
      await _api.openMorningBrowser();
    } catch (e) {
      _showError('打开早读失败', e.toString());
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
      body: Row(
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
          _buildUpdateIndicator(),
          const SizedBox(height: 16),
          Text('壁纸 & 屏保', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _bigButton(Icons.school, '中考倒计时', Colors.blue, () => _startCountdown('zhongkao')),
              _bigButton(Icons.school_outlined, '高考倒计时', Colors.purple, () => _startCountdown('gaokao')),
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
              _bigButton(Icons.timer_outlined, '倒计时', Colors.teal, () {
                Navigator.push(context, MaterialPageRoute(builder: (_) => const TimerPage()));
              }),
              _bigButton(Icons.timer_10_select, '秒表', Colors.indigo, () {
                Navigator.push(context, MaterialPageRoute(builder: (_) => const StopwatchPage()));
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
            : Icon(leadingIcon, color: leadingColor),
        title: Text(
          downloading ? '正在下载更新 $pending...' : (hasUpdate ? '新版本待更新：$pending' : '已是最新版本'),
          style: const TextStyle(fontSize: 13),
        ),
        subtitle: Text(
          '当前 v${_status['version'] ?? '?'}',
          style: TextStyle(fontSize: 11, color: Colors.grey[600]),
        ),
        trailing: hasUpdate && !downloading
            ? TextButton(onPressed: () => _api.checkUpdate(), child: const Text('立即更新'))
            : null,
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
          FilledButton(onPressed: () async { await _api.checkUpdate(); if (mounted) Navigator.pop(context); }, child: const Text('检查更新')),
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
              child: Text('随机抽学生需要登录后使用', style: TextStyle(fontSize: 12, color: Colors.grey[600])),
            ),
        ],
      ),
    );
  }

  void _showMorningLogin() {
    final idCtrl = TextEditingController();
    final pwdCtrl = TextEditingController();
    bool persistent = true;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('早晚读登录'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: idCtrl, decoration: const InputDecoration(labelText: '班级 ID（如 2024-1-1）')),
              const SizedBox(height: 12),
              TextField(controller: pwdCtrl, obscureText: true, decoration: const InputDecoration(labelText: '密码')),
              const SizedBox(height: 12),
              Row(
                children: [
                  Checkbox(value: persistent, onChanged: (v) => setDialogState(() => persistent = v ?? true)),
                  const Text('持久登录（重启后保留）'),
                ],
              ),
              const SizedBox(height: 8),
              Text('注意：用户名格式为 年级-班级-序号，密码由管理员提供', style: TextStyle(fontSize: 11, color: Colors.grey[600])),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            FilledButton(
              onPressed: () async {
                try {
                  final ok = await _api.morningLogin(idCtrl.text.trim(), pwdCtrl.text, persistent);
                  if (ok && ctx.mounted) {
                    Navigator.pop(ctx);
                    await _pollStatus();
                    if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('登录成功')));
                  } else {
                    if (ctx.mounted) ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(content: Text('账号或密码错误')));
                  }
                } catch (e) {
                  if (ctx.mounted) ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text('登录失败：$e')));
                }
              },
              child: const Text('登录'),
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
        builder: (ctx) => AlertDialog(
          title: const Text('随机抽学生'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('共 ${students.length} 名学生'),
              const SizedBox(height: 12),
              TextField(controller: countCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '抽取人数')),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            FilledButton(
              onPressed: () {
                final n = int.tryParse(countCtrl.text) ?? 1;
                final shuffled = [...students]..shuffle();
                final picked = shuffled.take(n).toList();
                Navigator.pop(ctx);
                showDialog(
                  context: context,
                  builder: (_) => AlertDialog(
                    title: Text('抽到的学生（${picked.length}人）'),
                    content: Column(mainAxisSize: MainAxisSize.min, children: picked.map((s) => Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text(s, style: const TextStyle(fontSize: 18)))).toList()),
                    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('确定'))],
                  ),
                );
              },
              child: const Text('开始抽取'),
            ),
          ],
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
                  title: const Text('检查更新'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () async { await _api.checkUpdate(); await _pollStatus(); },
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
