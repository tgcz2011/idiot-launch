import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/format.dart';

// 说明：原来的 widget_test 直接 pump 整个 App，会去调 window_manager /
// desktop_multi_window 的平台通道，在测试宿主里必然失败。这里改成对纯逻辑做测试。
void main() {
  group('formatDuration', () {
    test('不足一小时显示 mm:ss', () {
      expect(formatDuration(const Duration(minutes: 5)), '05:00');
      expect(formatDuration(const Duration(seconds: 59)), '00:59');
      expect(formatDuration(Duration.zero), '00:00');
    });

    test('超过一小时显示 hh:mm:ss', () {
      expect(formatDuration(const Duration(hours: 1, minutes: 2, seconds: 3)),
          '01:02:03');
      expect(formatDuration(const Duration(hours: 12)), '12:00:00');
    });

    test('负数按 0 处理（超时后不显示负数）', () {
      expect(formatDuration(const Duration(seconds: -5)), '00:00');
    });
  });

  group('formatStopwatch', () {
    test('毫秒换算成 mm:ss.mmm', () {
      expect(formatStopwatch(0), '00:00.000');
      expect(formatStopwatch(1234), '00:01.234');
      expect(formatStopwatch(61000), '01:01.000');
      expect(formatStopwatch(3661234), '61:01.234');
    });
  });

  group('remainingRatio', () {
    test('夹在 0~1 之间', () {
      expect(remainingRatio(const Duration(seconds: 5), const Duration(seconds: 10)), 0.5);
      expect(remainingRatio(const Duration(seconds: 20), const Duration(seconds: 10)), 1.0);
      expect(remainingRatio(const Duration(seconds: -1), const Duration(seconds: 10)), 0.0);
      expect(remainingRatio(const Duration(seconds: 1), Duration.zero), 0.0);
    });
  });
}
