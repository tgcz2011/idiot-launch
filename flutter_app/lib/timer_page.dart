import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_log.dart';
import 'format.dart';
import 'fullscreen_guard.dart';
import 'sub_window.dart';
import 'widgets/duration_picker.dart';

/// 倒计时 / 秒表（独立子窗口）。
///
/// 窗口由 desktop_multi_window 创建，样式与位置交给 [SubWindow]（非阻塞 FFI）。
/// [hwnd] 由父窗口通过窗口通道传下来，避免两个子窗口互相抢错窗口。
///
/// 设计目标：老师站在讲台/大屏幕前，一两次点击就能用 ——
/// 预设大按钮 + 时/分滚轮（可以拖，也可以滚鼠标滚轮）。
class TimerPage extends StatefulWidget {
  const TimerPage({super.key, this.hwnd = 0, this.nativeShow});

  final int hwnd;
  final Future<void> Function()? nativeShow;

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
  int _pickSeconds = 0;
  int _totalSeconds = 0;
  DateTime? _endAt;
  Duration _remainingAtPause = Duration.zero;
  Timer? _tick;
  bool _alarmPlayed = false;
  bool _fullscreen = false;
  String? _audioWarning;

  // 滚轮控制器由**页面**持有。放进滚轮组件内部的话，页面一重建控制器就被重建，
  // 拖动立刻被弹回原来的位置 —— 用户实测"倒计时时间改不了（拖动）"就是这个。
  late final FixedExtentScrollController _hourCtrl =
      FixedExtentScrollController(initialItem: 0);
  late final FixedExtentScrollController _minCtrl = FixedExtentScrollController(
    initialItem: 5,
  );
  late final FixedExtentScrollController _secCtrl = FixedExtentScrollController(
    initialItem: 0,
  );

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final dpr = View.of(context).devicePixelRatio;
      _win.attach(
        widthPx: (380 * dpr).round(),
        heightPx: (530 * dpr).round(),
        title: '倒计时',
        hwnd: widget.hwnd,
        scale: dpr,
        nativeShow: widget.nativeShow,
      );
    });
  }

  /// 把滚轮拨到指定位置（点预设时用，否则轮子会和显示的数字不一致）。
  void _syncWheels(int hours, int minutes, [int seconds = 0]) {
    if (_hourCtrl.hasClients) _hourCtrl.jumpToItem(hours.clamp(0, 12));
    if (_minCtrl.hasClients) _minCtrl.jumpToItem(minutes.clamp(0, 59));
    if (_secCtrl.hasClients) _secCtrl.jumpToItem(seconds.clamp(0, 59));
  }

  void _applyPreset(int minutes) {
    final h = minutes ~/ 60;
    final m = minutes % 60;
    setState(() {
      _pickHours = h;
      _pickMinutes = m;
      _pickSeconds = 0;
    });
    _syncWheels(h, m, 0);
    _startWith(Duration(minutes: minutes));
  }

  // ---------- 计时逻辑（基于真实时间，不受卡顿/休眠影响） ----------

  Duration get _picked =>
      Duration(seconds: _pickHours * 3600 + _pickMinutes * 60 + _pickSeconds);

  Duration get _display {
    switch (_phase) {
      case _Phase.idle:
        return _picked;
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
      setState(() => _audioWarning = '请先选择时长（不能是 0 分钟）');
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
    _hourCtrl.dispose();
    _minCtrl.dispose();
    _secCtrl.dispose();
    ToolFullscreenGuard.release();
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
        child: _fullscreen ? _buildFullscreen(scheme) : _buildNormal(scheme),
      ),
    );
  }

  Widget _buildNormal(ColorScheme scheme) {
    return Column(
      children: <Widget>[
        _WindowBar(
          title: '倒计时',
          isTopMost: _win.isTopMost,
          isFullscreen: _fullscreen,
          onToggleTopMost: () => setState(() => _win.toggleTopMost()),
          onToggleFullscreen: _toggleFullscreen,
          onMinimize: _win.minimize,
          onClose: _win.close,
          dragStart: _win.beginDrag,
          dragUpdate: _win.updateDrag,
          onDragEnd: _win.endDrag,
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
            child: Text(
              _audioWarning!,
              style: TextStyle(fontSize: 14, color: scheme.error),
            ),
          ),
        _buildActions(scheme),
      ],
    );
  }

  /// 完全全屏：只剩"时间 + 操作 + 退出全屏"（Esc 也能退），字随窗口放大铺满。
  Widget _buildFullscreen(ColorScheme scheme) {
    return Stack(
      children: <Widget>[
        Positioned.fill(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(36, 56, 36, 108),
            child: Center(
              child: _phase == _Phase.idle
                  ? _buildPicker(scheme)
                  : FittedBox(
                      fit: BoxFit.contain,
                      child: Text(
                        formatDuration(_display),
                        style: TextStyle(
                          fontSize: 520,
                          fontWeight: FontWeight.w800,
                          color: _timeColor(scheme),
                          fontFeatures: const <FontFeature>[
                            FontFeature.tabularFigures(),
                          ],
                        ),
                      ),
                    ),
            ),
          ),
        ),
        Positioned(top: 16, right: 16, child: _exitFullscreenButton()),
        if (_audioWarning != null)
          Positioned(
            bottom: 96,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                _audioWarning!,
                style: TextStyle(fontSize: 16, color: scheme.error),
              ),
            ),
          ),
        Positioned(bottom: 24, left: 0, right: 0, child: _buildActions(scheme)),
      ],
    );
  }

  Widget _exitFullscreenButton() {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: '退出全屏（Esc）',
      child: Material(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.8),
        shape: const CircleBorder(),
        child: IconButton(
          icon: const Icon(Icons.fullscreen_exit),
          iconSize: 28,
          onPressed: _exitFullscreen,
        ),
      ),
    );
  }

  void _toggleFullscreen() {
    final fs = _win.toggleFullscreen();
    setState(() => _fullscreen = fs);
    if (fs) {
      ToolFullscreenGuard.acquire();
    } else {
      ToolFullscreenGuard.release();
    }
  }

  void _exitFullscreen() {
    if (!_fullscreen) return;
    setState(() => _fullscreen = _win.toggleFullscreen());
    ToolFullscreenGuard.release();
  }

  void _onKey(KeyEvent e) {
    if (e is! KeyDownEvent) return;
    final k = e.logicalKey;
    if (k == LogicalKeyboardKey.escape && _fullscreen) {
      _exitFullscreen();
    } else if (k == LogicalKeyboardKey.space) {
      if (_phase == _Phase.running) {
        _pause();
      } else if (_phase == _Phase.paused) {
        _resume();
      } else if (_phase == _Phase.idle) {
        _startWith(_picked);
      }
    } else if (k == LogicalKeyboardKey.keyR) {
      _reset();
    }
  }

  // ---------- 选择时长（预设 + 滚轮） ----------
  //
  // 滚轮拖动交给 DurationPicker：控制器由本 State 持有（拖了才不会被弹回去）。

  Widget _buildPicker(ColorScheme scheme) {
    return DurationPicker(
      hourController: _hourCtrl,
      minuteController: _minCtrl,
      hours: _pickHours,
      minutes: _pickMinutes,
      onHoursChanged: (i) => setState(() => _pickHours = i),
      onMinutesChanged: (i) => setState(() => _pickMinutes = i),
      onPreset: _applyPreset,
      showSeconds: true,
      secondController: _secCtrl,
      seconds: _pickSeconds,
      onSecondsChanged: (i) => setState(() => _pickSeconds = i),
    );
  }

  // ---------- 运行显示 ----------

  Widget _buildDisplay(ColorScheme scheme) {
    final label = switch (_phase) {
      _Phase.paused => '已暂停',
      _Phase.overtime => '已超时',
      _ => '',
    };
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              formatDuration(_display),
              style: TextStyle(
                fontSize: 104,
                fontWeight: FontWeight.w800,
                color: _timeColor(scheme),
                fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
              ),
            ),
          ),
        ),
        if (label.isNotEmpty) ...<Widget>[
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: _phase == _Phase.overtime
                  ? scheme.error
                  : scheme.onSurfaceVariant,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildActions(ColorScheme scheme) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16, top: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          if (_phase == _Phase.idle)
            FilledButton.icon(
              onPressed: () => _startWith(_picked),
              icon: const Icon(Icons.play_arrow, size: 26),
              label: const Text('开始'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                  horizontal: 30,
                  vertical: 16,
                ),
                textStyle: const TextStyle(
                  fontSize: 19,
                  fontWeight: FontWeight.w600,
                ),
              ),
            )
          else ...<Widget>[
            if (_phase == _Phase.running)
              FilledButton.icon(
                onPressed: _pause,
                icon: const Icon(Icons.pause, size: 26),
                label: const Text('暂停'),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 26,
                    vertical: 16,
                  ),
                  textStyle: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              )
            else if (_phase == _Phase.paused)
              FilledButton.icon(
                onPressed: _resume,
                icon: const Icon(Icons.play_arrow, size: 26),
                label: const Text('继续'),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 26,
                    vertical: 16,
                  ),
                  textStyle: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              )
            else
              const SizedBox.shrink(),
            const SizedBox(width: 12),
            OutlinedButton.icon(
              onPressed: _reset,
              icon: const Icon(Icons.refresh, size: 22),
              label: const Text('重置'),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 16,
                ),
                textStyle: const TextStyle(fontSize: 17),
              ),
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
  const StopwatchPage({super.key, this.hwnd = 0, this.nativeShow});

  final int hwnd;
  final Future<void> Function()? nativeShow;

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
        widthPx: (700 * dpr).round(),
        heightPx: (260 * dpr).round(),
        title: '秒表',
        hwnd: widget.hwnd,
        scale: dpr,
        nativeShow: widget.nativeShow,
      );
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    _focus.dispose();
    ToolFullscreenGuard.release();
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
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('重置'),
            ),
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

  void _onKey(KeyEvent e) {
    if (e is! KeyDownEvent) return;
    final k = e.logicalKey;
    if (k == LogicalKeyboardKey.escape && _fullscreen) {
      _exitFullscreen();
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
        child: _fullscreen ? _buildFullscreen(scheme) : _buildNormal(scheme),
      ),
    );
  }

  Widget _buildNormal(ColorScheme scheme) {
    return Column(
      children: <Widget>[
        _WindowBar(
          title: '秒表',
          isTopMost: _win.isTopMost,
          isFullscreen: _fullscreen,
          onToggleTopMost: () => setState(() => _win.toggleTopMost()),
          onToggleFullscreen: _toggleFullscreen,
          onMinimize: _win.minimize,
          onClose: _win.close,
          dragStart: _win.beginDrag,
          dragUpdate: _win.updateDrag,
          onDragEnd: _win.endDrag,
        ),
        // 紧凑横向布局（希沃白板那种横着的长方形）：左边大号毫秒时间，
        // 右边一排操作，底部一条可横向滚动的记次。高度都写死，避免被压没。
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 8, 18, 0),
          child: SizedBox(
            height: 84,
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: Text(
                        formatStopwatch(_elapsedMs),
                        style: TextStyle(
                          fontSize: 64,
                          fontWeight: FontWeight.w800,
                          color: scheme.onSurface,
                          fontFeatures: const <FontFeature>[
                            FontFeature.tabularFigures(),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                if (!_sw.isRunning)
                  FilledButton.icon(
                    onPressed: _start,
                    icon: const Icon(Icons.play_arrow, size: 22),
                    label: const Text('开始'),
                  )
                else
                  FilledButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause, size: 22),
                    label: const Text('暂停'),
                  ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: _sw.isRunning ? _lap : null,
                  icon: const Icon(Icons.flag),
                  tooltip: '记次',
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh),
                  tooltip: '重置',
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 6),
        SizedBox(height: 66, child: _lapsRow(scheme)),
      ],
    );
  }

  /// 完全全屏：大号时间铺满 + 操作 + 退出全屏键（Esc 也能退）。
  Widget _buildFullscreen(ColorScheme scheme) {
    return Stack(
      children: <Widget>[
        Positioned.fill(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(36, 48, 36, 160),
            child: Center(
              child: FittedBox(
                fit: BoxFit.contain,
                child: Text(
                  formatStopwatch(_elapsedMs),
                  style: TextStyle(
                    fontSize: 520,
                    fontWeight: FontWeight.w800,
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
        if (_laps.isNotEmpty)
          Positioned(
            left: 0,
            right: 0,
            bottom: 100,
            child: SizedBox(height: 66, child: _lapsRow(scheme)),
          ),
        Positioned(
          bottom: 24,
          left: 0,
          right: 0,
          child: Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (!_sw.isRunning)
                  FilledButton.icon(
                    onPressed: _start,
                    icon: const Icon(Icons.play_arrow, size: 24),
                    label: const Text('开始'),
                  )
                else
                  FilledButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause, size: 24),
                    label: const Text('暂停'),
                  ),
                const SizedBox(width: 10),
                IconButton.filledTonal(
                  onPressed: _sw.isRunning ? _lap : null,
                  icon: const Icon(Icons.flag, size: 24),
                  tooltip: '记次',
                ),
                const SizedBox(width: 10),
                IconButton.filledTonal(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh, size: 24),
                  tooltip: '重置',
                ),
              ],
            ),
          ),
        ),
        Positioned(top: 16, right: 16, child: _exitFullscreenButton()),
      ],
    );
  }

  Widget _exitFullscreenButton() {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: '退出全屏（Esc）',
      child: Material(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.8),
        shape: const CircleBorder(),
        child: IconButton(
          icon: const Icon(Icons.fullscreen_exit),
          iconSize: 28,
          onPressed: _exitFullscreen,
        ),
      ),
    );
  }

  void _toggleFullscreen() {
    final fs = _win.toggleFullscreen();
    setState(() => _fullscreen = fs);
    if (fs) {
      ToolFullscreenGuard.acquire();
    } else {
      ToolFullscreenGuard.release();
    }
  }

  void _exitFullscreen() {
    if (!_fullscreen) return;
    setState(() => _fullscreen = _win.toggleFullscreen());
    ToolFullscreenGuard.release();
  }

  Widget _lapsRow(ColorScheme scheme) {
    if (_laps.isEmpty) return const SizedBox.shrink();
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: <Widget>[
          for (int i = 0; i < _laps.length; i++)
            _lapChip(scheme, _laps.length - i, _laps[i], i == 0),
        ],
      ),
    );
  }

  /// 单条记次（横向排布的小胶囊，越新的越靠左并高亮）。
  Widget _lapChip(ColorScheme scheme, int no, int ms, bool latest) {
    return Container(
      margin: const EdgeInsets.only(right: 8, top: 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: latest
            ? scheme.primaryContainer
            : scheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: <Widget>[
          Text(
            '$no',
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
          const SizedBox(width: 8),
          Text(
            formatStopwatch(ms),
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================================
// 共用：标题栏 + 步进按钮
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
    required this.onDragEnd,
  });

  final String title;
  final bool isTopMost;
  final bool isFullscreen;
  final VoidCallback onToggleTopMost;
  final VoidCallback onToggleFullscreen;
  final VoidCallback onMinimize;
  final VoidCallback onClose;

  /// 拖动窗口：参数是 Flutter 的逻辑坐标（**不是 delta**）和输入设备类型。
  /// 鼠标交给系统移动循环（跟手、任何 DPI 都对），触摸走逐帧拖动。
  final void Function(double x, double y, PointerDeviceKind kind) dragStart;
  final void Function(double x, double y) dragUpdate;
  final VoidCallback onDragEnd;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 44,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        border: Border(
          bottom: BorderSide(color: scheme.outlineVariant, width: 1),
        ),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onPanStart: (d) => dragStart(
                d.globalPosition.dx,
                d.globalPosition.dy,
                d.kind ?? PointerDeviceKind.mouse,
              ),
              onPanUpdate: (d) =>
                  dragUpdate(d.globalPosition.dx, d.globalPosition.dy),
              onPanEnd: (_) => onDragEnd(),
              // 手势被抢走/取消也要收尾：鼠标捕获必须还回去，
              // 否则整个桌面的鼠标消息都会被投到本窗口
              onPanCancel: onDragEnd,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Row(
                    children: <Widget>[
                      Icon(
                        Icons.drag_indicator,
                        size: 18,
                        color: scheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        title,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
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
          _BarButton(icon: Icons.remove, tooltip: '最小化', onTap: onMinimize),
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

class _BarButton extends StatefulWidget {
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
  State<_BarButton> createState() => _BarButtonState();
}

class _BarButtonState extends State<_BarButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // 危险按钮（关窗）平时用深灰（浅色模式下看得见），
    // 悬停变红底时才换成 onError（浅色模式下是白色）。
    final Color color = widget.danger && _hover
        ? scheme.onError
        : (widget.active ? scheme.primary : scheme.onSurfaceVariant);
    return Tooltip(
      message: widget.tooltip,
      waitDuration: const Duration(milliseconds: 500),
      child: MouseRegion(
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        child: InkWell(
          onTap: widget.onTap,
          hoverColor: widget.danger
              ? scheme.error.withValues(alpha: 0.9)
              : null,
          child: SizedBox(
            width: 46,
            height: 44,
            child: Icon(widget.icon, size: 20, color: color),
          ),
        ),
      ),
    );
  }
}
