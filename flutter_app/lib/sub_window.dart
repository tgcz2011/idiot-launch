import 'dart:async';
import 'dart:ffi' as ffi;

import 'package:ffi/ffi.dart';

import 'app_log.dart';

// ============================================================================
// 子窗口（倒计时 / 秒表）原生窗口控制
//
// 为什么不用 window_manager：它作用于进程的"主窗口"，而子窗口是
// desktop_multi_window 在同一进程里新建的另一个顶层窗口。
//
// 原来的实现为什么"点几下就未响应"：
//   1) 全部窗口（主窗口 + 每个子窗口）都由进程主线程/PowerShell 消息循环那一根线程
//      创建并拥有。Dart 的 UI 线程不是窗口线程。
//   2) 对别的线程拥有的窗口调用 SendMessage（WM_CLOSE / WM_SETTEXT）或
//      SetWindowPos（不带 SWP_ASYNCWINDOWPOS）会同步等待窗口线程处理消息；
//      而窗口线程处理 WM_CLOSE 时又会回头找 Dart（插件 / Flutter 引擎），
//      两边互等 → 整个界面"未响应"。
//   3) 每 100ms 用 EnumWindows 重新找一次窗口，并且"取最后一个"，倒计时和秒表
//      两个窗口会互相抢（把对方的标题/尺寸改掉）。
//
// 现在的做法：
//   * 关闭用 PostMessage（异步投递，不等待）。
//   * 移动/缩放一律 SWP_ASYNCWINDOWPOS，绝不阻塞。
//   * 设置标题用 SendMessageTimeoutW + SMTO_ABORTIFHUNG（对方卡住就放弃）。
//   * 只在"定位"阶段做 EnumWindows，定位成功立刻停表；并且定位条件是
//     "本进程 + 可见 + 标题为空"（插件创建窗口时标题就是空的），
//     定位成功马上写标题 → 已经配置好的窗口永远不会被第二个子窗口抢走。
// ============================================================================

final ffi.DynamicLibrary _user32 = ffi.DynamicLibrary.open('user32.dll');
final ffi.DynamicLibrary _kernel32 = ffi.DynamicLibrary.open('kernel32.dll');

// ---- user32 / kernel32 绑定 -------------------------------------------------

typedef _EnumWindowsProcNative = ffi.Int32 Function(
    ffi.IntPtr hWnd, ffi.IntPtr lParam);

typedef _EnumWindowsNative = ffi.Int32 Function(
    ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> lpEnumFunc,
    ffi.IntPtr lParam);
typedef _EnumWindowsDart = int Function(
    ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> lpEnumFunc,
    int lParam);

final _EnumWindowsDart _enumWindows = _user32.lookupFunction<
    _EnumWindowsNative, _EnumWindowsDart>('EnumWindows');

typedef _GetWindowThreadProcessIdNative = ffi.Uint32 Function(
    ffi.IntPtr hWnd, ffi.Pointer<ffi.Uint32> lpdwProcessId);
typedef _GetWindowThreadProcessIdDart = int Function(
    int hWnd, ffi.Pointer<ffi.Uint32> lpdwProcessId);

final _GetWindowThreadProcessIdDart _getWindowThreadProcessId =
    _user32.lookupFunction<_GetWindowThreadProcessIdNative,
        _GetWindowThreadProcessIdDart>('GetWindowThreadProcessId');

typedef _IntPtr2Native = ffi.IntPtr Function(ffi.IntPtr, ffi.Int32);
typedef _IntPtr2Dart = int Function(int, int);
typedef _IntPtr3Native = ffi.IntPtr Function(ffi.IntPtr, ffi.Int32, ffi.IntPtr);
typedef _IntPtr3Dart = int Function(int, int, int);
typedef _Int1Native = ffi.Int32 Function(ffi.IntPtr);
typedef _Int1Dart = int Function(int);
typedef _Int2Native = ffi.Int32 Function(ffi.IntPtr, ffi.Int32);
typedef _Int2Dart = int Function(int, int);

final _Int1Dart _getWindowTextLength =
    _user32.lookupFunction<_Int1Native, _Int1Dart>('GetWindowTextLengthW');
final _Int1Dart _isWindowVisible =
    _user32.lookupFunction<_Int1Native, _Int1Dart>('IsWindowVisible');
final _Int2Dart _showWindow =
    _user32.lookupFunction<_Int2Native, _Int2Dart>('ShowWindow');
final _Int2Dart _getWindowLong =
    _user32.lookupFunction<_IntPtr2Native, _IntPtr2Dart>('GetWindowLongW');
final _IntPtr3Dart _setWindowLong = _user32
    .lookupFunction<_IntPtr3Native, _IntPtr3Dart>('SetWindowLongW');

typedef _GetCurrentProcessIdNative = ffi.Uint32 Function();
typedef _GetCurrentProcessIdDart = int Function();
final _GetCurrentProcessIdDart _getCurrentProcessId = _kernel32
    .lookupFunction<_GetCurrentProcessIdNative, _GetCurrentProcessIdDart>(
        'GetCurrentProcessId');

typedef _GetWindowRectNative = ffi.Int32 Function(
    ffi.IntPtr hWnd, ffi.Pointer<_Rect> lpRect);
typedef _GetWindowRectDart = int Function(int hWnd, ffi.Pointer<_Rect> lpRect);
final _GetWindowRectDart _getWindowRect = _user32
    .lookupFunction<_GetWindowRectNative, _GetWindowRectDart>('GetWindowRect');

typedef _SetWindowPosNative = ffi.Int32 Function(ffi.IntPtr hWnd,
    ffi.IntPtr hWndInsertAfter, ffi.Int32 x, ffi.Int32 y, ffi.Int32 cx, ffi.Int32 cy, ffi.Uint32 uFlags);
typedef _SetWindowPosDart = int Function(
    int hWnd, int hWndInsertAfter, int x, int y, int cx, int cy, int uFlags);
final _SetWindowPosDart _setWindowPos = _user32
    .lookupFunction<_SetWindowPosNative, _SetWindowPosDart>('SetWindowPos');

typedef _PostMessageNative = ffi.Int32 Function(
    ffi.IntPtr hWnd, ffi.Uint32 msg, ffi.IntPtr wParam, ffi.IntPtr lParam);
typedef _PostMessageDart = int Function(
    int hWnd, int msg, int wParam, int lParam);
final _PostMessageDart _postMessage = _user32
    .lookupFunction<_PostMessageNative, _PostMessageDart>('PostMessageW');

typedef _SendMessageTimeoutNative = ffi.IntPtr Function(
    ffi.IntPtr hWnd,
    ffi.Uint32 msg,
    ffi.IntPtr wParam,
    ffi.IntPtr lParam,
    ffi.Uint32 flags,
    ffi.Uint32 timeout,
    ffi.Pointer<ffi.UintPtr> result);
typedef _SendMessageTimeoutDart = int Function(int hWnd, int msg, int wParam,
    int lParam, int flags, int timeout, ffi.Pointer<ffi.UintPtr> result);
final _SendMessageTimeoutDart _sendMessageTimeout =
    _user32.lookupFunction<_SendMessageTimeoutNative, _SendMessageTimeoutDart>(
        'SendMessageTimeoutW');

typedef _MonitorFromWindowNative = ffi.IntPtr Function(
    ffi.IntPtr hWnd, ffi.Uint32 dwFlags);
typedef _MonitorFromWindowDart = int Function(int hWnd, int dwFlags);
final _MonitorFromWindowDart _monitorFromWindow = _user32.lookupFunction<
    _MonitorFromWindowNative, _MonitorFromWindowDart>('MonitorFromWindow');

typedef _GetMonitorInfoNative = ffi.Int32 Function(
    ffi.IntPtr hMonitor, ffi.Pointer<_MonitorInfo> lpmi);
typedef _GetMonitorInfoDart = int Function(
    int hMonitor, ffi.Pointer<_MonitorInfo> lpmi);
final _GetMonitorInfoDart _getMonitorInfo = _user32.lookupFunction<
    _GetMonitorInfoNative, _GetMonitorInfoDart>('GetMonitorInfoW');

// ---- 结构体 -----------------------------------------------------------------

final class _Rect extends ffi.Struct {
  @ffi.Int32()
  external int left;
  @ffi.Int32()
  external int top;
  @ffi.Int32()
  external int right;
  @ffi.Int32()
  external int bottom;
}

final class _MonitorInfo extends ffi.Struct {
  @ffi.Uint32()
  external int cbSize;
  external _Rect rcMonitor;
  external _Rect rcWork;
  @ffi.Uint32()
  external int dwFlags;
}

// ---- 常量 -------------------------------------------------------------------

const int _gwlStyle = -16;
const int _wsCaption = 0x00C00000;
const int _wsSysMenu = 0x00080000;
const int _wsMinimizeBox = 0x00020000;
const int _wsMaximizeBox = 0x00010000;

const int _swpNoSize = 0x0001;
const int _swpNoMove = 0x0002;
const int _swpNoZOrder = 0x0004;
const int _swpNoActivate = 0x0010;
const int _swpFrameChanged = 0x0020;
/// 关键：把请求投递给窗口所属线程，本线程立即返回，不会因为对方忙而死等。
const int _swpAsyncWindowPos = 0x4000;

const int _hwndTopMost = -1;
const int _hwndNoTopMost = -2;
const int _swMinimize = 6;
const int _wmClose = 0x0010;
const int _wmSetText = 0x000C;
const int _smtoAbortIfHung = 0x0002;
const int _monitorDefaultToNearest = 2;

// ---- EnumWindows 回调（FFI 回调必须是顶级函数，且只创建一次） ---------------

final List<int> _enumResult = <int>[];
int _enumPid = 0;

int _enumWindowsProc(int hWnd, int lParam) {
  try {
    final pidPtr = _pidScratch;
    _getWindowThreadProcessId(hWnd, pidPtr);
    if (pidPtr.value == _enumPid &&
        _isWindowVisible(hWnd) != 0 &&
        _getWindowTextLength(hWnd) == 0) {
      _enumResult.add(hWnd);
    }
  } catch (_) {
    // 忽略单个窗口的读取失败
  }
  return 1; // 继续枚举
}

final ffi.Pointer<ffi.Uint32> _pidScratch = calloc<ffi.Uint32>();
final ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> _enumProcPtr =
    ffi.Pointer.fromFunction<_EnumWindowsProcNative>(_enumWindowsProc, 0);

/// 找出"属于本进程、可见、且标题为空"的顶层窗口。
///
/// 标题为空 = 这个子窗口还没被配置过（插件创建时标题是空字符串）。
List<int> _findUnstyledWindows() {
  _enumResult.clear();
  _enumPid = _getCurrentProcessId();
  try {
    _enumWindows(_enumProcPtr, 0);
  } catch (e, s) {
    AppLog.error('EnumWindows 失败', e, s);
  }
  return List<int>.from(_enumResult);
}

// ---- 窗口控制器 -------------------------------------------------------------

class SubWindow {
  SubWindow(this.tag);

  /// 日志/调试用标记，例如 'timer' / 'stopwatch'
  final String tag;

  int _hwnd = 0;
  Timer? _locateTimer;
  int _attempts = 0;
  bool _isTopMost = false;
  bool _isFullscreen = false;

  int _widthPx = 360;
  int _heightPx = 440;
  String _title = '';

  int _dragX = 0;
  int _dragY = 0;

  /// 窗口是否已就绪（拿到 HWND 并完成样式设置）。
  bool get isReady => _hwnd != 0;

  bool get isTopMost => _isTopMost;

  /// 开始定位并配置窗口。
  ///
  /// [logicalWidth] / [logicalHeight] 是 Flutter 逻辑像素，调用方用
  /// MediaQuery.devicePixelRatio 换算成物理像素传进来。
  void attach({
    required int widthPx,
    required int heightPx,
    required String title,
  }) {
    _widthPx = widthPx;
    _heightPx = heightPx;
    _title = title;
    _attempts = 0;
    _locateTimer?.cancel();
    // 立即试一次，之后每 150ms 重试，最多 6 秒
    _tryAttach();
    if (_hwnd == 0) {
      _locateTimer = Timer.periodic(const Duration(milliseconds: 150), (t) {
        _attempts++;
        _tryAttach();
        if (_hwnd != 0 || _attempts > 40) {
          t.cancel();
          _locateTimer = null;
          if (_hwnd == 0) {
            AppLog.warn('$tag: 6 秒内未找到自身窗口，放弃样式设置（窗口仍可用）');
          }
        }
      });
    }
  }

  void _tryAttach() {
    if (_hwnd != 0) return;
    final candidates = _findUnstyledWindows();
    if (candidates.isEmpty) return;
    // 取最后创建的那个（EnumWindows 按 Z 序，新窗口在最前，这里取列表末尾兜底）
    final h = candidates.last;
    final style = _getWindowLong(h, _gwlStyle);
    if ((style & _wsCaption) != 0) {
      final stripped = style &
          ~(_wsCaption | _wsSysMenu | _wsMinimizeBox | _wsMaximizeBox);
      _setWindowLong(h, _gwlStyle, stripped);
      if ((_getWindowLong(h, _gwlStyle) & _wsCaption) != 0) {
        return; // 样式没生效，下一轮再试
      }
    }
    _hwnd = h;
    _applyFrame();
    _setTitle(_title);
    AppLog.info('$tag: 已接管窗口 hwnd=$h ${_widthPx}x$_heightPx');
  }

  void _applyFrame() {
    if (_hwnd == 0) return;
    final r = _centeredRect(_widthPx, _heightPx);
    _setWindowPos(_hwnd, 0, r[0], r[1], r[2], r[3],
        _swpAsyncWindowPos | _swpNoZOrder | _swpFrameChanged | _swpNoActivate);
  }

  /// 在当前显示器的工作区里居中（避开任务栏、支持多显示器 / 缩放）。
  List<int> _centeredRect(int w, int h) {
    final mi = calloc<_MonitorInfo>();
    try {
      mi.ref.cbSize = ffi.sizeOf<_MonitorInfo>();
      final mon = _monitorFromWindow(_hwnd, _monitorDefaultToNearest);
      int left = 0, top = 0, right = 1920, bottom = 1080;
      if (mon != 0 && _getMonitorInfo(mon, mi) != 0) {
        left = mi.ref.rcWork.left;
        top = mi.ref.rcWork.top;
        right = mi.ref.rcWork.right;
        bottom = mi.ref.rcWork.bottom;
      }
      final workW = right - left;
      final workH = bottom - top;
      final x = left + ((workW - w) ~/ 2).clamp(0, workW);
      final y = top + ((workH - h) ~/ 2).clamp(0, workH);
      return <int>[x, y, w, h];
    } finally {
      calloc.free(mi);
    }
  }

  void _setTitle(String title) {
    if (_hwnd == 0 || title.isEmpty) return;
    final ptr = title.toNativeUtf16();
    final out = calloc<ffi.UintPtr>();
    try {
      // 对方线程卡住时直接超时返回，绝不把自己的 UI 线程挂死
      _sendMessageTimeout(_hwnd, _wmSetText, 0, ptr.address, _smtoAbortIfHung,
          1000, out);
    } finally {
      calloc.free(ptr);
      calloc.free(out);
    }
  }

  /// 拖动：记录起点，之后按增量移动（异步投递，不阻塞手势）。
  void beginDrag() {
    if (_hwnd == 0) return;
    final rc = calloc<_Rect>();
    try {
      if (_getWindowRect(_hwnd, rc) != 0) {
        _dragX = rc.ref.left;
        _dragY = rc.ref.top;
      }
    } finally {
      calloc.free(rc);
    }
  }

  void updateDrag(double dx, double dy) {
    if (_hwnd == 0) return;
    _dragX += dx.round();
    _dragY += dy.round();
    _setWindowPos(_hwnd, 0, _dragX, _dragY, 0, 0,
        _swpAsyncWindowPos | _swpNoSize | _swpNoZOrder | _swpNoActivate);
  }

  void minimize() {
    if (_hwnd == 0) return;
    _showWindow(_hwnd, _swMinimize);
  }

  /// 关闭窗口。用 PostMessage 而不是 SendMessage —— 这是"未响应"的主因之一。
  void close() {
    if (_hwnd == 0) return;
    if (_postMessage(_hwnd, _wmClose, 0, 0) == 0) {
      AppLog.warn('$tag: PostMessage(WM_CLOSE) 失败');
    }
  }

  bool toggleTopMost() {
    if (_hwnd == 0) return _isTopMost;
    _isTopMost = !_isTopMost;
    _setWindowPos(_hwnd, _isTopMost ? _hwndTopMost : _hwndNoTopMost, 0, 0, 0, 0,
        _swpAsyncWindowPos | _swpNoMove | _swpNoSize | _swpNoActivate);
    return _isTopMost;
  }

  /// 全屏：铺满当前显示器（含任务栏区域），再次调用还原。
  bool toggleFullscreen() {
    if (_hwnd == 0) return _isFullscreen;
    if (!_isFullscreen) {
      final mi = calloc<_MonitorInfo>();
      try {
        mi.ref.cbSize = ffi.sizeOf<_MonitorInfo>();
        final mon = _monitorFromWindow(_hwnd, _monitorDefaultToNearest);
        if (mon == 0 || _getMonitorInfo(mon, mi) == 0) return false;
        final m = mi.ref.rcMonitor;
        _isFullscreen = true;
        _setWindowPos(
            _hwnd,
            0,
            m.left,
            m.top,
            m.right - m.left,
            m.bottom - m.top,
            _swpAsyncWindowPos |
                _swpNoZOrder |
                _swpFrameChanged |
                _swpNoActivate);
      } finally {
        calloc.free(mi);
      }
    } else {
      _isFullscreen = false;
      _applyFrame();
    }
    return _isFullscreen;
  }

  void dispose() {
    _locateTimer?.cancel();
    _locateTimer = null;
  }
}
