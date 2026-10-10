import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/theme.dart';
import 'package:idiot_launch/widgets/duration_picker.dart';

// 回归测试：用户实测"倒计时选择时间拖不动"。
//
// 根因有两个：
//  1. 滚轮控制器建在滚轮组件内部：页面一重建控制器就被重建，
//     拖动立刻被弹回原位，看上去就是"拖了没反应"。
//  2. Flutter 桌面端默认禁止**鼠标拖动**滚动（dragDevices 不含 mouse）。
//     教室里的希沃触摸屏大多把手指触摸提升成鼠标消息，于是"手指按在滚轮上拖"
//     什么都不动 —— 用户实测反馈"倒计时的拖动应该是为了触屏设计的"。
//     tester.drag 默认模拟的是 touch，所以只有第 3 条鼠标拖动测试能抓到这个问题。
//
// 这里把触摸拖动、鼠标拖动、鼠标滚轮三条路径都钉死。
void main() {
  Future<FixedExtentScrollController> pumpPicker(
    WidgetTester tester, {
    required void Function(int) onMinutes,
    required void Function(int) onHours,
    void Function(int)? onPreset,
    FixedExtentScrollController? hourCtrl,
    FixedExtentScrollController? minCtrl,
  }) async {
    final hc = hourCtrl ?? FixedExtentScrollController(initialItem: 0);
    final mc = minCtrl ?? FixedExtentScrollController(initialItem: 5);
    await tester.binding.setSurfaceSize(const Size(420, 620));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: StatefulBuilder(
            builder: (BuildContext ctx, StateSetter setState) => Center(
              child: SizedBox(
                width: 380,
                child: DurationPicker(
                  hourController: hc,
                  minuteController: mc,
                  hours: 0,
                  minutes: 5,
                  onHoursChanged: (int i) {
                    onHours(i);
                    setState(() {});
                  },
                  onMinutesChanged: (int i) {
                    onMinutes(i);
                    setState(() {});
                  },
                  onPreset: (int m) => onPreset?.call(m),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    addTearDown(() {
      hc.dispose();
      mc.dispose();
    });
    return mc;
  }

  testWidgets('两个滚轮都渲染出来了', (WidgetTester tester) async {
    await pumpPicker(tester, onMinutes: (_) {}, onHours: (_) {});
    expect(find.byType(ListWheelScrollView), findsNWidgets(2));
    expect(find.text('05:00'), findsOneWidget);
  });

  testWidgets('拖动分钟滚轮真的能改分钟', (WidgetTester tester) async {
    final seen = <int>[];
    final mc = await pumpPicker(tester, onMinutes: seen.add, onHours: (_) {});
    expect(mc.selectedItem, 5);

    await tester.drag(
      find.byType(ListWheelScrollView).last,
      const Offset(0, -132),
      warnIfMissed: false,
    );
    await tester.pumpAndSettle();

    expect(seen, isNotEmpty, reason: '拖动没有触发任何回调 —— 就是"拖不动"的症状');
    expect(seen.last, isNot(5), reason: '拖动后分钟数没变');
    expect(mc.selectedItem, seen.last, reason: '滚轮位置和回调给的值不一致（会被弹回原位）');
  });

  testWidgets('拖动小时滚轮真的能改小时', (WidgetTester tester) async {
    final seen = <int>[];
    await pumpPicker(tester, onMinutes: (_) {}, onHours: seen.add);
    await tester.drag(
      find.byType(ListWheelScrollView).first,
      const Offset(0, -132),
      warnIfMissed: false,
    );
    await tester.pumpAndSettle();
    expect(seen, isNotEmpty);
    expect(seen.last, greaterThan(0));
  });

  testWidgets('鼠标滚轮也能改时间（讲台鼠标没拖动习惯）', (WidgetTester tester) async {
    final seen = <int>[];
    await pumpPicker(tester, onMinutes: seen.add, onHours: (_) {});
    final center = tester.getCenter(find.byType(ListWheelScrollView).last);
    final pointer = TestPointer(1, PointerDeviceKind.mouse);
    await tester.sendEventToBinding(pointer.hover(center));
    await tester.sendEventToBinding(pointer.scroll(const Offset(0, 160)));
    await tester.pumpAndSettle();
    expect(seen, isNotEmpty, reason: '鼠标滚轮没有改变分钟数');
    expect(seen.last, isNot(5));
  });

  testWidgets('鼠标拖动滚轮也能改时间（希沃触摸=鼠标消息时走的就是这条）', (WidgetTester tester) async {
    final seen = <int>[];
    final mc = await pumpPicker(tester, onMinutes: seen.add, onHours: (_) {});
    expect(mc.selectedItem, 5);

    final center = tester.getCenter(find.byType(ListWheelScrollView).last);
    // 关键：kind 必须是 mouse。桌面端 Flutter 默认把鼠标排除在 dragDevices 之外，
    // 不禁用这个默认行为就会"拖了半天没反应"。
    final gesture = await tester.startGesture(
      center,
      kind: PointerDeviceKind.mouse,
      buttons: kPrimaryButton,
    );
    await tester.pump(const Duration(milliseconds: 20));
    await gesture.moveBy(const Offset(0, -50));
    await tester.pump();
    await gesture.moveBy(const Offset(0, -50));
    await tester.pump();
    await gesture.moveBy(const Offset(0, -50));
    await tester.pump(const Duration(milliseconds: 20));
    await gesture.up();
    await tester.pumpAndSettle();

    expect(seen, isNotEmpty, reason: '鼠标拖动滚轮没有任何反应 —— 触摸屏手指拖动就是这个症状');
    expect(seen.last, isNot(5), reason: '鼠标拖动后分钟数没变');
  });

  testWidgets('触摸拖动滚轮也能改时间', (WidgetTester tester) async {
    final seen = <int>[];
    final mc = await pumpPicker(tester, onMinutes: seen.add, onHours: (_) {});
    final center = tester.getCenter(find.byType(ListWheelScrollView).last);
    final gesture = await tester.startGesture(
      center,
      kind: PointerDeviceKind.touch,
    );
    await tester.pump(const Duration(milliseconds: 20));
    await gesture.moveBy(const Offset(0, -60));
    await tester.pump();
    await gesture.moveBy(const Offset(0, -60));
    await tester.pump(const Duration(milliseconds: 20));
    await gesture.up();
    await tester.pumpAndSettle();
    expect(seen, isNotEmpty, reason: '触摸拖动滚轮没有反应（直接手指拖的场景）');
    expect(seen.last, isNot(5));
    expect(mc.selectedItem, seen.last);
  });

  testWidgets('点滚轮上的数字直接跳到那一格（触摸屏最省事）', (WidgetTester tester) async {
    final seen = <int>[];
    final mc = await pumpPicker(tester, onMinutes: seen.add, onHours: (_) {});
    final minuteWheel = find.byType(ListWheelScrollView).last;
    // 起始是 5 分，可见的相邻格里有 06
    final six = find.descendant(of: minuteWheel, matching: find.text('06'));
    expect(six, findsOneWidget, reason: '06 应该就在可见范围内');
    await tester.tap(six);
    await tester.pumpAndSettle();
    expect(seen, isNotEmpty, reason: '点数字没有反应');
    expect(seen.last, 6, reason: '点 06 之后分钟数应该是 6');
    expect(mc.selectedItem, 6);
  });

  testWidgets('页面重建后滚轮位置不会被弹回（控制器在外部）', (WidgetTester tester) async {
    final hc = FixedExtentScrollController(initialItem: 0);
    final mc = FixedExtentScrollController(initialItem: 5);
    addTearDown(() {
      hc.dispose();
      mc.dispose();
    });
    await tester.binding.setSurfaceSize(const Size(420, 620));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    Widget build(int minutes) => MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: Center(
          child: SizedBox(
            width: 380,
            child: DurationPicker(
              hourController: hc,
              minuteController: mc,
              hours: 0,
              minutes: minutes,
              onHoursChanged: (_) {},
              onMinutesChanged: (_) {},
              onPreset: (_) {},
            ),
          ),
        ),
      ),
    );

    await tester.pumpWidget(build(5));
    await tester.pumpAndSettle();
    mc.jumpToItem(20);
    await tester.pumpAndSettle();
    expect(mc.selectedItem, 20);

    // 模拟页面状态变化导致的重建（比如选完时间后刷新显示）
    await tester.pumpWidget(build(20));
    await tester.pumpAndSettle();
    expect(mc.selectedItem, 20, reason: '重建后滚轮被弹回去了 —— 控制器不能建在滚轮控件内部');
  });

  testWidgets('点预设会回调对应的分钟数', (WidgetTester tester) async {
    final seen = <int>[];
    await pumpPicker(
      tester,
      onMinutes: (_) {},
      onHours: (_) {},
      onPreset: seen.add,
    );
    await tester.tap(find.text('25 分钟'));
    await tester.pumpAndSettle();
    expect(seen, <int>[25]);
  });

  testWidgets('打开"秒"后多出秒滚轮，显示 hh:mm:ss', (WidgetTester tester) async {
    final hc = FixedExtentScrollController(initialItem: 0);
    final mc = FixedExtentScrollController(initialItem: 0);
    final sc = FixedExtentScrollController(initialItem: 30);
    addTearDown(() {
      hc.dispose();
      mc.dispose();
      sc.dispose();
    });
    await tester.binding.setSurfaceSize(const Size(560, 620));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 460,
              child: DurationPicker(
                hourController: hc,
                minuteController: mc,
                hours: 0,
                minutes: 0,
                onHoursChanged: (_) {},
                onMinutesChanged: (_) {},
                onPreset: (_) {},
                showSeconds: true,
                secondController: sc,
                seconds: 30,
                onSecondsChanged: (_) {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(ListWheelScrollView), findsNWidgets(3));
    expect(find.text('00:00:30'), findsOneWidget);
  });
}
