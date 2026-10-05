import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/theme.dart';
import 'package:idiot_launch/widgets/title_bar.dart';

// 回归测试：用户反馈"标题栏和壁纸设置的字体看不见"。
//
// 根因是有一批文字用了 `TextStyle(fontSize: xx)`（color 为 null），
// 一旦继承链断开就会变成看不见的文字（beta27 真实出现过）。
//
// 这里不再只检查"样式里有颜色"，而是**真的把控件渲染出来**，
// 逐个取 RichText 实际生效的颜色，按 WCAG 对比度标准校验：
// 普通文字 >= 4.5:1，大号文字 >= 3:1。
void main() {
  double contrast(Color fg, Color bg) {
    final a = fg.computeLuminance();
    final b = bg.computeLuminance();
    final hi = math.max(a, b);
    final lo = math.min(a, b);
    return (hi + 0.05) / (lo + 0.05);
  }

  /// 渲染 [child]，校验里面所有文字与 [background] 的对比度。
  Future<void> expectReadable(
    WidgetTester tester, {
    required ThemeData theme,
    required Widget child,
    required Color background,
    required String what,
  }) async {
    // 给足空间：避让 overflow，也不让文字被裁剪掉
    await tester.binding.setSurfaceSize(const Size(900, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      theme: theme,
      home: Scaffold(body: Center(child: child)),
    ));
    await tester.pumpAndSettle();

    final rich = tester.widgetList<RichText>(find.byType(RichText)).toList();
    expect(rich, isNotEmpty, reason: '$what 没有渲染出任何文字');

    var checked = 0;
    for (final r in rich) {
      final style = r.text.style;
      final color = style?.color;
      final content = r.text.toPlainText();
      if (content.trim().isEmpty) continue;
      // 图标也是 RichText（Material 图标字体），字形在私有区，
      // 它的颜色是按"悬停背景"设计的，不能拿页面底色来量。
      if (content.runes.every((int c) => c >= 0xE000 && c <= 0xF8FF)) continue;
      expect(color, isNotNull,
          reason: '$what 中"$content"没有颜色（color == null），继承链一断就会看不见');
      final size = style?.fontSize ?? 14;
      final bold = (style?.fontWeight ?? FontWeight.w400).value >=
          FontWeight.w600.value;
      // WCAG：>=18pt(24px) 或 >=14pt(18.66px) 加粗 算大字
      final large = size >= 24 || (bold && size >= 18.66);
      final min = large ? 3.0 : 4.5;
      final c = contrast(color!, background);
      expect(c, greaterThanOrEqualTo(min),
          reason: '$what 中"$content"对比度只有 ${c.toStringAsFixed(2)}:1'
              '（要求 >= $min），颜色 $color 叠在 $background 上');
      checked++;
    }
    expect(checked, greaterThan(0));
  }

  for (final entry in <String, ThemeData>{
    '浅色': AppTheme.light(),
    '深色': AppTheme.dark(),
  }.entries) {
    final name = entry.key;
    final theme = entry.value;
    final bg = theme.scaffoldBackgroundColor;
    final surface = theme.colorScheme.surface;

    testWidgets('$name主题：标题栏文字看得见', (tester) async {
      await expectReadable(tester,
          theme: theme,
          child: const SizedBox(width: 700, child: CustomTitleBar(title: '傻瓜启动器')),
          background: surface,
          what: '$name主题标题栏');
    });

    testWidgets('$name主题：正文/卡片/按钮文字看得见', (tester) async {
      await expectReadable(tester,
          theme: theme,
          child: SizedBox(
            width: 600,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text('普通正文，讲台前也要看得清'),
                const SizedBox(height: 8),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const <Widget>[
                        Text('卡片标题', style: TextStyle(fontSize: 18)),
                        SizedBox(height: 4),
                        Text('卡片里的正文'),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                const ListTile(
                  title: Text('列表标题'),
                  subtitle: Text('列表副标题'),
                  leading: Icon(Icons.info),
                ),
                const SizedBox(height: 8),
                Row(children: <Widget>[
                  TextButton(onPressed: () {}, child: const Text('文字按钮')),
                  const SizedBox(width: 8),
                  OutlinedButton(onPressed: () {}, child: const Text('描边按钮')),
                ]),
                const SizedBox(height: 8),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('开关项'),
                  subtitle: const Text('开关说明'),
                  value: true,
                  onChanged: (_) {},
                ),
              ],
            ),
          ),
          background: bg,
          what: '$name主题常用控件');
    });

    testWidgets('$name主题：预设按钮/滚轮文字看得见', (tester) async {
      await expectReadable(tester,
          theme: theme,
          child: SizedBox(
            width: 400,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                FilledButton.tonal(onPressed: () {}, child: const Text('25 分钟')),
                const SizedBox(height: 8),
                Text('上下拖动滚轮选时间',
                    style: TextStyle(color: theme.colorScheme.onSurfaceVariant)),
              ],
            ),
          ),
          background: bg,
          what: '$name主题预设');
    });
  }
}
