import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

/// 后端 API 服务封装。
/// 读取 D:\IdiotLaunch\data\backend_port 获取端口，连接本地 HTTP 后端。
class ApiService {
  static const String _dataDir = r'D:\IdiotLaunch\data';
  static const String _portFile = '$_dataDir\\backend_port';

  int? _port;
  bool _backendStarting = false;

  /// 获取后端基础 URL，如后端未运行则尝试启动。
  Future<String?> _baseUrl() async {
    _port ??= await _readPort();
    if (_port == null) {
      await _startBackend();
      _port = await _waitForPort(maxWait: 10);
    }
    if (_port == null) return null;
    return 'http://127.0.0.1:$_port';
  }

  Future<int?> _readPort() async {
    try {
      final f = File(_portFile);
      if (await f.exists()) {
        final content = await f.readAsString();
        final p = int.tryParse(content.trim());
        // 验证端口是否还活着
        if (p != null && await _pingPort(p)) return p;
      }
    } catch (_) {}
    return null;
  }

  Future<bool> _pingPort(int port) async {
    try {
      final resp = await http
          .get(Uri.parse('http://127.0.0.1:$port/api/version'))
          .timeout(const Duration(seconds: 2));
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<void> _startBackend() async {
    if (_backendStarting) return;
    _backendStarting = true;
    try {
      // 开发模式：用 python run.py --server
      // 打包后：用同目录下的 IdiotLaunchBackend.exe --server
      final exe = File(r'D:\IdiotLaunch\IdiotLaunchBackend.exe');
      if (await exe.exists()) {
        await Process.start(exe.path, ['--server'], mode: ProcessStartMode.detached);
      } else {
        // 开发模式 fallback
        await Process.start(
          'python',
          [r'D:\ID\idiot-launch\run.py', '--server'],
          mode: ProcessStartMode.detached,
        );
      }
    } catch (_) {}
  }

  Future<int?> _waitForPort({int maxWait = 10}) async {
    for (var i = 0; i < maxWait * 4; i++) {
      await Future.delayed(const Duration(milliseconds: 250));
      try {
        final f = File(_portFile);
        if (await f.exists()) {
          final p = int.tryParse((await f.readAsString()).trim());
          if (p != null && await _pingPort(p)) return p;
        }
      } catch (_) {}
    }
    return null;
  }

  Future<Map<String, dynamic>?> _get(String path) async {
    final base = await _baseUrl();
    if (base == null) return null;
    try {
      final resp = await http
          .get(Uri.parse('$base$path'))
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        return jsonDecode(utf8.decode(resp.bodyBytes));
      }
    } catch (_) {
      _port = null; // 连接失败，下次重新检测
    }
    return null;
  }

  Future<Map<String, dynamic>?> _post(String path,
      [Map<String, dynamic>? body]) async {
    final base = await _baseUrl();
    if (base == null) return null;
    try {
      final resp = await http
          .post(
            Uri.parse('$base$path'),
            headers: {'Content-Type': 'application/json'},
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 200) {
        return jsonDecode(utf8.decode(resp.bodyBytes));
      }
    } catch (_) {
      _port = null;
    }
    return null;
  }

  // ---- 状态 ----
  Future<Map<String, dynamic>?> getStatus() => _get('/api/status');
  Future<Map<String, dynamic>?> getVersion() => _get('/api/version');
  Future<Map<String, dynamic>?> getUpdateStatus() => _get('/api/update/status');

  // ---- 倒计时 ----
  Future<bool> startCountdown(String exam) async {
    final r = await _post('/api/countdown/start', {'exam': exam});
    return r?['success'] == true;
  }

  Future<bool> stopCountdown() async {
    final r = await _post('/api/countdown/stop');
    return r?['success'] == true;
  }

  Future<bool> openSettings() async {
    final r = await _post('/api/countdown/settings');
    return r?['success'] == true;
  }

  Future<bool> startCustomWallpaper() async {
    final r = await _post('/api/countdown/custom');
    return r?['success'] == true;
  }

  // ---- 早读 ----
  Future<Map<String, dynamic>?> getMorningConfig() => _get('/api/morning/config');
  Future<List<dynamic>> getMorningStudents() async {
    final r = await _get('/api/morning/students');
    return r?['students'] ?? [];
  }

  Future<Map<String, dynamic>?> loginMorning(
      String grade, String classNumber, String password, bool persistent) async {
    return _post('/api/morning/login', {
      'grade': grade,
      'class_number': classNumber,
      'password': password,
      'persistent': persistent,
    });
  }

  Future<bool> logoutMorning() async {
    final r = await _post('/api/morning/logout');
    return r?['success'] == true;
  }

  Future<bool> openMorning() async {
    final r = await _post('/api/morning/open');
    return r?['success'] == true;
  }

  // ---- 更新 ----
  Future<bool> checkUpdate() async {
    final r = await _post('/api/update/check');
    return r?['success'] == true;
  }

  Future<bool> installUpdate() async {
    final r = await _post('/api/update/install');
    return r?['success'] == true;
  }
}
