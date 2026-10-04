import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_log.dart';
import 'format.dart';
import 'sub_window.dart';

/// 倒计时 / 秒表（独立子窗口）。
///
/// 窗口由 desktop_multi_window 创建，样式与位置交给 [SubWindow]（非阻塞 FFI）。
/// 设计目标：老师站在讲台/大屏幕前，一两次点击就能用，字大、按钮大。
class TimerPage extends StatefulWidget {
  const TimerPage({super.key});

  @override
  State<TimerPage> createState() => _TimerPageState();
}

enum _Phase { idle, running, paused, overtime }

class _TimerPageState extends State<TimerPage> {
  final SubWindow _win = SubWindow('timer');
  final AudioPlayer _player = AudioPlayer();
  final FocusNode _focus = FocusNode();

  _Phase _phase = _Phase.idle;
  int _pickHours = 0;
  int _pickMinutes = 5;
  int _totalSeconds = 0;
  DateTime? _endAt;
  Duration _remainingAtPause = Duration.zero;
  Timer? _tick;
  bool _alarmPlayed = false;
  bool _fullscreen = false;
  String? _audioWarning;

  static const List<int> _presetMinutes = <int>[5, 10, 15, 25, 45, 60];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final dpr = View.of(context).devicePixelRatio;
      _win.attach(
        widthPx: (380 * dpr).round(),
        heightPx: (500 * dpr).round(),
        title: '倒计时',
      );
    });
  }

  // ---------- 计时逻辑（基于真实时间，不受卡顿/休眠影响） ----------

  Duration get _display {
    switch (_phase) {
      case _Phase.idle:
        return Duration(seconds: _pickHours * 3600 + _pickMinutes * 60);
      case _Phase.running:
        final left = _endAt!.difference(DateTime.now());
        return left.isNegative ? Duration.zero : left;
      case _Phase.paused:
        return _remainingAtPause;
      case _Phase.overtime:
        return DateTime.now().difference(_endAt!);
    }
  }

  void _startTicker() {
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(milliseconds: 250), (_) {
      if (!mounted) return;
      if (_phase == _Phase.running) {
        final now = DateTime.now();
        if (!now.isBefore(_endAt!)) {
          setState(() => _phase = _Phase.overtime);
          _playAlarm();
          return;
        }
      }
      setState(() {});
    });
  }

  void _startWith(Duration d) {
    if (d.inSeconds <= 0) {
      setState(() => _audioWarning = '请先选择时长');
      return;
    }
    setState(() {
      _totalSeconds = d.inSeconds;
      _endAt = DateTime.now().add(d);
      _phase = _Phase.running;
      _alarmPlayed = false;
      _audioWarning = null;
    });
    _startTicker();
  }

  void _pause() {
    _tick?.cancel();
    final left = _endAt!.difference(DateTime.now());
    setState(() {
      _remainingAtPause = left.isNegative ? Duration.zero : left;
      _phase = _Phase.paused;
    });
  }

  void _resume() {
    setState(() {
      _endAt = DateTime.now().add(_remainingAtPause);
      _phase = _Phase.running;
    });
    _startTicker();
  }

  void _reset() {
    _tick?.cancel();
    setState(() {
      _phase = _Phase.idle;
      _endAt = null;
      _totalSeconds = 0;
      _alarmPlayed = false;
      _audioWarning = null;
    });
  }

  Future<void> _playAlarm() async {
    if (_alarmPlayed) return;
    _alarmPlayed = true;
    try {
      await _player.stop();
      await _player.play(AssetSource('audio/alarm.wav'));
    } catch (e, s) {
      AppLog.error('倒计时结束铃声播放失败', e, s);
      if (mounted) setState(() => _audioWarning = '铃声播放失败，请检查系统音量');
    }
  }

  // ---------- 显示 ----------

  static String _format(Duration d) => formatDuration(d);

  Color _timeColor(ColorScheme scheme) {
    if (_phase == _Phase.overtime) return scheme.error;
    if (_phase == _Phase.running &&
        _totalSeconds > 0 &&
        _display.inSeconds <= (_totalSeconds / 5).ceil()) {
      return scheme.error;
    }
    return scheme.onSurface;
  }

  @override
  void dispose() {
    _tick?.cancel();
    _player.dispose();
    _focus.dispose();
    _win.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: KeyboardListener(
        focusNode: _focus,
        autofocus: true,
        onKeyEvent: _onKey,
        child: Column(
          children: <Widget>[
            _WindowBar(
              title: '倒计时',
              isTopMost: _win.isTopMost,
              isFullscreen: _fullscreen,
              onToggleTopMost: () => setState(() => _win.toggleTopMost()),
              onToggleFullscreen: () => setState(() => _fullscreen = _win.toggleFullscreen()),
              onMinimize: _win.minimize,
              onClose: _win.close,
              dragStart: _win.beginDrag,
              dragUpdate: _win.updateDrag,
            ),
            Expanded(
              child: Center(
                child: _phase == _Phase.idle
                    ? _buildPicker(scheme)
                    : _buildDisplay(scheme),
              ),
            ),
            if (_audioWarning != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(_audioWarning!,
                    style: TextStyle(fontSize: 14, color: scheme.error)),
              ),
            _buildActions(scheme),
          ],
        ),
      ),
    );
  }

  void _onKey(KeyEvent e) {
    if (e is! KeyDownEvent) return;
    final k = e.logicalKey;
    if (k == LogicalKeyboardKey.escape && _fullscreen) {
      setState(() => _fullscreen = _win.toggleFullscreen());
    } else if (k == LogicalKeyboardKey.space) {
      if (_phase == _Phase.running) {
        _pause();
      } else if (_phase == _Phase.paused) {
        _resume();
      } else if (_phase == _Phase.idle) {
        _startWith(Duration(seconds: _pickHours * 3600 + _pickMinutes * 60));
      }
    } else if (k == LogicalKeyboardKey.keyR) {
      _reset();
    }
  }

  // ---------- 选择时长 ----------

  Widget _buildPicker(ColorScheme scheme) {
    final picked = Duration(seconds: _pickHours * 3600 + _pickMinutes * 60);
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(_format(picked),
              style: TextStyle(
                  fontSize: 46,
                  fontWeight: FontWeight.w700,
                  color: scheme.primary,
                  fontFeatures: const <FontFeature>[FontFeature.tabularFigures()])),
          const SizedBox(height: 6),
          Text('点一下下面的时长立即开始，或自己拨轮子',
              style: TextStyle(fontSize: 14, color: scheme.onSurfaceVariant)),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            alignment: WrapAlignment.center,
            children: _presetMinutes
                .map((m) => SizedBox(
                      width: 104,
                      height: 52,
                      child: FilledButton.tonal(
                        onPressed: () => _startWith(Duration(minutes: m)),
                        child: Text(m == 60 ? '1 小时' : '$m 分钟',
                            style: const TextStyle(
                                fontSize: 17, fontWeight: FontWeight.w600)),
                      ),
                    ))
                .toList(),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              _Wheel(
                  label: '小时',
                  max: 13,
                  initial: _pickHours,
                  onChanged: (v) => setState(() => _pickHours = v)),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 4),
                child: Text(':', style: TextStyle(fontSize: 34)),
              ),
              _Wheel(
                  label: '分钟',
                  max: 60,
                  initial: _pickMinutes,
                  onChanged: (v) => setState(() => _pickMinutes = v)),
            ],
          ),
        ],
      ),
    );
  }

  // ---------- 运行显示 ----------

  Widget _buildDisplay(ColorScheme scheme) {
    final label = switch (_phase) {
      _Phase.running => '倒计时中',
      _Phase.paused => '已暂停',
      _Phase.overtime => '已超时 · 正计时',
      _Phase.idle => '',
    };
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              _format(_display),
              style: TextStyle(
                fontSize: 104,
                fontWeight: FontWeight.w800,
                color: _timeColor(scheme),
                fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
              ),
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(label,
            style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: _phase == _Phase.overtime
                    ? scheme.error
                    : scheme.onSurfaceVariant)),
      ],
    );
  }

  Widget _buildActions(ColorScheme scheme) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18, top: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          if (_phase == _Phase.idle)
            FilledButton.icon(
              onPressed: () => _startWith(
                  Duration(seconds: _pickHours * 3600 + _pickMinutes * 60)),
              icon: const Icon(Icons.play_arrow, size: 26),
              label: const Text('开始'),
              style: FilledButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 30, vertical: 16),
                  textStyle: const TextStyle(
                      fontSize: 19, fontWeight: FontWeight.w600)),
            )
          else ...<Widget>[
            if (_phase == _Phase.running)
              FilledButton.icon(
                onPressed: _pause,
                icon: const Icon(Icons.pause, size: 26),
                label: const Text('暂停'),
                style: FilledButton.styleFrom(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 26, vertical: 16),
                    textStyle: const TextStyle(
                        fontSize: 19, fontWeight: FontWeight.w600)),
              )
            else if (_phase == _Phase.paused)
              FilledButton.icon(
                onPressed: _resume,
                icon: const Icon(Icons.play_arrow, size: 26),
                label: const Text('继续'),
                style: FilledButton.styleFrom(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 26, vertical: 16),
                    textStyle: const TextStyle(
                        fontSize: 19, fontWeight: FontWeight.w600)),
              )
            else
              const SizedBox.shrink(),
            const SizedBox(width: 12),
            OutlinedButton.icon(
              onPressed: _reset,
              icon: const Icon(Icons.refresh, size: 22),
              label: const Text('重置'),
              style: OutlinedButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  textStyle: const TextStyle(fontSize: 17)),
            ),
          ],
        ],
      ),
    );
  }
}

// ============================================================================
// 秒表
// ============================================================================

class StopwatchPage extends StatefulWidget {
  const StopwatchPage({super.key});

  @override
  State<StopwatchPage> createState() => _StopwatchPageState();
}

class _StopwatchPageState extends State<StopwatchPage> {
  final SubWindow _win = SubWindow('stopwatch');
  final Stopwatch _sw = Stopwatch();
  final FocusNode _focus = FocusNode();

  Timer? _tick;
  int _elapsedMs = 0;
  int _lastLapMs = 0;
  final List<int> _laps = <int>[];
  bool _fullscreen = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final dpr = View.of(context).devicePixelRatio;
      _win.attach(
        widthPx: (400 * dpr).round(),
        heightPx: (580 * dpr).round(),
        title: '秒表',
      );
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    _focus.dispose();
    _win.dispose();
    super.dispose();
  }

  void _refresh() {
    if (mounted) setState(() => _elapsedMs = _sw.elapsedMilliseconds);
  }

  void _start() {
    _sw.start();
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(milliseconds: 50), (_) => _refresh());
    _refresh();
  }

  void _pause() {
    _sw.stop();
    _tick?.cancel();
    _refresh();
  }

  void _lap() {
    setState(() {
      _laps.insert(0, _elapsedMs - _lastLapMs);
      _lastLapMs = _elapsedMs;
    });
  }

  Future<void> _reset() async {
    if (_elapsedMs > 0) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('重置秒表？'),
          content: Text('当前记录 ${_laps.length} 次记次，重置后全部清空。'),
          actions: <Widget>[
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('取消')),
            FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('重置')),
          ],
        ),
      );
      if (ok != true) return;
    }
    _sw.stop();
    _sw.reset();
    _tick?.cancel();
    setState(() {
      _elapsedMs = 0;
      _lastLapMs = 0;
      _laps.clear();
    });
  }

  static String _fmt(int ms) => formatStopwatch(ms);

  void _onKey(KeyEvent e) {
    if (e is! KeyDownEvent) return;
    final k = e.logicalKey;
    if (k == LogicalKeyboardKey.escape && _fullscreen) {
      setState(() => _fullscreen = _win.toggleFullscreen());
    } else if (k == LogicalKeyboardKey.space) {
      _sw.isRunning ? _pause() : _start();
    } else if (k == LogicalKeyboardKey.keyL && _sw.isRunning) {
      _lap();
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: KeyboardListener(
        focusNode: _focus,
        autofocus: true,
        onKeyEvent: _onKey,
        child: Column(
          children: <Widget>[
            _WindowBar(
              title: '秒表',
              isTopMost: _win.isTopMost,
              isFullscreen: _fullscreen,
              onToggleTopMost: () => setState(() => _win.toggleTopMost()),
              onToggleFullscreen: () =>
                  setState(() => _fullscreen = _win.toggleFullscreen()),
              onMinimize: _win.minimize,
              onClose: _win.close,
              dragStart: _win.beginDrag,
              dragUpdate: _win.updateDrag,
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 14),
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  _fmt(_elapsedMs),
                  style: TextStyle(
                    fontSize: 76,
                    fontWeight: FontWeight.w800,
                    color: scheme.onSurface,
                    fontFeatures: const <FontFeature>[
                      FontFeature.tabularFigures()
                    ],
                  ),
                ),
              ),
            ),
            Expanded(
              child: _laps.isEmpty
                  ? Center(
                      child: Text('还没有记次（运行时按「记次」或 L 键）',
                          style: TextStyle(
                              fontSize: 15, color: scheme.onSurfaceVariant)))
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      itemCount: _laps.length,
                      itemBuilder: (ctx, i) {
                        final lapNo = _laps.length - i;
                        final isLatest = i == 0;
                        return Container(
                          margin: const EdgeInsets.symmetric(vertical: 3),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            color: isLatest
                                ? scheme.primaryContainer
                                : scheme.surfaceContainerHighest
                                    .withValues(alpha: 0.4),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: <Widget>[
                              Text('第 $lapNo 次',
                                  style: const TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600)),
                              Text(_fmt(_laps[i]),
                                  style: const TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w600,
                                      fontFeatures: <FontFeature>[
                                        FontFeature.tabularFigures()
                                      ])),
                            ],
                          ),
                        );
                      },
                    ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 18, top: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  if (!_sw.isRunning)
                    FilledButton.icon(
                      onPressed: _start,
                      icon: const Icon(Icons.play_arrow, size: 26),
                      label: const Text('开始'),
                      style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 28, vertical: 16),
                          textStyle: const TextStyle(
                              fontSize: 19, fontWeight: FontWeight.w600)),
                    )
                  else
                    FilledButton.icon(
                      onPressed: _pause,
                      icon: const Icon(Icons.pause, size: 26),
                      label: const Text('暂停'),
                      style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 24, vertical: 16),
                          textStyle: const TextStyle(
                              fontSize: 19, fontWeight: FontWeight.w600)),
                    ),
                  const SizedBox(width: 10),
                  OutlinedButton.icon(
                    onPressed: _sw.isRunning ? _lap : null,
                    icon: const Icon(Icons.flag, size: 22),
                    label: const Text('记次'),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 18, vertical: 16),
                        textStyle: const TextStyle(fontSize: 17)),
                  ),
                  const SizedBox(width: 10),
                  OutlinedButton.icon(
                    onPressed: _reset,
                    icon: const Icon(Icons.refresh, size: 22),
                    label: const Text('重置'),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 18, vertical: 16),
                        textStyle: const TextStyle(fontSize: 17)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// 共用：自定义标题栏 + 滚轮
// ============================================================================

class _WindowBar extends StatelessWidget {
  const _WindowBar({
    required this.title,
    required this.isTopMost,
    required this.isFullscreen,
    required this.onToggleTopMost,
    required this.onToggleFullscreen,
    required this.onMinimize,
    required this.onClose,
    required this.dragStart,
    required this.dragUpdate,
  });

  final String title;
  final bool isTopMost;
  final bool isFullscreen;
  final VoidCallback onToggleTopMost;
  final VoidCallback onToggleFullscreen;
  final VoidCallback onMinimize;
  final VoidCallback onClose;
  final VoidCallback dragStart;
  final void Function(double dx, double dy) dragUpdate;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 44,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        border: Border(
            bottom: BorderSide(color: scheme.outlineVariant, width: 1)),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onPanStart: (_) => dragStart(),
              onPanUpdate: (d) => dragUpdate(d.delta.dx, d.delta.dy),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(title,
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w600)),
                ),
              ),
            ),
          ),
          _BarButton(
            icon: isTopMost ? Icons.push_pin : Icons.push_pin_outlined,
            tooltip: isTopMost ? '取消置顶' : '置顶显示',
            active: isTopMost,
            onTap: onToggleTopMost,
          ),
          _BarButton(
            icon: isFullscreen ? Icons.fullscreen_exit : Icons.fullscreen,
            tooltip: isFullscreen ? '退出全屏（Esc）' : '全屏',
            active: isFullscreen,
            onTap: onToggleFullscreen,
          ),
          _BarButton(
            icon: Icons.remove,
            tooltip: '最小化',
            onTap: onMinimize,
          ),
          _BarButton(
            icon: Icons.close,
            tooltip: '关闭',
            danger: true,
            onTap: onClose,
          ),
        ],
      ),
    );
  }
}

class _BarButton extends StatelessWidget {
  const _BarButton({
    required this.icon,
    required this.tooltip,
    required this.onTap,
    this.active = false,
    this.danger = false,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  final bool active;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      waitDuration: const Duration(milliseconds: 500),
      child: InkWell(
        onTap: onTap,
        hoverColor: danger ? scheme.error.withValues(alpha: 0.85) : null,
        child: SizedBox(
          width: 46,
          height: 44,
          child: Icon(icon,
              size: 20,
              color: active ? scheme.primary : scheme.onSurfaceVariant),
        ),
      ),
    );
  }
}

class _Wheel extends StatelessWidget {
  const _Wheel({
    required this.label,
    required this.max,
    required this.initial,
    required this.onChanged,
  });

  final String label;
  final int max;
  final int initial;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(label, style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
        const SizedBox(height: 4),
        Container(
          width: 88,
          height: 132,
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(12),
          ),
          child: _WheelList(
              max: max, initial: initial, onChanged: onChanged, scheme: scheme),
        ),
      ],
    );
  }
}

class _WheelList extends StatefulWidget {
  const _WheelList({
    required this.max,
    required this.initial,
    required this.onChanged,
    required this.scheme,
  });

  final int max;
  final int initial;
  final ValueChanged<int> onChanged;
  final ColorScheme scheme;

  @override
  State<_WheelList> createState() => _WheelListState();
}

class _WheelListState extends State<_WheelList> {
  late final FixedExtentScrollController _controller =
      FixedExtentScrollController(initialItem: widget.initial);
  late int _index = widget.initial;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListWheelScrollView.useDelegate(
      controller: _controller,
      itemExtent: 40,
      physics: const FixedExtentScrollPhysics(),
      onSelectedItemChanged: (i) {
        setState(() => _index = i);
        widget.onChanged(i);
      },
      childDelegate: ListWheelChildBuilderDelegate(
        childCount: widget.max,
        builder: (ctx, i) => Center(
          child: Text(
            i.toString().padLeft(2, '0'),
            style: TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.w600,
              // 用 state 里的下标：controller.selectedItem 在首次 build（还没 attach）时不可用
              color: i == _index
                  ? widget.scheme.primary
                  : widget.scheme.onSurfaceVariant,
            ),
          ),
        ),
      ),
    );
  }
}
