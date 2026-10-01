import 'dart:async';
import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';
import 'api.dart';
import 'timer_page.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();
  const windowOptions = WindowOptions(
    size: Size(520, 680),
    minimumSize: Size(420, 520),
    center: true,
    title: '傻瓜启动器',
  );
  await windowManager.waitUntilReadyToShow(windowOptions, () async {
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
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF2F6B4F),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF8F9FA),
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
  final ApiService _api = ApiService();
  int _selectedIndex = 0;
  Map<String, dynamic>? _status;
  Timer? _pollTimer;
  bool _countdownRunning = false;
  bool _morningLoggedIn = false;
  String? _pendingVersion;

  static const _pages = [
    NavigationRailDestination(
      icon: Icon(Icons.timer_outlined),
      selectedIcon: Icon(Icons.timer),
      label: Text('倒计时'),
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
    _refreshStatus();
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) => _refreshStatus());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _refreshStatus() async {
    final s = await _api.getStatus();
    if (s != null && mounted) {
      setState(() {
        _status = s;
        _countdownRunning = s['countdown_running'] == true;
        _morningLoggedIn = s['morning_logged_in'] == true;
        _pendingVersion = s['pending_version'];
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('傻瓜启动器', style: TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: false,
        actions: [
          _UpdateIndicator(
            hasUpdate: _pendingVersion != null,
            pendingVersion: _pendingVersion,
            onTap: () => _showUpdateDialog(),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Row(
        children: [
          NavigationRail(
            selectedIndex: _selectedIndex,
            onDestinationSelected: (i) => setState(() => _selectedIndex = i),
            destinations: _pages,
            labelType: NavigationRailLabelType.all,
            minWidth: 72,
            backgroundColor: Colors.white,
          ),
          const VerticalDivider(width: 1),
          Expanded(child: _buildPage()),
        ],
      ),
    );
  }

  Widget _buildPage() {
    switch (_selectedIndex) {
      case 0:
        return _CountdownPage(
          api: _api,
          countdownRunning: _countdownRunning,
          onAction: _refreshStatus,
        );
      case 1:
        return _ToolsPage(api: _api, morningLoggedIn: _morningLoggedIn);
      case 2:
        return _MorningPage(
          api: _api,
          loggedIn: _morningLoggedIn,
          onChanged: _refreshStatus,
        );
      case 3:
        return _SettingsPage(api: _api, status: _status);
      default:
        return const SizedBox.shrink();
    }
  }

  void _showUpdateDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('更新详情'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('当前版本：${_status?['version'] ?? '未知'}'),
            if (_pendingVersion != null)
              Text('待更新版本：$_pendingVersion',
                  style: const TextStyle(color: Colors.green)),
            const SizedBox(height: 8),
            Text('守护进程：${(_status?['daemon']?['activity'] ?? '空闲')}'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () async {
              await _api.checkUpdate();
              if (mounted) Navigator.pop(ctx);
            },
            child: const Text('立即检查'),
          ),
          if (_pendingVersion != null)
            FilledButton(
              onPressed: () async {
                await _api.installUpdate();
                if (mounted) Navigator.pop(ctx);
              },
              child: const Text('立即更新'),
            ),
        ],
      ),
    );
  }
}

// ---- 更新状态指示器 ----
class _UpdateIndicator extends StatelessWidget {
  final bool hasUpdate;
  final String? pendingVersion;
  final VoidCallback onTap;

  const _UpdateIndicator({
    required this.hasUpdate,
    required this.pendingVersion,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: hasUpdate ? Colors.green : Colors.grey[300],
        ),
        child: Icon(
          hasUpdate ? Icons.system_update : Icons.check_circle_outline,
          size: 20,
          color: hasUpdate ? Colors.white : Colors.grey[600],
        ),
      ),
    );
  }
}

// ---- 倒计时页面 ----
class _CountdownPage extends StatelessWidget {
  final ApiService api;
  final bool countdownRunning;
  final VoidCallback onAction;

  const _CountdownPage({
    required this.api,
    required this.countdownRunning,
    required this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        _BigButton(
          icon: Icons.school,
          label: '中考倒计时',
          subtitle: '启动中考倒计时壁纸',
          color: const Color(0xFFE74C3C),
          onTap: () async {
            await api.startCountdown('zhongkao');
            onAction();
          },
        ),
        const SizedBox(height: 14),
        _BigButton(
          icon: Icons.school_outlined,
          label: '高考倒计时',
          subtitle: '启动高考倒计时壁纸',
          color: const Color(0xFF3498DB),
          onTap: () async {
            await api.startCountdown('gaokao');
            onAction();
          },
        ),
        const SizedBox(height: 14),
        _BigButton(
          icon: Icons.wallpaper,
          label: '自定义壁纸&屏保',
          subtitle: '启动用户配置的壁纸',
          color: const Color(0xFF9B59B6),
          onTap: () async {
            await api.startCustomWallpaper();
            onAction();
          },
        ),
        const SizedBox(height: 14),
        _BigButton(
          icon: Icons.stop,
          label: '关闭倒计时',
          subtitle: countdownRunning ? '通知壁纸优雅退出' : '当前未运行',
          color: const Color(0xFF7F8C8D),
          enabled: countdownRunning,
          onTap: () async {
            await api.stopCountdown();
            onAction();
          },
        ),
        const SizedBox(height: 14),
        _BigButton(
          icon: Icons.tune,
          label: '壁纸&屏保设置',
          subtitle: '打开 Countdown Desktop 设置',
          color: const Color(0xFF2F6B4F),
          onTap: () => api.openSettings(),
        ),
      ],
    );
  }
}

class _BigButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;
  final bool enabled;

  const _BigButton({
    required this.icon,
    required this.label,
    required this.subtitle,
    required this.color,
    required this.onTap,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1.0 : 0.45,
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        elevation: 1,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: enabled ? onTap : null,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
            child: Row(
              children: [
                Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(icon, color: color, size: 28),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(label,
                          style: const TextStyle(
                              fontSize: 17, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 2),
                      Text(subtitle,
                          style: TextStyle(
                              fontSize: 13, color: Colors.grey[600])),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: Colors.grey[400]),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---- 工具页面 ----
class _ToolsPage extends StatelessWidget {
  final ApiService api;
  final bool morningLoggedIn;

  const _ToolsPage({required this.api, required this.morningLoggedIn});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        _BigButton(
          icon: Icons.hourglass_empty,
          label: '倒计时',
          subtitle: '可设置时长，结束后铃声提醒',
          color: const Color(0xFFE67E22),
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const TimerPage()),
          ),
        ),
        const SizedBox(height: 14),
        _BigButton(
          icon: Icons.timer,
          label: '秒表',
          subtitle: '支持记次、暂停、重置',
          color: const Color(0xFF1ABC9C),
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const StopwatchPage()),
          ),
        ),
        const SizedBox(height: 14),
        _BigButton(
          icon: Icons.people_alt,
          label: '随机抽学生',
          subtitle: morningLoggedIn ? '从当前班级随机抽取' : '需要先登录早读',
          color: const Color(0xFF8E44AD),
          enabled: morningLoggedIn,
          onTap: () => _showStudentPicker(context),
        ),
      ],
    );
  }

  void _showStudentPicker(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => _StudentPickerDialog(api: api),
    );
  }
}

class _StudentPickerDialog extends StatefulWidget {
  final ApiService api;
  const _StudentPickerDialog({required this.api});

  @override
  State<_StudentPickerDialog> createState() => _StudentPickerDialogState();
}

class _StudentPickerDialogState extends State<_StudentPickerDialog> {
  int _count = 1;
  List<dynamic>? _students;
  List<dynamic>? _picked;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final list = await widget.api.getMorningStudents();
    if (mounted) {
      setState(() {
        _students = list;
        _loading = false;
      });
    }
  }

  void _pick() {
    if (_students == null || _students!.isEmpty) return;
    final pool = List<dynamic>.from(_students!);
    pool.shuffle();
    setState(() {
      _picked = pool.take(_count.clamp(1, pool.length)).toList();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('随机抽学生'),
      content: SizedBox(
        width: 320,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      const Text('抽取人数：'),
                      IconButton(
                        icon: const Icon(Icons.remove_circle_outline),
                        onPressed: () =>
                            setState(() => _count = (_count - 1).clamp(1, 99)),
                      ),
                      Text('$_count',
                          style: const TextStyle(
                              fontSize: 20, fontWeight: FontWeight.bold)),
                      IconButton(
                        icon: const Icon(Icons.add_circle_outline),
                        onPressed: () =>
                            setState(() => _count = (_count + 1).clamp(1, 99)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  if (_picked != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.green.withOpacity(0.08),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Column(
                        children: _picked!
                            .map((s) => Padding(
                                  padding:
                                      const EdgeInsets.symmetric(vertical: 4),
                                  child: Text(
                                    '${s['student_no']}号 ${s['name']}',
                                    style: const TextStyle(
                                        fontSize: 18,
                                        fontWeight: FontWeight.w600),
                                  ),
                                ))
                            .toList(),
                      ),
                    ),
                ],
              ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('关闭')),
        FilledButton(onPressed: _pick, child: const Text('抽取')),
      ],
    );
  }
}

// ---- 早读页面 ----
class _MorningPage extends StatefulWidget {
  final ApiService api;
  final bool loggedIn;
  final VoidCallback onChanged;

  const _MorningPage({
    required this.api,
    required this.loggedIn,
    required this.onChanged,
  });

  @override
  State<_MorningPage> createState() => _MorningPageState();
}

class _MorningPageState extends State<_MorningPage> {
  final _gradeCtrl = TextEditingController(text: '9');
  final _classCtrl = TextEditingController(text: '1');
  final _passCtrl = TextEditingController();
  bool _persistent = true;
  bool _loggingIn = false;
  String? _loginError;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        _BigButton(
          icon: Icons.menu_book,
          label: '打开早晚读',
          subtitle: '内嵌浏览器打开早读网页',
          color: const Color(0xFF2F6B4F),
          onTap: () => widget.api.openMorning(),
        ),
        const SizedBox(height: 24),
        if (!widget.loggedIn) ...[
          const Text('班级登录',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
          const Text(
            '注意：先选年级，再填班级号（初中 01-14，高中 01-11）；初始密码 admin+班号（一班=admin01），密码可在教师管理界面修改。',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _gradeCtrl,
                  decoration: const InputDecoration(
                    labelText: '年级',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _classCtrl,
                  decoration: const InputDecoration(
                    labelText: '班级号',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _passCtrl,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: '密码',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Checkbox(
                value: _persistent,
                onChanged: (v) => setState(() => _persistent = v ?? true),
              ),
              const Text('持久登录（重启后保留）'),
            ],
          ),
          if (_loginError != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(_loginError!,
                  style: const TextStyle(color: Colors.red, fontSize: 13)),
            ),
          FilledButton(
            onPressed: _loggingIn ? null : _doLogin,
            child: Text(_loggingIn ? '登录中...' : '登录'),
          ),
        ] else ...[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('已登录',
                      style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  FutureBuilder<Map<String, dynamic>?>(
                    future: widget.api.getMorningConfig(),
                    builder: (context, snap) {
                      final cfg = snap.data;
                      return Text(
                        '班级：${cfg?['grade'] ?? '-'}-${cfg?['class_number'] ?? '-'}\n'
                        '持久登录：${cfg?['persistent'] == true ? '是' : '否'}',
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    icon: const Icon(Icons.logout),
                    label: const Text('退出登录'),
                    onPressed: () async {
                      await widget.api.logoutMorning();
                      widget.onChanged();
                    },
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }

  Future<void> _doLogin() async {
    setState(() {
      _loggingIn = true;
      _loginError = null;
    });
    final r = await widget.api.loginMorning(
      _gradeCtrl.text.trim(),
      _classCtrl.text.trim(),
      _passCtrl.text,
      _persistent,
    );
    if (!mounted) return;
    setState(() => _loggingIn = false);
    if (r?['success'] == true) {
      widget.onChanged();
    } else {
      setState(() => _loginError = r?['error'] ?? '登录失败');
    }
  }
}

// ---- 设置页面 ----
class _SettingsPage extends StatelessWidget {
  final ApiService api;
  final Map<String, dynamic>? status;

  const _SettingsPage({required this.api, required this.status});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('关于',
                    style: TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text('版本：${status?['version'] ?? '未知'}'),
                const Text('傻瓜启动器 — 专为学校电脑设计'),
                const Text('内嵌 Countdown Desktop（特供版）'),
                const Text('开源许可证：GPL-3.0'),
                const Text('作者：陈彦均 + 豆包 AI'),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('更新',
                    style: TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text('守护进程：${status?['daemon']?['activity'] ?? '空闲'}'),
                if (status?['pending_version'] != null)
                  Text('待更新：${status?['pending_version']}',
                      style: const TextStyle(color: Colors.green)),
                const SizedBox(height: 12),
                Row(
                  children: [
                    OutlinedButton(
                      onPressed: () => api.checkUpdate(),
                      child: const Text('检查更新'),
                    ),
                    const SizedBox(width: 12),
                    if (status?['pending_version'] != null)
                      FilledButton(
                        onPressed: () => api.installUpdate(),
                        child: const Text('立即更新'),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
