/// 时间格式化（倒计时 / 秒表共用，便于单元测试）。
library;

String _two(int v) => v.toString().padLeft(2, '0');

/// 倒计时显示：不足 1 小时用 mm:ss，否则 hh:mm:ss。
String formatDuration(Duration d) {
  final total = d.isNegative ? Duration.zero : d;
  final h = total.inHours;
  final m = total.inMinutes % 60;
  final s = total.inSeconds % 60;
  return h > 0 ? '${_two(h)}:${_two(m)}:${_two(s)}' : '${_two(m)}:${_two(s)}';
}

/// 秒表显示：mm:ss.mmm（毫秒）。
String formatStopwatch(int milliseconds) {
  final ms = milliseconds < 0 ? 0 : milliseconds;
  final m = ms ~/ 60000;
  final s = (ms % 60000) ~/ 1000;
  final milli = ms % 1000;
  return '${_two(m)}:${_two(s)}.${milli.toString().padLeft(3, '0')}';
}

/// 剩余时间占比（0~1），用于进度显示。
double remainingRatio(Duration left, Duration total) {
  if (total.inMilliseconds <= 0) return 0;
  final r = left.inMilliseconds / total.inMilliseconds;
  return r.clamp(0.0, 1.0);
}
