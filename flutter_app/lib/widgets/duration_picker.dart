import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/material.dart';

import '../format.dart';

/// 倒计时的"选时长"控件：大号显示 + 预设按钮 + 时/分滚轮。
///
/// 单独抽出来是为了能**单测拖动**（用户实测反馈"倒计时时间拖不动"）。
///
/// 关键点：
///  1. [hourController] / [minuteController] 必须由**外部**持有。
///     以前控制器建在滚轮组件内部，页面一重建控制器就被重建，
///     拖动立刻被弹回原位 —— 表现就是"拖了没反应"。
///  2. 滚轮必须允许**鼠标/触摸/触控笔**拖动（见 [_Wheel] 里的 ScrollConfiguration）。
///     Flutter 桌面端默认把鼠标排除在 dragDevices 之外（只能用滚轮滚），
///     而教室里的希沃触摸屏大多把手指触摸提升成鼠标消息 —— 结果就是
///     "手指在滚轮上拖，什么都不动"。拖动才是主交互（触摸屏），滚轮只是附带。
class DurationPicker extends StatelessWidget {
  const DurationPicker({
    super.key,
    required this.hourController,
    required this.minuteController,
    required this.hours,
    required this.minutes,
    required this.onHoursChanged,
    required this.onMinutesChanged,
    required this.onPreset,
    this.presets = const <int>[5, 10, 15, 25, 45, 60],
  });

  final FixedExtentScrollController hourController;
  final FixedExtentScrollController minuteController;
  final int hours;
  final int minutes;
  final ValueChanged<int> onHoursChanged;
  final ValueChanged<int> onMinutesChanged;
  final ValueChanged<int> onPreset;
  final List<int> presets;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final picked = Duration(hours: hours, minutes: minutes);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            formatDuration(picked),
            style: TextStyle(
              fontSize: 42,
              fontWeight: FontWeight.w800,
              color: scheme.primary,
              fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: presets
                .map(
                  (m) => SizedBox(
                    width: 106,
                    height: 46,
                    child: FilledButton.tonal(
                      onPressed: () => onPreset(m),
                      child: Text(
                        m == 60 ? '1 小时' : '$m 分钟',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
          const SizedBox(height: 14),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              _Wheel(
                scheme: scheme,
                controller: hourController,
                count: 13,
                unit: '时',
                onChanged: onHoursChanged,
              ),
              const SizedBox(width: 4),
              _Wheel(
                scheme: scheme,
                controller: minuteController,
                count: 60,
                unit: '分',
                onChanged: onMinutesChanged,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Wheel extends StatelessWidget {
  const _Wheel({
    required this.scheme,
    required this.controller,
    required this.count,
    required this.unit,
    required this.onChanged,
  });

  final ColorScheme scheme;
  final FixedExtentScrollController controller;
  final int count;
  final String unit;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Container(
          width: 96,
          height: 132,
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: <Widget>[
              // 当前选中行的高亮条
              Container(
                height: 44,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: scheme.primaryContainer.withValues(alpha: 0.55),
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
              ScrollConfiguration(
                // Flutter 桌面端默认把鼠标排除在 dragDevices 之外（桌面习惯是滚轮），
                // 而触摸屏（希沃）上手指拖动又常常被 Windows 提升成鼠标消息，
                // 于是"手指按在滚轮上拖"完全没反应。这里显式允许所有指针类型拖动：
                // 拖动是主交互，滚轮只是附带。
                behavior: ScrollConfiguration.of(context).copyWith(
                  dragDevices: const <PointerDeviceKind>{
                    PointerDeviceKind.touch,
                    PointerDeviceKind.mouse,
                    PointerDeviceKind.stylus,
                    PointerDeviceKind.invertedStylus,
                    PointerDeviceKind.trackpad,
                    PointerDeviceKind.unknown,
                  },
                ),
                child: ListWheelScrollView.useDelegate(
                  controller: controller,
                  itemExtent: 44,
                  diameterRatio: 1.8,
                  perspective: 0.002,
                  physics: const FixedExtentScrollPhysics(),
                  onSelectedItemChanged: onChanged,
                  childDelegate: ListWheelChildBuilderDelegate(
                    childCount: count,
                    // 触摸屏上"点数字"比"拖到数字"更省事：
                    // 点哪一格就滚到哪一格（拖动时这个 tap 会被拖动抢掉，不冲突）。
                    builder: (BuildContext ctx, int i) => GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => controller.animateToItem(
                        i,
                        duration: const Duration(milliseconds: 140),
                        curve: Curves.easeOut,
                      ),
                      child: Center(
                        child: Text(
                          i.toString().padLeft(2, '0'),
                          style: TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.w600,
                            color: scheme.onSurface,
                            fontFeatures: const <FontFeature>[
                              FontFeature.tabularFigures(),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6),
          child: Text(
            unit,
            style: TextStyle(fontSize: 16, color: scheme.onSurfaceVariant),
          ),
        ),
      ],
    );
  }
}
