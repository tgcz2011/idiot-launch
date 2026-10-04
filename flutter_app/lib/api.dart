import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'app_log.dart';

/// 后端 HTTP API 封装。
///
/// 约定：
///  * 端口文件在 %TEMP%\idiot_launch_backend_port，由后端写入。
///  * 所有 JSON 字段都用下面的 asXxx 兜底转换：后端给 int/给 null 都不会让界面崩
///    （历史 bug：`as double` 遇到整数进度直接抛异常，整个更新卡片渲染失败）。
class ApiService {
  static String get portFile =>
      '${Platform.environment['TEMP'] ?? Platform.environment['TMP'] ?? r'C:\Windows\Temp'}\\idiot_launch_backend_port';

  static String get backendExe => r'D:\IdiotLaunch\backend\IdiotLaunchBackend.exe';

  int? _port;

  // ---- 类型兜底 ----
  static double asDouble(dynamic v) => v is num ? v.toDouble() : 0.0;
  static int asInt(dynamic v) => v is num ? v.toInt() : 0;
  static bool asBool(dynamic v) => v == true;
  static String asString(dynamic v) => v == null ? '' : v.toString();

  // ---- 连接管理 ----
  Future<int> _getPort() async {
    if (_port != null) return _port!;
    final port = await _readPort();
    if (port != null) {
      _port = port;
      return port;
    }
    await ensureBackend();
    final p = await _readPort();
    if (p == null) throw Exception('后端没有写出端口文件');
    _port = p;
    return p;
  }

  Future<int?> _readPort() async {
    try {
      final f = File(portFile);
      if (!await f.exists()) return null;
      return int.tryParse((await f.readAsString()).trim());
    } catch (_) {
      return null;
    }
  }

  /// 确保后端在跑：先探测端口文件，不行就自己把后端拉起来。
  Future<void> ensureBackend() async {
    final existing = await _readPort();
    if (existing != null && await _ping(existing)) {
      _port = existing;
      return;
    }

    if (await File(backendExe).exists()) {
      AppLog.info('后端未运行，启动 $backendExe');
      await Process.start(backendExe, <String>['--server'],
          mode: ProcessStartMode.detached);
    } else {
      // 开发环境：源码运行
      AppLog.warn('未找到 $backendExe，尝试用 python 启动（开发模式）');
      await Process.start('python', <String>['run.py', '--server'],
          mode: ProcessStartMode.detached);
    }

    for (int i = 0; i < 30; i++) {
      await Future.delayed(const Duration(milliseconds: 500));
      final p = await _readPort();
      if (p != null && await _ping(p)) {
        _port = p;
        return;
      }
    }
    throw Exception('后端启动超时（15 秒），请点击「打开日志」把 ui.log / daemon.log 发给管理员');
  }

  Future<bool> _ping(int port) async {
    try {
      final resp = await http
          .get(Uri.parse('http://127.0.0.1:$port/api/version'))
          .timeout(const Duration(seconds: 2));
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ---- 基础请求 ----
  Future<Map<String, dynamic>> _get(String path,
      {Duration timeout = const Duration(seconds: 10)}) async {
    final port = await _getPort();
    final resp = await http
        .get(Uri.parse('http://127.0.0.1:$port$path'))
        .timeout(timeout);
    if (resp.statusCode != 200) {
      throw Exception('后端返回 HTTP ${resp.statusCode}');
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _post(String path,
      [Map<String, dynamic>? body,
      Duration timeout = const Duration(seconds: 30)]) async {
    final port = await _getPort();
    final resp = await http
        .post(Uri.parse('http://127.0.0.1:$port$path'),
            headers: const {'Content-Type': 'application/json'},
            body: body != null ? jsonEncode(body) : null)
        .timeout(timeout);
    if (resp.statusCode != 200) {
      throw Exception('后端返回 HTTP ${resp.statusCode}');
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  // ===== 状态 =====
  Future<Map<String, dynamic>> getStatus() => _get('/api/status');
  Future<Map<String, dynamic>> getUpdateStatus() => _get('/api/update/status');
  Future<Map<String, dynamic>> getMorningConfig() => _get('/api/morning/config');

  /// 后端是否活着（不抛异常版本）。
  Future<bool> isBackendAlive() async {
    try {
      final p = _port ?? await _readPort();
      if (p == null) return false;
      return await _ping(p);
    } catch (_) {
      return false;
    }
  }

  // ===== 倒计时壁纸 =====
  Future<bool> startCountdown(String exam) async {
    final r = await _post('/api/countdown/start', {'exam': exam});
    return asBool(r['success']);
  }

  Future<bool> stopCountdown() async {
    final r = await _post('/api/countdown/stop');
    return asBool(r['success']);
  }

  Future<bool> startCustomWallpaper() async =>
      asBool((await _post('/api/countdown/custom'))['success']);

  // ===== 早读 =====
  Future<Map<String, dynamic>> morningLogin(
      String grade, String classNumber, String password, bool persistent) {
    return _post('/api/morning/login', {
      'grade': grade,
      'class_number': classNumber,
      'password': password,
      'persistent': persistent,
    });
  }

  Future<void> morningLogout() => _post('/api/morning/logout');
  Future<void> openMorningBrowser() => _post('/api/morning/open');

  Future<List<Map<String, dynamic>>> getMorningStudents() async {
    final r = await _get('/api/morning/students');
    if (!asBool(r['success'])) {
      throw Exception(asString(r['error']).isEmpty ? '获取学生名单失败' : asString(r['error']));
    }
    final list = r['students'] as List?;
    return list?.map((e) => Map<String, dynamic>.from(e as Map)).toList() ??
        <Map<String, dynamic>>[];
  }

  // ===== 更新 =====
  Future<void> checkUpdate() => _post('/api/update/check');

  /// 触发"一键更新"。后端会回复后启动安装程序并退出本进程。
  Future<Map<String, dynamic>> installUpdate() => _post('/api/update/install');

  // ===== 设置 =====
  Future<Map<String, dynamic>> getSettings() => _get('/api/settings');
  Future<Map<String, dynamic>> saveSettings(Map<String, dynamic> patch) =>
      _post('/api/settings', patch);

  // ===== 其它 =====
  /// 弹托盘气泡通知。oncePerBoot=true 时由后端保证"每次开机只提示一次"，
  /// 返回里 shown 表示这次是否真的弹了（前端据此决定要不要再显示应用内提示）。
  Future<Map<String, dynamic>> notifyTray(String title, String message,
      {bool oncePerBoot = false}) async {
    try {
      return await _post(
        '/api/notify',
        <String, dynamic>{
          'title': title,
          'message': message,
          'once_per_boot': oncePerBoot,
        },
        const Duration(seconds: 5),
      );
    } catch (_) {
      return <String, dynamic>{'success': false, 'shown': false};
    }
  }

  Future<bool> openFolder(String path) async {
    try {
      final r = await _post('/api/open-folder', {'path': path},
          const Duration(seconds: 5));
      return asBool(r['success']);
    } catch (_) {
      return false;
    }
  }

  Future<void> quitAll() => _post('/api/quit');

  Future<void> activateWindow() => _post('/api/activate');
  Future<void> clearActivate() => _post('/api/activate/clear');

  // ===== Countdown Desktop 设置 =====
  Future<Map<String, dynamic>> getCdConfig() => _get('/api/cd/config');
  Future<Map<String, dynamic>> saveCdConfig(Map<String, dynamic> config) =>
      _post('/api/cd/config', {'config': config});
  Future<void> testCdScreensaver() => _post('/api/cd/test-screensaver');
}
