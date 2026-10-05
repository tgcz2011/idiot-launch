import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/sub_window.dart';

// 回归测试：用户实测"倒计时/秒表窗口拖动不跟手"（beta28、beta29 两轮）。
//
// 真正的原因是：**Flutter 给的指针坐标是相对窗口的**。窗口一跟着指针动，
// 指针相对窗口的位置就跟着变，"指针走了多少"和"窗口走了多少"搅在一起。
// 用绝对位置会来回跳（实测窗口动 30px 又弹回原位），
// 用 delta 累加每步只剩一半（实测十步走 60%、反向 FAST-BACK 正好一半）。
//
// 所以：鼠标直接用 GetCursorPos 的屏幕绝对坐标；
// 触摸用"窗口当前位置 + 指针相对位移"把窗口自己的位移补回来。
void main() {
  test('鼠标：用屏幕绝对坐标，和 Flutter 的坐标语义无关', () {
    // 窗口在 (100,200)，光标按下时在屏幕 (500,500)
    final t = SubWindow.dragTarget(
      originX: 100,
      originY: 200,
      cursorStartX: 500,
      cursorStartY: 500,
      cursorX: 530, // 光标往右下走了 (30,20)
      cursorY: 520,
      startX: 0,
      startY: 0,
      x: 0,
      y: 0,
      scale: 1.25,
    );
    expect(t.x, 130, reason: '光标走多少窗口走多少，不乘 DPI（都是物理像素）');
    expect(t.y, 220);
  });

  test('鼠标：事件丢了也不会漂移（绝对坐标，不累加）', () {
    ({int x, int y}) at(int cx, int cy) => SubWindow.dragTarget(
          originX: 10,
          originY: 10,
          cursorStartX: 100,
          cursorStartY: 100,
          cursorX: cx,
          cursorY: cy,
          startX: 0,
          startY: 0,
          x: 0,
          y: 0,
          scale: 1.0,
        );
    expect(at(300, 400).x, 10 + 200);
    expect(at(300, 400).y, 10 + 300);
    // 回到起点也要回到原位
    expect(at(100, 100).x, 10);
    expect(at(100, 100).y, 10);
  });

  test('触摸：窗口当前位置 + 相对位移（把窗口自己的位移补回来）', () {
    // 窗口已经被拖到 (400,300)，指针相对窗口从 50 走到 80（逻辑），dpr=1.25
    final t = SubWindow.dragTarget(
      originX: 100,
      originY: 100,
      cursorStartX: 0,
      cursorStartY: 0,
      windowNowX: 400,
      windowNowY: 300,
      startX: 50,
      startY: 50,
      x: 80,
      y: 70,
      scale: 1.25,
    );
    // 相对位移 (30,20) 逻辑 → (37.5,25) 物理
    expect(t.x, 400 + 38);
    expect(t.y, 300 + 25);
  });

  test('触摸：1:1 跟手的自洽性 —— 窗口完全跟上时相对位移不再增长', () {
    // 窗口起始 100，指针相对窗口起点 20；窗口跟到 140 后
    // 指针相对窗口仍是 20（因为窗口跟着走了），此时目标应还是 140
    final t = SubWindow.dragTarget(
      originX: 100,
      originY: 0,
      cursorStartX: 0,
      cursorStartY: 0,
      windowNowX: 140,
      windowNowY: 0,
      startX: 20,
      startY: 0,
      x: 20,
      y: 0,
      scale: 1.0,
    );
    expect(t.x, 140, reason: '不动就是不动，不能因为"相对位移变小"而往回缩');
  });

  test('拿不到窗口/光标位置时退回"原位 + 位移"', () {
    final t = SubWindow.dragTarget(
      originX: -50,
      originY: 30,
      cursorStartX: 0,
      cursorStartY: 0,
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
