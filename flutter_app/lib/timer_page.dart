import 'dart:async';
import 'dart:ffi' as ffi;
import 'dart:io';
import 'package:ffi/ffi.dart';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:window_manager/window_manager.dart';
import 'package:audioplayers/audioplayers.dart';

// ==================== FFI: 子窗口无边框控制 ====================
// window_manager 在 desktop_multi_window 子窗口中控制的是主窗口，
// 所以用 FFI 直接调用 user32.dll 控制当前活动窗口（子窗口）。
final _user32 = ffi.DynamicLibrary.open('user32.dll');

typedef _GetForegroundWindowNative = ffi.IntPtr Function();
typedef _GetForegroundWindowDart = int Function();
final _getForegroundWindow = _user32.lookupFunction<_GetForegroundWindowNative, _GetForegroundWindowDart>('GetForegroundWindow');

typedef _GetWindowLongNative = ffi.IntPtr Function(ffi.IntPtr hWnd, ffi.Int32 nIndex);
typedef _GetWindowLongDart = int Function(int hWnd, int nIndex);
final _getWindowLong = _user32.lookupFunction<_GetWindowLongNative, _GetWindowLongDart>('GetWindowLongW');

typedef _SetWindowLongNative = ffi.IntPtr Function(ffi.IntPtr hWnd, ffi.Int32 nIndex, ffi.IntPtr dwNewLong);
typedef _SetWindowLongDart = int Function(int hWnd, int nIndex, int dwNewLong);
final _setWindowLong = _user32.lookupFunction<_SetWindowLongNative, _SetWindowLongDart>('SetWindowLongW');

typedef _SetWindowPosNative = ffi.Int32 Function(
    ffi.IntPtr hWnd, ffi.IntPtr hWndInsertAfter,
    ffi.Int32 X, ffi.Int32 Y, ffi.Int32 cx, ffi.Int32 cy, ffi.Uint32 uFlags);
typedef _SetWindowPosDart = int Function(
    int hWnd, int hWndInsertAfter, int X, int Y, int cx, int cy, int uFlags);
final _setWindowPos = _user32.lookupFunction<_SetWindowPosNative, _SetWindowPosDart>('SetWindowPos');

const int _gwlStyle = -16;
const int _wsCaption = 0x00C00000;
const int _wsThickFrame = 0x00040000;
const int _wsSysMenu = 0x00080000;
const int _wsMinimizeBox = 0x00020000;
const int _wsMaximizeBox = 0x00010000;
const int _swpFrameChanged = 0x0020;
const int _swpNoZOrder = 0x0004;
const int _swpNoMove = 0x0002;
const int _swpNoSize = 0x0001;
const int _hwndTopmost = -1;
const int _hwndNotopmost = -2;
const int _smCxScreen = 0;
const int _smCyScreen = 1;

// 无边框窗口拖动：ReleaseCapture + SendMessage(WM_NCLBUTTONDOWN, HTCAPTION)
typedef _ReleaseCaptureNative = ffi.Int32 Function();
typedef _ReleaseCaptureDart = int Function();
final _releaseCapture = _user32.lookupFunction<_ReleaseCaptureNative, _ReleaseCaptureDart>('ReleaseCapture');

typedef _SendMessageNative = ffi.IntPtr Function(
    ffi.IntPtr hWnd, ffi.Uint32 Msg, ffi.IntPtr wParam, ffi.IntPtr lParam);
typedef _SendMessageDart = int Function(
    int hWnd, int Msg, int wParam, int lParam);
final _sendMessage = _user32.lookupFunction<_SendMessageNative, _SendMessageDart>('SendMessageW');

const int _wmNcLButtonDown = 0x00A1;
const int _htCaption = 2;

typedef _GetSystemMetricsNative = ffi.Int32 Function(ffi.Int32 nIndex);
typedef _GetSystemMetricsDart = int Function(int nIndex);
final _getSystemMetrics = _user32.lookupFunction<_GetSystemMetricsNative, _GetSystemMetricsDart>('GetSystemMetrics');

// 当前子窗口句柄缓存
int _cachedHWnd = 0;
bool _isTopMost = false;

/// 通过进程ID查找属于当前进程的可见顶层窗口。
/// 优先用 GetForegroundWindow（子窗口创建后应为前台窗口），验证进程ID后使用。
int _findOurWindow() {
  if (_cachedHWnd != 0) return _cachedHWnd;
  try {
    final currentPid = pid;
    final getWindowThreadProcessId = _user32.lookupFunction<
        ffi.Uint32 Function(ffi.IntPtr hWnd, ffi.Pointer<ffi.Uint32> lpdwProcessId),
        int Function(int hWnd, ffi.Pointer<ffi.Uint32>)>('GetWindowThreadProcessId');
    final isWindowVisible = _user32.lookupFunction<
        ffi.Int32 Function(ffi.IntPtr hWnd),
        int Function(int hWnd)>('IsWindowVisible');
    final getWindow = _user32.lookupFunction<
        ffi.IntPtr Function(ffi.IntPtr hWnd, ffi.Uint32 uCmd),
        int Function(int hWnd, int uCmd)>('GetWindow');

    final pidPtr = calloc<ffi.Uint32>();

    // 1. 优先用前台窗口（子窗口刚创建时是前台窗口）
    int fg = _getForegroundWindow();
    if (fg != 0 && isWindowVisible(fg) != 0) {
      getWindowThreadProcessId(fg, pidPtr);
      if (pidPtr.value == currentPid) {
        _cachedHWnd = fg;
        calloc.free(pidPtr);
        return fg;
      }
    }

    // 2. 枚举所有窗口，找属于当前进程的可见窗口（排除主窗口：主窗口类名是 Flutter 窗口）
    const int gwHwndFirst = 0;
    const int gwHwndNext = 2;
    int hWnd = getWindow(0, gwHwndFirst);
    while (hWnd != 0) {
      if (isWindowVisible(hWnd) != 0 && hWnd != fg) {
        getWindowThreadProcessId(hWnd, pidPtr);
        if (pidPtr.value == currentPid) {
          _cachedHWnd = hWnd;
          calloc.free(pidPtr);
          return hWnd;
        }
      }
      hWnd = getWindow(hWnd, gwHwndNext);
    }
    calloc.free(pidPtr);
  } catch (_) {}
  return _getForegroundWindow();
}

/// 设置窗口大小并居中。去掉系统标题栏，用自定义标题栏+FFI拖动。
void _setupWindow(int width, int height) {
  for (int attempt = 0; attempt < 6; attempt++) {
    Future.delayed(Duration(milliseconds: 100 + attempt * 100), () {
      try {
        final hWnd = _findOurWindow();
        if (hWnd == 0) return;
        // 去掉系统标题栏和调整大小边框
        int style = _getWindowLong(hWnd, _gwlStyle);
        style &= ~(_wsCaption | _wsThickFrame | _wsSysMenu | _wsMinimizeBox | _wsMaximizeBox);
        _setWindowLong(hWnd, _gwlStyle, style);
        // 用 GetSystemMetrics 获取屏幕大小
        final screenW = _getSystemMetrics(_smCxScreen);
        final screenH = _getSystemMetrics(_smCyScreen);
        final x = ((screenW - width) ~/ 2).clamp(0, screenW - width);
        final y = ((screenH - height) ~/ 2).clamp(0, screenH - height);
        _setWindowPos(hWnd, 0, x, y, width, height, _swpFrameChanged | _swpNoZOrder);
      } catch (_) {}
    });
  }
}

/// 无边框窗口拖动：模拟标题栏拖动
void _startDrag() {
  try {
    final hWnd = _findOurWindow();
    if (hWnd == 0) return;
    _releaseCapture();
    _sendMessage(hWnd, _wmNcLButtonDown, _htCaption, 0);
  } catch (_) {}
}

// 窗口最小化/关闭
const int _swMinimize = 6;
const int _wmClose = 0x0010;
typedef _ShowWindowNative = ffi.Int32 Function(ffi.IntPtr hWnd, ffi.Int32 nCmdShow);
typedef _ShowWindowDart = int Function(int hWnd, int nCmdShow);
final _showWindow = _user32.lookupFunction<_ShowWindowNative, _ShowWindowDart>('ShowWindow');

void _minimizeWindow() {
  try {
    final hWnd = _findOurWindow();
    if (hWnd != 0) _showWindow(hWnd, _swMinimize);
  } catch (_) {}
}

void _closeWindow() {
  try {
    final hWnd = _findOurWindow();
    if (hWnd != 0) _sendMessage(hWnd, _wmClose, 0, 0);
  } catch (_) {}
}

/// 切换窗口置顶状态
void _toggleTopMost() {
  try {
    final hWnd = _findOurWindow();
    if (hWnd == 0) return;
    _isTopMost = !_isTopMost;
    _setWindowPos(hWnd, _isTopMost ? _hwndTopmost : _hwndNotopmost,
        0, 0, 0, 0, _swpNoMove | _swpNoSize | _swpFrameChanged);
  } catch (_) {}
}

// ==================== 倒计时页面 ====================
Widget _buildTimerTitleBar(BuildContext context, String title, VoidCallback? onFullscreen, {bool showPin = true}) {
  return Container(
    height: 36,
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surface,
      border: Border(bottom: BorderSide(color: Colors.grey.withOpacity(0.2), width: 1)),
    ),
    child: Row(
      children: [
        Expanded(
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onPanStart: (_) {
              _startDrag();
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            ),
          ),
        ),
        if (showPin)
          SizedBox(width: 36, height: 36, child: InkWell(
            onTap: _toggleTopMost,
            child: Icon(Icons.push_pin_outlined, size: 17, color: Colors.grey[600]),
          )),
        if (onFullscreen != null)
          SizedBox(width: 36, height: 36, child: InkWell(onTap: onFullscreen, child: const Icon(Icons.fullscreen, size: 17))),
        SizedBox(width: 36, height: 36, child: InkWell(
          onTap: _minimizeWindow,
          child: const Icon(Icons.remove, size: 17),
        )),
        SizedBox(
          width: 44, height: 36,
          child: InkWell(
            onTap: _closeWindow,
            hoverColor: Colors.red.withOpacity(0.8),
            child: const Icon(Icons.close, size: 17),
          ),
        ),
      ],
    ),
  );
}

class TimerPage extends StatefulWidget {
  const TimerPage({super.key});

  @override
  State<TimerPage> createState() => _TimerPageState();
}

class _TimerPageState extends State<TimerPage> {
  int _hours = 0;
  int _minutes = 5;
  int _totalSeconds = 0;
  int _remaining = 0;
  bool _running = false;
  bool _isCountdown = true; // true=倒计时, false=正计时(超时后)
  Timer? _tick;
  final AudioPlayer _player = AudioPlayer();
  bool _alarmPlayed = false;

  @override
  void initState() {
    super.initState();
    _cachedHWnd = 0;
    _isTopMost = false;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _setupWindow(440, 560);
    });
  }

  int get _oneFifth => (_totalSeconds / 5).ceil();

  void _start() {
    if (_totalSeconds == 0) {
      _totalSeconds = _hours * 3600 + _minutes * 60;
      _remaining = _totalSeconds;
    }
    setState(() {
      _running = true;
      _isCountdown = true;
      _alarmPlayed = false;
    });
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => _onTick());
  }

  void _pause() {
    setState(() => _running = false);
    _tick?.cancel();
  }

  void _reset() {
    _tick?.cancel();
    setState(() {
      _running = false;
      _totalSeconds = 0;
      _remaining = 0;
      _isCountdown = true;
      _alarmPlayed = false;
    });
  }

  void _onTick() {
    setState(() {
      if (_isCountdown) {
        _remaining--;
        if (_remaining <= 0) {
          _remaining = 0;
          _isCountdown = false;
          if (!_alarmPlayed) {
            _alarmPlayed = true;
            _playAlarm();
          }
        }
      } else {
        _remaining++;
      }
    });
  }

  Future<void> _playAlarm() async {
    try {
      // 用系统提示音替代（打包后可替换为 assets/alarm.wav）
      await _player.play(AssetSource('audio/alarm.wav'));
    } catch (_) {
      // 无音频文件时静默
    }
  }

  String _format(int sec) {
    final h = sec ~/ 3600;
    final m = (sec % 3600) ~/ 60;
    final s = sec % 60;
    if (h > 0) {
      return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  Color get _timerColor {
    if (!_isCountdown) return Colors.red;
    if (_totalSeconds > 0 && _remaining <= _oneFifth && _remaining > 0) {
      return Colors.red;
    }
    return Colors.black87;
  }

  Future<void> _toggleFullscreen() async {
    final isFull = await windowManager.isFullScreen();
    await windowManager.setFullScreen(!isFull);
    await windowManager.setAlwaysOnTop(!isFull);
  }

  @override
  void dispose() {
    _tick?.cancel();
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selecting = _totalSeconds == 0 && !_running;
    return Scaffold(
      body: Column(
        children: [
          _buildTimerTitleBar(context, '倒计时', null, showPin: true),
          Expanded(
            child: Center(
              child: selecting ? _buildPicker() : _buildDisplay(),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 24),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (!_running)
                  FilledButton.icon(
                    onPressed: _start,
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('开始'),
                    style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 28, vertical: 12)),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause),
                    label: const Text('暂停'),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 28, vertical: 12)),
                  ),
                const SizedBox(width: 12),
                TextButton.icon(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh),
                  label: const Text('重置'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDisplay() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          _format(_isCountdown ? _remaining : _remaining),
          style: TextStyle(
            fontSize: 72,
            fontWeight: FontWeight.bold,
            fontFeatures: const [FontFeature.tabularFigures()],
            color: _timerColor,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _isCountdown ? '倒计时中' : '已超时 · 正计时',
          style: TextStyle(fontSize: 16, color: Colors.grey[600]),
        ),
      ],
    );
  }

  Widget _buildPicker() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildWheel('小时', 24, (v) => _hours = v, _hours),
        const Text(':', style: TextStyle(fontSize: 48)),
        _buildWheel('分钟', 60, (v) => _minutes = v, _minutes),
      ],
    );
  }

  Widget _buildWheel(String label, int max, ValueChanged<int> onChanged, int initial) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: TextStyle(color: Colors.grey[600], fontSize: 13)),
        const SizedBox(height: 8),
        SizedBox(
          width: 90,
          height: 160,
          child: CupertinoPicker(
            itemExtent: 44,
            scrollController: FixedExtentScrollController(initialItem: initial),
            onSelectedItemChanged: onChanged,
            children: List.generate(max, (i) => Center(
                  child: Text(i.toString().padLeft(2, '0'),
                      style: const TextStyle(fontSize: 28)),
                )),
          ),
        ),
      ],
    );
  }
}

// ==================== 秒表页面 ====================
class StopwatchPage extends StatefulWidget {
  const StopwatchPage({super.key});

  @override
  State<StopwatchPage> createState() => _StopwatchPageState();
}

class _StopwatchPageState extends State<StopwatchPage> {
  int _elapsed = 0; // 毫秒
  int _lastLap = 0;
  final List<int> _laps = [];
  bool _running = false;
  Timer? _tick;
  final Stopwatch _sw = Stopwatch();

  @override
  void initState() {
    super.initState();
    _cachedHWnd = 0;
    _isTopMost = false;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _setupWindow(440, 600);
    });
  }

  void _start() {
    _sw.start();
    setState(() => _running = true);
    _tick = Timer.periodic(const Duration(milliseconds: 30), (_) {
      setState(() => _elapsed = _sw.elapsedMilliseconds);
    });
  }

  void _pause() {
    _sw.stop();
    _tick?.cancel();
    setState(() => _running = false);
  }

  void _reset() {
    _sw.stop();
    _sw.reset();
    _tick?.cancel();
    setState(() {
      _elapsed = 0;
      _laps.clear();
      _lastLap = 0;
      _running = false;
    });
  }

  void _lap() {
    setState(() {
      _laps.insert(0, _elapsed - _lastLap);
      _lastLap = _elapsed;
    });
  }

  String _fmt(int ms) {
    final m = ms ~/ 60000;
    final s = (ms % 60000) ~/ 1000;
    final cs = (ms % 1000) ~/ 10;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}.${cs.toString().padLeft(2, '0')}';
  }

  Future<void> _toggleFullscreen() async {
    final isFull = await windowManager.isFullScreen();
    await windowManager.setFullScreen(!isFull);
    await windowManager.setAlwaysOnTop(!isFull);
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _buildTimerTitleBar(context, '秒表', null, showPin: true),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Text(
              _fmt(_elapsed),
              style: const TextStyle(
                fontSize: 56,
                fontWeight: FontWeight.bold,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
          ),
          Expanded(
            child: _laps.isEmpty
                ? Center(
                    child: Text('暂无记次',
                        style: TextStyle(color: Colors.grey[500])),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    itemCount: _laps.length,
                    itemBuilder: (ctx, i) {
                      final lapNum = _laps.length - i;
                      return ListTile(
                        dense: true,
                        leading: Text('第$lapNum次',
                            style: const TextStyle(
                                fontWeight: FontWeight.w600)),
                        trailing: Text(_fmt(_laps[i]),
                            style: const TextStyle(
                                fontFeatures: [FontFeature.tabularFigures()])),
                      );
                    },
                  ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 24),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (!_running)
                  FilledButton.icon(
                    onPressed: _start,
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('开始'),
                    style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 28, vertical: 12)),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause),
                    label: const Text('暂停'),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 28, vertical: 12)),
                  ),
                const SizedBox(width: 12),
                if (_running)
                  TextButton.icon(
                    onPressed: _lap,
                    icon: const Icon(Icons.flag),
                    label: const Text('记次'),
                  ),
                const SizedBox(width: 12),
                TextButton.icon(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh),
                  label: const Text('重置'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
);
}
}
