import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/sub_window.dart';

// 回归测试：用户实测"倒计时/秒表窗口拖动不跟手"。
//
// 根因：Flutter 的手势坐标是**逻辑**像素，SetWindowPos 要**物理**像素。
// 以前把逻辑像素的位移直接当物理像素用，在 125% 缩放的屏幕上
// 窗口只走 80% 的距离，越拖越落后（150% 时只走 2/3）。
void main() {
  test('拖动位移要按 DPI 缩放换算成物理像素', () {
    final t = SubWindow.dragTarget(
      originX: 100,
      originY: 200,
      startX: 50,
      startY: 60,
      x: 150, // 逻辑像素：指针往右 100
      y: 260, // 逻辑像素：指针往下 200
      scale: 1.25, // 125% 缩放
    );
    expect(t.x, 100 + 125, reason: '逻辑 100 * 1.25 = 物理 125');
    expect(t.y, 200 + 250, reason: '逻辑 200 * 1.25 = 物理 250');
  });

  test('100% 缩放下位移不变', () {
    final t = SubWindow.dragTarget(
      originX: 0,
      originY: 0,
      startX: 500,
      startY: 500,
      x: 480,
      y: 470,
      scale: 1.0,
    );
    expect(t.x, -20);
    expect(t.y, -30);
  });

  test('用绝对位置：中途丢事件也不会累积漂移', () {
    // 起始窗口位置 (10, 10)，指针从 (0,0) 开始
    ({int x, int y}) at(double x, double y) => SubWindow.dragTarget(
          originX: 10,
          originY: 10,
          startX: 0,
          startY: 0,
          x: x,
          y: y,
          scale: 2.0,
        );
    // 直接跳到 (30, 40)（中间的移动事件被认为丢了）也要落在正确位置
    expect(at(30, 40).x, 10 + 60);
    expect(at(30, 40).y, 10 + 80);
  });

  test('高 DPI（150%）同样跟手', () {
    final t = SubWindow.dragTarget(
      originX: -50,
      originY: 30,
      startX: 10,
      startY: 10,
      x: 110,
      y: -90,
      scale: 1.5,
    );
    expect(t.x, -50 + 150);
    expect(t.y, 30 - 150);
  });
}
