import 'dart:math' as math;

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/theme.dart';
import 'package:idiot_launch/widgets/title_bar.dart';

// 回归测试：用户反馈"标题栏和壁纸设置的字体看不见"、"关闭按钮的 × 看不见"。
//
// 根因是有一批文字用了 `TextStyle(fontSize: xx)`（color 为 null），
// 一旦继承链断开就会变成看不见的文字（beta27 真实出现过）；
// 后来关闭按钮又反过来用了一个"只在悬停时才成立"的颜色
// （onError 在浅色模式下是白色，平时叠在白底上 → × 直接消失，beta29）。
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

  bool isIconGlyph(String s) =>
      s.runes.isNotEmpty &&
      s.runes.every((int c) => c >= 0xE000 && c <= 0xF8FF);

  /// 取所有渲染出来的文字（含图标字形）实际生效的颜色。
  List<({String text, Color? color, double size, FontWeight weight})> readTexts(
      WidgetTester tester) {
    final out = <({String text, Color? color, double size, FontWeight weight})>[];
    for (final r in tester.widgetList<RichText>(find.byType(RichText))) {
      final content = r.text.toPlainText();
      if (content.trim().isEmpty) continue;
      final style = r.text.style;
      out.add((
        text: content,
        color: style?.color,
        size: style?.fontSize ?? 14,
        weight: style?.fontWeight ?? FontWeight.w400,
      ));
    }
    return out;
  }

  double minFor(
      ({String text, Color? color, double size, FontWeight weight}) t) {
    final bold = t.weight.value >= FontWeight.w600.value;
    // WCAG：>=18pt(24px) 或 >=14pt(18.66px) 加粗 算大字
    final large = t.size >= 24 || (bold && t.size >= 18.66);
    return large ? 3.0 : 4.5;
  }

  /// 渲染 [child]，校验里面所有文字与 [background] 的对比度。
  ///
  /// [includeIcons] 打开时把图标字形也算进来（用 [iconBackground]，
  /// 默认同 [background]）—— 用于校验"平时状态"下的按钮图标。
  Future<void> expectReadable(
    WidgetTester tester, {
    required ThemeData theme,
    required Widget child,
    required Color background,
    required String what,
    bool includeIcons = false,
    Color? iconBackground,
  }) async {
    // 给足空间：避让 overflow，也不让文字被裁剪掉
    await tester.binding.setSurfaceSize(const Size(900, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      theme: theme,
      home: Scaffold(body: Center(child: child)),
    ));
    await tester.pumpAndSettle();

    final texts = readTexts(tester);
    expect(texts, isNotEmpty, reason: '$what 没有渲染出任何文字');

    var checked = 0;
    for (final t in texts) {
      final icon = isIconGlyph(t.text);
      // 图标字形的颜色可能按"悬停背景"设计，默认不参与页面底色校验
      if (icon && !includeIcons) continue;
      expect(t.color, isNotNull,
          reason: '$what 中"${t.text}"没有颜色（color == null），继承链一断就会看不见');
      final bg = icon ? (iconBackground ?? background) : background;
      final min = minFor(t);
      final c = contrast(t.color!, bg);
      expect(c, greaterThanOrEqualTo(min),
          reason: '$what 中"${t.text}"对比度只有 ${c.toStringAsFixed(2)}:1'
              '（要求 >= $min），颜色 ${t.color} 叠在 $bg 上');
      checked++;
    }
    expect(checked, greaterThan(0), reason: '$what 一个颜色都没校验到');
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

    testWidgets('$name主题：标题栏三个按钮的图标看得见（含关闭 ×）', (tester) async {
      // beta29 的 bug：关闭按钮平时就用 onError —— 浅色模式下 onError 是白色，
      // 叠在白底上，× 直接消失。这条测试就是钉住"平时状态"。
      await expectReadable(tester,
          theme: theme,
          includeIcons: true,
          child: Material(
            color: surface,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                TitleBarButton(icon: Icons.remove, onPressed: () {}),
                TitleBarButton(icon: Icons.crop_square, onPressed: () {}),
                TitleBarButton(
                    icon: Icons.close, isClose: true, onPressed: () {}),
              ],
            ),
          ),
          background: surface,
          what: '$name主题标题栏按钮');
    });

    testWidgets('$name主题：关闭按钮悬停变红底时图标仍然看得见', (tester) async {
      await tester.binding.setSurfaceSize(const Size(400, 300));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
        theme: theme,
        home: Scaffold(
          body: Center(
            child: TitleBarButton(
                icon: Icons.close, isClose: true, onPressed: () {}),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // 真的把鼠标移上去，触发悬停态
      final gesture = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await gesture.addPointer(location: Offset.zero);
      addTearDown(gesture.removePointer);
      await tester.pump();
      await gesture.moveTo(tester.getCenter(find.byType(TitleBarButton)));
      await tester.pumpAndSettle();

      final icons = readTexts(tester).where((t) => isIconGlyph(t.text)).toList();
      expect(icons, isNotEmpty, reason: '$name主题关闭按钮没渲染出图标');
      for (final t in icons) {
        final c = contrast(t.color!, theme.colorScheme.error);
        expect(c, greaterThanOrEqualTo(3.0),
            reason: '$name主题关闭按钮悬停时图标对比度只有 '
                '${c.toStringAsFixed(2)}:1（红底 ${theme.colorScheme.error}）');
      }
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
