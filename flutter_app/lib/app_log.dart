import 'dart:io';

/// 前端日志（替代原来散落的 boot_debug.log / subwindow_debug.log）。
///
/// 设计：
///  * 只写文件，不做任何 UI 操作；失败一律吞掉（日志绝不能影响主流程）。
///  * 每条都带时间戳与进程/窗口标识，方便在同一台机器上区分主窗口与子窗口。
///  * 单文件超过 512KB 时轮转一份 .1，避免教室机器上无限增长。
///  * 同步写盘，但调用点都很少（只记关键事件和异常），不再是每次轮询都写。
class AppLog {
  AppLog._();

  static const int _maxBytes = 512 * 1024;
  static const String _fileName = 'ui.log';

  static String? _cachedPath;
  static int _windowTag = 0;

  /// 子窗口在入口处设置一个标记，便于区分日志来源。
  static void setWindowTag(int tag) => _windowTag = tag;

  static String? _baseDir() {
    // 与后端保持一致：优先 D:\IdiotLaunch\data（冰点还原不影响），失败退回 %TEMP%
    for (final dir in <String?>[
      r'D:\IdiotLaunch\data',
      Platform.environment['TEMP'],
      Platform.environment['TMP'],
    ]) {
      if (dir == null || dir.isEmpty) continue;
      try {
        final d = Directory(dir);
        if (!d.existsSync()) d.createSync(recursive: true);
        return dir;
      } catch (_) {
        continue;
      }
    }
    return null;
  }

  static String? _path() {
    if (_cachedPath != null) return _cachedPath;
    final dir = _baseDir();
    if (dir == null) return null;
    _cachedPath = '$dir\\$_fileName';
    return _cachedPath;
  }

  static void _write(String level, String message) {
    try {
      final path = _path();
      if (path == null) return;
      final f = File(path);
      if (f.existsSync() && f.lengthSync() > _maxBytes) {
        final bak = File('$path.1');
        try {
          if (bak.existsSync()) bak.deleteSync();
          f.renameSync(bak.path);
        } catch (_) {}
      }
      final now = DateTime.now();
      final ts = '${now.year}-${_p(now.month)}-${_p(now.day)} '
          '${_p(now.hour)}:${_p(now.minute)}:${_p(now.second)}.${now.millisecond.toString().padLeft(3, '0')}';
      final tag = _windowTag == 0 ? 'main' : 'win$_windowTag';
      f.writeAsStringSync('[$ts][$tag][$level] $message\n',
          mode: FileMode.append, flush: false);
    } catch (_) {
      // 日志失败绝不影响功能
    }
  }

  static String _p(int v) => v.toString().padLeft(2, '0');

  static void info(String message) => _write('INFO', message);

  static void warn(String message) => _write('WARN', message);

  static void error(String message, [Object? error, StackTrace? stack]) {
    final buf = StringBuffer(message);
    if (error != null) buf.write(' | $error');
    if (stack != null) {
      final lines = stack.toString().split('\n');
      buf.write(' | ${lines.take(6).join(' <- ')}');
    }
    _write('ERROR', buf.toString());
  }
}
