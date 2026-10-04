import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/theme.dart';

// 回归测试：用户反馈"程序在后台做了什么这个框在浅色模式下看不见"。
// 根因是卡片用了 surfaceContainerLowest（纯白），而页面底色也很接近白色，
// 只剩一条极淡的边框 —— 白底白卡，投影上完全看不出"框"。
//
// 这里把三条设计约束钉死：
//   1. 卡片必须显式指定填充色和不透明的边框；
//   2. 浅色主题的页面底色不能是"接近白色"（否则白卡片没有依托）；
//   3. 卡片边框与页面底色要有可分辨的亮度差（也就是能看出框）。
void main() {
  final light = AppTheme.light();
  final dark = AppTheme.dark();

  Color borderColorOf(ThemeData t) {
    final shape = t.cardTheme.shape;
    expect(shape, isA<RoundedRectangleBorder>());
    final side = (shape as RoundedRectangleBorder).side;
    expect(side.style, BorderStyle.solid);
    expect(side.color.a, 1.0, reason: '边框不能半透明，浅色下会几乎看不见');
    return side.color;
  }

  test('卡片必须显式指定颜色（不能靠默认值）', () {
    expect(light.cardTheme.color, isNotNull);
    expect(dark.cardTheme.color, isNotNull);
  });

  test('浅色主题：页面底色不能接近纯白，白卡片才看得出"框"', () {
    final bg = light.scaffoldBackgroundColor.computeLuminance();
    expect(bg, lessThan(0.93),
        reason: '页面底色太亮（luminance=$bg），白色卡片会跟背景融在一起');
  });

  test('浅色主题：卡片边框与底色有明显亮度差', () {
    final diff =
        (borderColorOf(light).computeLuminance() -
                light.scaffoldBackgroundColor.computeLuminance())
            .abs();
    expect(diff, greaterThan(0.1), reason: '边框太淡（差值 $diff），看不出框');
  });

  test('深色主题：卡片填充与底色可分辨', () {
    final diff = (dark.cardTheme.color!.computeLuminance() -
            dark.scaffoldBackgroundColor.computeLuminance())
        .abs();
    expect(diff, greaterThan(0.004), reason: '深色下卡片与背景完全同色');
    // 深色下主要靠边框分辨
    final bd = (borderColorOf(dark).computeLuminance() -
            dark.cardTheme.color!.computeLuminance())
        .abs();
    expect(bd, greaterThan(0.01));
  });

  test('常用文本样式都携带颜色（避免继承链断裂后变成隐形文字）', () {
    for (final t in <ThemeData>[light, dark]) {
      for (final style in <TextStyle?>[
        t.textTheme.titleLarge,
        t.textTheme.titleMedium,
        t.textTheme.bodyLarge,
        t.textTheme.bodyMedium,
        t.textTheme.bodySmall,
        t.listTileTheme.titleTextStyle,
        t.listTileTheme.subtitleTextStyle,
      ]) {
        expect(style, isNotNull);
        expect(style!.color, isNotNull, reason: '样式缺少颜色: $style');
      }
    }
  });
}
