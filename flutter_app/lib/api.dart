import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

class ApiService {
  static const String _dataDir = r'D:\IdiotLaunch\data';
  static const String _portFile = '$_dataDir\\backend_port';
  int? _port;

  Future<int> _getPort() async {
    if (_port != null) return _port!;
    final f = File(_portFile);
    if (await f.exists()) {
      final content = await f.readAsString();
      _port = int.tryParse(content.trim());
    }
    if (_port == null) {
      await ensureBackend();
      _port = int.tryParse(await f.readAsString());
    }
    return _port!;
  }

  Future<void> ensureBackend() async {
    final f = File(_portFile);
    if (await f.exists()) {
      try {
        final p = int.tryParse((await f.readAsString()).trim());
        if (p != null) {
          final resp = await http.get(Uri.parse('http://127.0.0.1:$p/api/version')).timeout(const Duration(seconds: 2));
          if (resp.statusCode == 200) {
            _port = p;
            return;
          }
        }
      } catch (_) {}
    }
    // 启动后端
    final backendExe = File(r'D:\IdiotLaunch\backend\IdiotLaunchBackend.exe');
    if (await backendExe.exists()) {
      await Process.start(backendExe.path, ['--server'], mode: ProcessStartMode.detached);
    } else {
      // 开发环境：用 python 启动
      await Process.start('python', ['run.py', '--server'], mode: ProcessStartMode.detached);
    }
    // 等待后端启动
    for (int i = 0; i < 30; i++) {
      await Future.delayed(const Duration(milliseconds: 500));
      if (await f.exists()) {
        final p = int.tryParse((await f.readAsString()).trim());
        if (p != null) {
          try {
            final resp = await http.get(Uri.parse('http://127.0.0.1:$p/api/version')).timeout(const Duration(seconds: 2));
            if (resp.statusCode == 200) {
              _port = p;
              return;
            }
          } catch (_) {}
        }
      }
    }
    throw Exception('后端启动超时');
  }

  Future<Map<String, dynamic>> _get(String path) async {
    final port = await _getPort();
    final resp = await http.get(Uri.parse('http://127.0.0.1:$port$path')).timeout(const Duration(seconds: 10));
    if (resp.statusCode != 200) throw Exception('HTTP ${resp.statusCode}: ${resp.body}');
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _post(String path, [Map<String, dynamic>? body]) async {
    final port = await _getPort();
    final resp = await http.post(
      Uri.parse('http://127.0.0.1:$port$path'),
      headers: {'Content-Type': 'application/json'},
      body: body != null ? jsonEncode(body) : null,
    ).timeout(const Duration(seconds: 30));
    if (resp.statusCode != 200) throw Exception('HTTP ${resp.statusCode}: ${resp.body}');
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  // ===== 状态 =====
  Future<Map<String, dynamic>> getStatus() => _get('/api/status');
  Future<Map<String, dynamic>> getUpdateStatus() => _get('/api/update/status');
  Future<Map<String, dynamic>> getMorningConfig() => _get('/api/morning/config');

  // ===== 倒计时壁纸 =====
  Future<void> startCountdown(String exam) => _post('/api/countdown/start', {'exam': exam});
  Future<void> stopCountdown() => _post('/api/countdown/stop');
  Future<void> openCountdownSettings() => _post('/api/countdown/settings');
  Future<void> startCustomWallpaper() => _post('/api/countdown/custom');

  // ===== 早读 =====
  Future<bool> morningLogin(String identity, String password, bool persistent) async {
    final r = await _post('/api/morning/login', {
      'identity': identity,
      'password': password,
      'persistent': persistent,
    });
    return r['success'] == true;
  }

  Future<bool> morningLoginWithGrade(String grade, String classNumber, String password, bool persistent) async {
    final r = await _post('/api/morning/login', {
      'grade': grade,
      'class_number': classNumber,
      'password': password,
      'persistent': persistent,
    });
    return r['success'] == true;
  }

  Future<void> morningLogout() => _post('/api/morning/logout');
  Future<void> openMorningBrowser() => _post('/api/morning/open');

  Future<List<String>> getMorningStudents() async {
    final r = await _get('/api/morning/students');
    final list = r['students'] as List?;
    return list?.map((e) => e.toString()).toList() ?? [];
  }

  // ===== 更新 =====
  Future<void> checkUpdate() => _post('/api/update/check');
  Future<void> installUpdate() => _post('/api/update/install');

  // ===== 退出 =====
  Future<void> quit() => _post('/api/quit');

  // ===== 单实例激活窗口 =====
  Future<void> activateWindow() => _post('/api/activate');
  Future<void> clearActivate() => _post('/api/activate/clear');

  // ===== Countdown Desktop 设置 =====
  Future<Map<String, dynamic>> getCdConfig() => _get('/api/cd/config');
  Future<void> saveCdConfig(Map<String, dynamic> config) => _post('/api/cd/config', {'config': config});
  Future<void> testCdScreensaver() => _post('/api/cd/test-screensaver');
}
