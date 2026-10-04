import 'dart:async';
import 'dart:ffi' as ffi;
import 'package:ffi/ffi.dart';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:audioplayers/audioplayers.dart';

// ==================== FFI: user32.dll / kernel32.dll 绑定 ====================
final _user32 = ffi.DynamicLibrary.open('user32.dll');
final _kernel32 = ffi.DynamicLibrary.open('kernel32.dll');

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

typedef _ReleaseCaptureNative = ffi.Int32 Function();
typedef _ReleaseCaptureDart = int Function();
final _releaseCapture = _user32.lookupFunction<_ReleaseCaptureNative, _ReleaseCaptureDart>('ReleaseCapture');

typedef _SendMessageNative = ffi.IntPtr Function(
    ffi.IntPtr hWnd, ffi.Uint32 Msg, ffi.IntPtr wParam, ffi.IntPtr lParam);
typedef _SendMessageDart = int Function(int hWnd, int Msg, int wParam, int lParam);
final _sendMessage = _user32.lookupFunction<_SendMessageNative, _SendMessageDart>('SendMessageW');

typedef _ShowWindowNative = ffi.Int32 Function(ffi.IntPtr hWnd, ffi.Int32 nCmdShow);
typedef _ShowWindowDart = int Function(int hWnd, int nCmdShow);
final _showWindow = _user32.lookupFunction<_ShowWindowNative, _ShowWindowDart>('ShowWindow');

typedef _GetSystemMetricsNative = ffi.Int32 Function(ffi.Int32 nIndex);
typedef _GetSystemMetricsDart = int Function(int nIndex);
final _getSystemMetrics = _user32.lookupFunction<_GetSystemMetricsNative, _GetSystemMetricsDart>('GetSystemMetrics');

typedef _SetWindowTextNative = ffi.Int32 Function(ffi.IntPtr hWnd, ffi.Pointer<Utf16> lpString);
typedef _SetWindowTextDart = int Function(int hWnd, ffi.Pointer<Utf16>);
final _setWindowText = _user32.lookupFunction<_SetWindowTextNative, _SetWindowTextDart>('SetWindowTextW');

// 新增：精准定位子窗口所需的 API
typedef _GetCurrentProcessIdNative = ffi.Uint32 Function();
typedef _GetCurrentProcessIdDart = int Function();
final _getCurrentProcessId = _kernel32.lookupFunction<_GetCurrentProcessIdNative, _GetCurrentProcessIdDart>('GetCurrentProcessId');

typedef _GetWindowThreadProcessIdNative = ffi.Uint32 Function(ffi.IntPtr hWnd, ffi.Pointer<ffi.Uint32> lpdwProcessId);
typedef _GetWindowThreadProcessIdDart = int Function(int hWnd, ffi.Pointer<ffi.Uint32> lpdwProcessId);
final _getWindowThreadProcessId = _user32.lookupFunction<_GetWindowThreadProcessIdNative, _GetWindowThreadProcessIdDart>('GetWindowThreadProcessId');

typedef _IsWindowVisibleNative = ffi.Int32 Function(ffi.IntPtr hWnd);
typedef _IsWindowVisibleDart = int Function(int hWnd);
final _isWindowVisible = _user32.lookupFunction<_IsWindowVisibleNative, _IsWindowVisibleDart>('IsWindowVisible');

typedef _GetWindowTextNative = ffi.Int32 Function(ffi.IntPtr hWnd, ffi.Pointer<Utf16> lpString, ffi.Int32 nMaxCount);
typedef _GetWindowTextDart = int Function(int hWnd, ffi.Pointer<Utf16> lpString, int nMaxCount);
final _getWindowText = _user32.lookupFunction<_GetWindowTextNative, _GetWindowTextDart>('GetWindowTextW');

// EnumWindows 回调类型
typedef _EnumWindowsProcNative = ffi.Int32 Function(ffi.IntPtr hWnd, ffi.IntPtr lParam);
typedef _EnumWindowsProcDart = int Function(int hWnd, int lParam);

typedef _EnumWindowsNative = ffi.Int32 Function(
    ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> lpEnumFunc, ffi.IntPtr lParam);
typedef _EnumWindowsDart = int Function(
    ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> lpEnumFunc, int lParam);
final _enumWindows = _user32.lookupFunction<_EnumWindowsNative, _EnumWindowsDart>('EnumWindows');

const int _gwlStyle = -16;
const int _wsCaption = 0x00C00000;
const int _wsSysMenu = 0x00080000;
const int _wsMinimizeBox = 0x00020000;
const int _wsMaximizeBox = 0x00010000;
const int _wsThickFrame = 0x00040000;
const int _swpFrameChanged = 0x0020;
const int _swpNoZOrder = 0x0004;
const int _swpNoMove = 0x0002;
const int _swpNoSize = 0x0001;
const int _hwndTopmost = -1;
const int _hwndNotopmost = -2;
const int _smCxScreen = 0;
const int _smCyScreen = 1;
const int _wmNcLButtonDown = 0x00A1;
const int _htCaption = 2;
const int _swMinimize = 6;
const int _wmClose = 0x0010;

// ==================== EnumWindows 回调（全局，因为 FFI 回调必须是顶级函数） ====================
final List<int> _gEnumResult = [];
int _gEnumPid = 0;

int _enumWindowsProc(int hWnd, int lParam) {
  try {
    final pidPtr = calloc<ffi.Uint32>();
    _getWindowThreadProcessId(hWnd, pidPtr);
    final pid = pidPtr.value;
    calloc.free(pidPtr);
    if (pid == _gEnumPid && _isWindowVisible(hWnd) != 0) {
      // 获取窗口标题，排除主窗口
      final titlePtr = calloc<ffi.Uint16>(512);
      _getWindowText(hWnd, titlePtr.cast<Utf16>(), 512);
      final title = titlePtr.cast<Utf16>().toDartString();
      calloc.free(titlePtr);
      // 主窗口标题是"傻瓜启动器"或"idiot_launch"，子窗口标题可能为空或"倒计时"/"秒表"
      if (title != '傻瓜启动器' && title != 'idiot_launch' && title != 'Idiot Launch') {
        _gEnumResult.add(hWnd);
      }
    }
  } catch (_) {}
  return 1; // 继续枚举
}

/// 通过 EnumWindows + 进程 ID 过滤，找到当前进程的所有子窗口（排除主窗口）
List<int> _findSubWindows() {
  _gEnumResult.clear();
  _gEnumPid = _getCurrentProcessId();
  final callback = ffi.Pointer.fromFunction<_EnumWindowsProcNative>(_enumWindowsProc, 0);
  _enumWindows(callback, 0);
  return List.from(_gEnumResult);
}

// ==================== 子窗口控制器 ====================
class _SubWindowController {
  int hWnd = 0;
  bool isTopMost = false;
  Timer? _retryTimer;
  int _retryCount = 0;

  /// 初始化：通过 EnumWindows 精准定位子窗口，去掉标题栏，设置大小并居中
  Future<void> setup(int width, int height, String title) async {
    _retryCount = 0;
    // 最多重试 30 次（约 3 秒），确保窗口完全创建后再修改样式
    _retryTimer = Timer.periodic(const Duration(milliseconds: 100), (timer) {
      _retryCount++;
      try {
        final subWindows = _findSubWindows();
        if (subWindows.isEmpty) {
          if (_retryCount > 30) {
            timer.cancel();
          }
          return;
        }
        // 选择最后一个子窗口（最新创建的）
        final hwnd = subWindows.last;

        // 设置窗口标题
        final titlePtr = title.toNativeUtf16();
        _setWindowText(hwnd, titlePtr);
        calloc.free(titlePtr);

        // 去掉系统标题栏（保留 WS_THICKFRAME 以便拖动和调整大小）
        int style = _getWindowLong(hwnd, _gwlStyle);
        style &= ~(_wsCaption | _wsSysMenu | _wsMinimizeBox | _wsMaximizeBox);
        style |= _wsThickFrame; // 确保有 thick frame 才能拖动
        _setWindowLong(hwnd, _gwlStyle, style);

        // 居中显示（SWP_FRAMECHANGED 刷新非客户区）
        final screenW = _getSystemMetrics(_smCxScreen);
        final screenH = _getSystemMetrics(_smCyScreen);
        final x = ((screenW - width) ~/ 2).clamp(0, screenW - width);
        final y = ((screenH - height) ~/ 2).clamp(0, screenH - height);
        _setWindowPos(hwnd, 0, x, y, width, height, _swpFrameChanged | _swpNoZOrder);

        // 验证样式是否生效（标题栏位是否被清除）
        final newStyle = _getWindowLong(hwnd, _gwlStyle);
        if ((newStyle & _wsCaption) == 0) {
          hWnd = hwnd;
          timer.cancel();
          _retryTimer = null;
        }
      } catch (_) {}
      if (_retryCount > 30) {
        timer.cancel();
        _retryTimer = null;
      }
    });
  }

  /// 拖动窗口：模拟标题栏拖动
  void startDrag() {
    if (hWnd == 0) return;
    try {
      _releaseCapture();
      _sendMessage(hWnd, _wmNcLButtonDown, _htCaption, 0);
    } catch (_) {}
  }

  /// 最小化
  void minimize() {
    if (hWnd == 0) return;
    try {
      _showWindow(hWnd, _swMinimize);
    } catch (_) {}
  }

  /// 关闭
  void close() {
    if (hWnd == 0) return;
    try {
      _sendMessage(hWnd, _wmClose, 0, 0);
    } catch (_) {}
  }

  /// 切换置顶，返回新状态
  bool toggleTopMost() {
    if (hWnd == 0) return isTopMost;
    try {
      isTopMost = !isTopMost;
      _setWindowPos(hWnd, isTopMost ? _hwndTopmost : _hwndNotopmost,
          0, 0, 0, 0, _swpNoMove | _swpNoSize | _swpFrameChanged);
    } catch (_) {}
    return isTopMost;
  }

  void dispose() {
    _retryTimer?.cancel();
    _retryTimer = null;
  }
}

// ==================== 通用标题栏 ====================
class _TimerTitleBar extends StatelessWidget {
  final String title;
  final VoidCallback onDrag;
  final VoidCallback onMinimize;
  final VoidCallback onClose;
  final bool isPinned;
  final VoidCallback? onTogglePin;

  const _TimerTitleBar({
    required this.title,
    required this.onDrag,
    required this.onMinimize,
    required this.onClose,
    required this.isPinned,
    this.onTogglePin,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 34,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(bottom: BorderSide(color: Colors.grey.withOpacity(0.15), width: 1)),
      ),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onPanStart: (_) => onDrag(),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                child: Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              ),
            ),
          ),
          if (onTogglePin != null)
            SizedBox(
              width: 34, height: 34,
              child: InkWell(
                onTap: onTogglePin,
                child: Icon(
                  isPinned ? Icons.push_pin : Icons.push_pin_outlined,
                  size: 16,
                  color: isPinned ? Theme.of(context).colorScheme.primary : Colors.grey[600],
                ),
              ),
            ),
          SizedBox(
            width: 34, height: 34,
            child: InkWell(onTap: onMinimize, child: const Icon(Icons.remove, size: 16)),
          ),
          SizedBox(
            width: 42, height: 34,
            child: InkWell(
              onTap: onClose,
              hoverColor: Colors.red.withOpacity(0.8),
              child: const Icon(Icons.close, size: 16),
            ),
          ),
        ],
      ),
    );
  }
}

// ==================== 倒计时页面 ====================
class TimerPage extends StatefulWidget {
  const TimerPage({super.key});

  @override
  State<TimerPage> createState() => _TimerPageState();
}

class _TimerPageState extends State<TimerPage> {
  final _win = _SubWindowController();
  int _hours = 0;
  int _minutes = 5;
  int _totalSeconds = 0;
  int _remaining = 0;
  bool _running = false;
  bool _isCountdown = true;
  Timer? _tick;
  final AudioPlayer _player = AudioPlayer();
  bool _alarmPlayed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _win.setup(360, 440, '倒计时');
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
      await _player.play(AssetSource('audio/alarm.wav'));
    } catch (_) {}
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
    if (_totalSeconds > 0 && _remaining <= _oneFifth && _remaining > 0) return Colors.red;
    return Colors.black87;
  }

  @override
  void dispose() {
    _tick?.cancel();
    _player.dispose();
    _win.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selecting = _totalSeconds == 0 && !_running;
    return Scaffold(
      body: Column(
        children: [
          _TimerTitleBar(
            title: '倒计时',
            onDrag: () => _win.startDrag(),
            onMinimize: () => _win.minimize(),
            onClose: () => _win.close(),
            isPinned: _win.isTopMost,
            onTogglePin: () => setState(() => _win.toggleTopMost()),
          ),
          Expanded(
            child: Center(
              child: selecting ? _buildPicker() : _buildDisplay(),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 20),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (!_running)
                  FilledButton.icon(
                    onPressed: _start,
                    icon: const Icon(Icons.play_arrow, size: 20),
                    label: const Text('开始'),
                    style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10)),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause, size: 20),
                    label: const Text('暂停'),
                    style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10)),
                  ),
                const SizedBox(width: 10),
                TextButton.icon(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh, size: 18),
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
          _format(_remaining),
          style: TextStyle(
            fontSize: 64,
            fontWeight: FontWeight.bold,
            fontFeatures: const [FontFeature.tabularFigures()],
            color: _timerColor,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          _isCountdown ? '倒计时中' : '已超时 · 正计时',
          style: TextStyle(fontSize: 14, color: Colors.grey[600]),
        ),
      ],
    );
  }

  Widget _buildPicker() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildWheel('小时', 24, (v) => _hours = v, _hours),
        const Text(':', style: TextStyle(fontSize: 40)),
        _buildWheel('分钟', 60, (v) => _minutes = v, _minutes),
      ],
    );
  }

  Widget _buildWheel(String label, int max, ValueChanged<int> onChanged, int initial) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: TextStyle(color: Colors.grey[600], fontSize: 12)),
        const SizedBox(height: 6),
        SizedBox(
          width: 80,
          height: 140,
          child: CupertinoPicker(
            itemExtent: 40,
            scrollController: FixedExtentScrollController(initialItem: initial),
            onSelectedItemChanged: onChanged,
            children: List.generate(max, (i) => Center(
                  child: Text(i.toString().padLeft(2, '0'), style: const TextStyle(fontSize: 24)),
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
  final _win = _SubWindowController();
  int _elapsed = 0;
  int _lastLap = 0;
  final List<int> _laps = [];
  bool _running = false;
  Timer? _tick;
  final Stopwatch _sw = Stopwatch();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _win.setup(360, 480, '秒表');
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

  @override
  void dispose() {
    _tick?.cancel();
    _win.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _TimerTitleBar(
            title: '秒表',
            onDrag: () => _win.startDrag(),
            onMinimize: () => _win.minimize(),
            onClose: () => _win.close(),
            isPinned: _win.isTopMost,
            onTogglePin: () => setState(() => _win.toggleTopMost()),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Text(
              _fmt(_elapsed),
              style: const TextStyle(
                fontSize: 48,
                fontWeight: FontWeight.bold,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
          ),
          Expanded(
            child: _laps.isEmpty
                ? Center(child: Text('暂无记次', style: TextStyle(color: Colors.grey[500], fontSize: 14)))
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    itemCount: _laps.length,
                    itemBuilder: (ctx, i) {
                      final lapNum = _laps.length - i;
                      return ListTile(
                        dense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 8),
                        leading: Text('第$lapNum次', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                        trailing: Text(_fmt(_laps[i]),
                            style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()], fontSize: 14)),
                      );
                    },
                  ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 20),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (!_running)
                  FilledButton.icon(
                    onPressed: _start,
                    icon: const Icon(Icons.play_arrow, size: 20),
                    label: const Text('开始'),
                    style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10)),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause, size: 20),
                    label: const Text('暂停'),
                    style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10)),
                  ),
                const SizedBox(width: 10),
                if (_running)
                  TextButton.icon(
                    onPressed: _lap,
                    icon: const Icon(Icons.flag, size: 18),
                    label: const Text('记次'),
                  ),
                const SizedBox(width: 10),
                TextButton.icon(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh, size: 18),
                  label: const Text('重置'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
