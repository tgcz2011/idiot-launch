import 'dart:async';
import 'dart:ffi' as ffi;
import 'dart:ui' show PointerDeviceKind;

import 'package:ffi/ffi.dart';

import 'app_log.dart';

// ============================================================================
// 子窗口（倒计时 / 秒表）原生窗口控制
//
// 为什么不用 window_manager：它作用于进程的"主窗口"，而子窗口是
// desktop_multi_window 在同一进程里新建的另一个顶层窗口。
//
// 历史问题（beta27 用户实测反馈）：
//   1) 子窗口自己去 EnumWindows 找"本进程 + 标题为空"的窗口 → 同时开两个窗口时
//      两边可能选中同一个窗口：A 的拖动会移动 B，另一个窗口永远保持插件默认的
//      800x600 + 原生标题栏（"有些一直留着"就是这个）。
//   2) 对别的线程拥有的窗口调用 SendMessage / 不带 SWP_ASYNCWINDOWPOS 的
//      SetWindowPos 会同步等待对方线程 → 界面"未响应"。
//   3) 窗口创建时是可见的，于是先闪一下 800x600 的原生窗口再被改样式。
//
// 现在的做法：
//   * 父窗口创建子窗口时用 hiddenAtLaunch=true，并在创建前后对比本进程顶层窗口，
//     确定地找出"新出现的那个 HWND"，通过窗口通道推给子窗口；
//     子窗口拿到 HWND 后立刻改样式、再自己显示 —— 看不到 800x600 的原生窗口。
//   * 拿不到 HWND 时回退到搜索，并且无论如何都会让窗口显示出来，
//     不会出现"点了没反应"。
//   * 关闭用 PostMessage，移动/缩放一律 SWP_ASYNCWINDOWPOS，设标题用
//     SendMessageTimeoutW + SMTO_ABORTIFHUNG。
//   * 拖动：鼠标拖动先 SetCapture（beta29 实测"拖动不跟手"的真正原因 ——
//     没有捕获，窗口一动光标就跑到窗口外面，后续鼠标消息收不到）；
//     触摸由系统自动捕获。逐帧按"窗口原位 + 指针起点 × devicePixelRatio"
//     算绝对位置，不用累加 delta（DPI 缩放 + 丢事件都不会偏）。
// ============================================================================

final ffi.DynamicLibrary _user32 = ffi.DynamicLibrary.open('user32.dll');
final ffi.DynamicLibrary _kernel32 = ffi.DynamicLibrary.open('kernel32.dll');

// ---- user32 / kernel32 绑定 -------------------------------------------------

typedef _EnumWindowsProcNative = ffi.Int32 Function(
  ffi.IntPtr hWnd,
  ffi.IntPtr lParam,
);

typedef _EnumWindowsNative = ffi.Int32 Function(
  ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> lpEnumFunc,
  ffi.IntPtr lParam,
);
typedef _EnumWindowsDart = int Function(
  ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> lpEnumFunc,
  int lParam,
);

final _EnumWindowsDart _enumWindows = _user32
    .lookupFunction<_EnumWindowsNative, _EnumWindowsDart>('EnumWindows');

typedef _GetWindowThreadProcessIdNative = ffi.Uint32 Function(
  ffi.IntPtr hWnd,
  ffi.Pointer<ffi.Uint32> lpdwProcessId,
);
typedef _GetWindowThreadProcessIdDart = int Function(
  int hWnd,
  ffi.Pointer<ffi.Uint32> lpdwProcessId,
);

final _GetWindowThreadProcessIdDart _getWindowThreadProcessId = _user32
    .lookupFunction<
      _GetWindowThreadProcessIdNative,
      _GetWindowThreadProcessIdDart
    >('GetWindowThreadProcessId');

typedef _IntPtr2Native = ffi.IntPtr Function(ffi.IntPtr, ffi.Int32);
typedef _IntPtr2Dart = int Function(int, int);
typedef _IntPtr3Native = ffi.IntPtr Function(ffi.IntPtr, ffi.Int32, ffi.IntPtr);
typedef _IntPtr3Dart = int Function(int, int, int);
typedef _Int1Native = ffi.Int32 Function(ffi.IntPtr);
typedef _Int1Dart = int Function(int);
typedef _Int2Native = ffi.Int32 Function(ffi.IntPtr, ffi.Int32);
typedef _Int2Dart = int Function(int, int);

final _Int1Dart _getWindowTextLength = _user32
    .lookupFunction<_Int1Native, _Int1Dart>('GetWindowTextLengthW');
final _Int1Dart _isWindowVisible = _user32
    .lookupFunction<_Int1Native, _Int1Dart>('IsWindowVisible');
final _Int2Dart _showWindow = _user32.lookupFunction<_Int2Native, _Int2Dart>(
  'ShowWindow',
);
final _Int2Dart _getWindowLong = _user32
    .lookupFunction<_IntPtr2Native, _IntPtr2Dart>('GetWindowLongW');
final _IntPtr3Dart _setWindowLong = _user32
    .lookupFunction<_IntPtr3Native, _IntPtr3Dart>('SetWindowLongW');

typedef _GetCurrentProcessIdNative = ffi.Uint32 Function();
typedef _GetCurrentProcessIdDart = int Function();
final _GetCurrentProcessIdDart _getCurrentProcessId = _kernel32
    .lookupFunction<_GetCurrentProcessIdNative, _GetCurrentProcessIdDart>(
      'GetCurrentProcessId',
    );

typedef _GetWindowRectNative = ffi.Int32 Function(
  ffi.IntPtr hWnd,
  ffi.Pointer<_Rect> lpRect,
);
typedef _GetWindowRectDart = int Function(int hWnd, ffi.Pointer<_Rect> lpRect);
final _GetWindowRectDart _getWindowRect = _user32
    .lookupFunction<_GetWindowRectNative, _GetWindowRectDart>('GetWindowRect');

typedef _SetWindowPosNative = ffi.Int32 Function(
  ffi.IntPtr hWnd,
  ffi.IntPtr hWndInsertAfter,
  ffi.Int32 x,
  ffi.Int32 y,
  ffi.Int32 cx,
  ffi.Int32 cy,
  ffi.Uint32 uFlags,
);
typedef _SetWindowPosDart = int Function(
  int hWnd,
  int hWndInsertAfter,
  int x,
  int y,
  int cx,
  int cy,
  int uFlags,
);
final _SetWindowPosDart _setWindowPos = _user32
    .lookupFunction<_SetWindowPosNative, _SetWindowPosDart>('SetWindowPos');

typedef _PostMessageNative = ffi.Int32 Function(
  ffi.IntPtr hWnd,
  ffi.Uint32 msg,
  ffi.IntPtr wParam,
  ffi.IntPtr lParam,
);
typedef _PostMessageDart = int Function(
  int hWnd,
  int msg,
  int wParam,
  int lParam,
);
final _PostMessageDart _postMessage = _user32
    .lookupFunction<_PostMessageNative, _PostMessageDart>('PostMessageW');

typedef _SendMessageTimeoutNative = ffi.IntPtr Function(
  ffi.IntPtr hWnd,
  ffi.Uint32 msg,
  ffi.IntPtr wParam,
  ffi.IntPtr lParam,
  ffi.Uint32 flags,
  ffi.Uint32 timeout,
  ffi.Pointer<ffi.UintPtr> result,
);
typedef _SendMessageTimeoutDart = int Function(
  int hWnd,
  int msg,
  int wParam,
  int lParam,
  int flags,
  int timeout,
  ffi.Pointer<ffi.UintPtr> result,
);
final _SendMessageTimeoutDart _sendMessageTimeout = _user32
    .lookupFunction<_SendMessageTimeoutNative, _SendMessageTimeoutDart>(
      'SendMessageTimeoutW',
    );

// 注意：这里**故意不导出 SetCapture/ReleaseCapture**。
// Flutter 的 Windows embedder 已经在 WM_LBUTTONDOWN 时 SetCapture、
// WM_LBUTTONUP 时 ReleaseCapture（flutter_window.cc，注释写着
// "Capture the pointer in case the user drags outside the client area"）。
// 我们再插一脚只会把它的捕获还回去 —— beta30 实测踩过：
// 拖动开始时 ReleaseCapture，快速反向甩动时窗口纹丝不动。

typedef _GetCursorPosNative = ffi.Int32 Function(ffi.Pointer<_Point> p);
typedef _GetCursorPosDart = int Function(ffi.Pointer<_Point> p);
final _GetCursorPosDart _getCursorPos = _user32
    .lookupFunction<_GetCursorPosNative, _GetCursorPosDart>('GetCursorPos');

typedef _MonitorFromWindowNative = ffi.IntPtr Function(
  ffi.IntPtr hWnd,
  ffi.Uint32 dwFlags,
);
typedef _MonitorFromWindowDart = int Function(int hWnd, int dwFlags);
final _MonitorFromWindowDart _monitorFromWindow = _user32
    .lookupFunction<_MonitorFromWindowNative, _MonitorFromWindowDart>(
      'MonitorFromWindow',
    );

typedef _GetMonitorInfoNative = ffi.Int32 Function(
  ffi.IntPtr hMonitor,
  ffi.Pointer<_MonitorInfo> lpmi,
);
typedef _GetMonitorInfoDart = int Function(
  int hMonitor,
  ffi.Pointer<_MonitorInfo> lpmi,
);
final _GetMonitorInfoDart _getMonitorInfo = _user32
    .lookupFunction<_GetMonitorInfoNative, _GetMonitorInfoDart>(
      'GetMonitorInfoW',
    );

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

final class _Point extends ffi.Struct {
  @ffi.Int32()
  external int x;
  @ffi.Int32()
  external int y;
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
const int _swpShowWindow = 0x0040;

/// 关键：把请求投递给窗口所属线程，本线程立即返回，不会因为对方忙而死等。
const int _swpAsyncWindowPos = 0x4000;

const int _hwndTopMost = -1;
const int _hwndNoTopMost = -2;
const int _swShow = 5;
const int _swMinimize = 6;
const int _wmClose = 0x0010;
const int _wmSetText = 0x000C;
const int _smtoAbortIfHung = 0x0002;
const int _monitorDefaultToNearest = 2;

/// 让系统进入"移动窗口"模态循环的消息（window_manager.startDragging 用的同一套）
const int _wmNcLButtonDown = 0x00A1;
const int _htCaption = 2;

/// 模态循环会一直跑到用户松手；给它一个上限，免得我们这边被无限挂住
const int _nativeDragWaitMs = 30000;

// ---- 顶层窗口枚举 -----------------------------------------------------------

final List<int> _enumResult = <int>[];
int _enumPid = 0;
bool _enumVisibleOnly = true;
bool _enumEmptyTitleOnly = false;

int _enumWindowsProc(int hWnd, int lParam) {
  try {
    _getWindowThreadProcessId(hWnd, _pidScratch);
    if (_pidScratch.value != _enumPid) return 1;
    if (_enumVisibleOnly && _isWindowVisible(hWnd) == 0) return 1;
    if (_enumEmptyTitleOnly && _getWindowTextLength(hWnd) != 0) return 1;
    _enumResult.add(hWnd);
  } catch (_) {
    // 单个窗口读取失败就跳过
  }
  return 1;
}

final ffi.Pointer<ffi.Uint32> _pidScratch = calloc<ffi.Uint32>();
final ffi.Pointer<ffi.NativeFunction<_EnumWindowsProcNative>> _enumProcPtr =
    ffi.Pointer.fromFunction<_EnumWindowsProcNative>(_enumWindowsProc, 0);

/// 列出本进程的所有顶层窗口。
///
/// [visibleOnly]=false 时连隐藏窗口一起列出（子窗口刚创建时是隐藏的）。
/// [emptyTitleOnly]=true 时只列标题为空的窗口（插件创建的窗口标题为空，主窗口有标题）。
List<int> listProcessWindows({
  bool visibleOnly = true,
  bool emptyTitleOnly = false,
}) {
  _enumResult.clear();
  _enumPid = _getCurrentProcessId();
  _enumVisibleOnly = visibleOnly;
  _enumEmptyTitleOnly = emptyTitleOnly;
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
  bool _shown = false;

  int _widthPx = 360;
  int _heightPx = 440;
  String _title = '';

  /// 逻辑像素 → 物理像素的比例（= Flutter 的 devicePixelRatio）。
  double _scale = 1.0;

  // 拖动：窗口原位 + 指针起点（鼠标用屏幕绝对坐标，触摸用"窗口当前位置 + 相对位移"）
  int _dragOriginX = 0;
  int _dragOriginY = 0;
  int _cursorStartX = 0;
  int _cursorStartY = 0;
  double _dragStartX = 0;
  double _dragStartY = 0;
  bool _dragging = false;

  /// 本次拖动是否用 GetCursorPos 的屏幕坐标（鼠标=true，触摸=false）
  bool _useCursor = false;

  /// 系统移动循环不可用只记一次日志，别每次拖动都刷
  bool _systemMoveLogged = false;

  bool get isReady => _hwnd != 0;

  bool get isTopMost => _isTopMost;

  /// 配置并显示窗口。
  ///
  /// [hwnd] 由父窗口通过窗口通道传下来（确定性，不会抢错窗口）。
  /// 传 0 时回退到"本进程 + 标题为空"的自动查找。
  /// [nativeShow] 是拿不到 HWND 时的兜底显示手段（window_show，作用于自己的窗口）。
  /// [scale] 传 devicePixelRatio，拖动时要做逻辑→物理换算。
  void attach({
    required int widthPx,
    required int heightPx,
    required String title,
    int hwnd = 0,
    double scale = 1.0,
    Future<void> Function()? nativeShow,
  }) {
    _widthPx = widthPx;
    _heightPx = heightPx;
    _title = title;
    if (scale > 0) _scale = scale;

    if (hwnd != 0) {
      _take(hwnd);
      if (_hwnd != 0) return;
    }

    // 回退路径：父窗口可能还没把 HWND 推过来
    _attempts = 0;
    _trySearch();
    if (_hwnd == 0) {
      _locateTimer = Timer.periodic(const Duration(milliseconds: 150), (t) {
        _attempts++;
        _trySearch();
        if (_hwnd != 0 || _attempts > 16) {
          t.cancel();
          _locateTimer = null;
          if (_hwnd == 0) {
            AppLog.warn('$tag: 未能识别自身窗口，先用原始样式显示出来');
            if (nativeShow != null) nativeShow();
          }
        }
      });
    }
  }

  void _trySearch() {
    if (_hwnd != 0) return;
    final candidates = listProcessWindows(
      visibleOnly: false,
      emptyTitleOnly: true,
    );
    if (candidates.isEmpty) return;
    _take(candidates.last);
  }

  void _take(int hwnd) {
    final style = _getWindowLong(hwnd, _gwlStyle);
    if ((style & _wsCaption) != 0) {
      final stripped =
          style & ~(_wsCaption | _wsSysMenu | _wsMinimizeBox | _wsMaximizeBox);
      _setWindowLong(hwnd, _gwlStyle, stripped);
      if ((_getWindowLong(hwnd, _gwlStyle) & _wsCaption) != 0) {
        return; // 样式没生效，留给下一轮
      }
    }
    _hwnd = hwnd;
    _applyFrame();
    _setTitle(_title);
    _show();
    AppLog.info('$tag: 已接管窗口 hwnd=$hwnd ${_widthPx}x$_heightPx');
  }

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

  void _applyFrame() {
    if (_hwnd == 0) return;
    final r = _centeredRect(_widthPx, _heightPx);
    _setWindowPos(
      _hwnd,
      0,
      r[0],
      r[1],
      r[2],
      r[3],
      _swpAsyncWindowPos | _swpNoZOrder | _swpFrameChanged | _swpNoActivate,
    );
  }

  /// 显示窗口（创建时是隐藏的，改好样式再显示 → 不会闪 800x600 的原生窗口）。
  void _show() {
    if (_hwnd == 0 || _shown) return;
    _shown = true;
    _showWindow(_hwnd, _swShow);
    _setWindowPos(
      _hwnd,
      0,
      0,
      0,
      0,
      0,
      _swpAsyncWindowPos |
          _swpNoMove |
          _swpNoSize |
          _swpNoZOrder |
          _swpShowWindow,
    );
  }

  void _setTitle(String title) {
    if (_hwnd == 0 || title.isEmpty) return;
    final ptr = title.toNativeUtf16();
    final out = calloc<ffi.UintPtr>();
    try {
      // 对方线程卡住时直接超时返回，绝不把自己的 UI 线程挂死
      _sendMessageTimeout(
        _hwnd,
        _wmSetText,
        0,
        ptr.address,
        _smtoAbortIfHung,
        1000,
        out,
      );
    } finally {
      calloc.free(ptr);
      calloc.free(out);
    }
  }

  /// 开始拖动窗口。[x]/[y] 是 Flutter 给的逻辑坐标（窗口内）。
  ///
  /// 先试一次**系统自己的"移动窗口"模态循环**
  /// （`WM_NCLBUTTONDOWN/HTCAPTION`，和主窗口 `windowManager.startDragging`
  /// 完全同一套消息）。这条消息在 `desktop_multi_window` 的子窗口上实测
  /// **不生效**（消息被处理但模态循环没起来，`SendMessageTimeoutW` 立刻返回，
  /// 具体原因在插件/Flutter 的 WndProc 里，不在我们这层），
  /// 所以真正的实现是下面的逐帧拖动；系统循环留着，别的环境上能用就更好
  /// （它自带贴边/Aero Snap，而且完全在屏幕坐标里跟踪指针）。
  ///
  /// 为什么自己 SetWindowPos 这么难（beta28、beta29 两轮都栽在这）：
  /// Flutter 给的指针坐标是**相对窗口**的。窗口一跟着指针动，指针相对窗口的
  /// 位置就跟着变，"指针走了多少"和"窗口走了多少"搅在一起：
  ///   * 按绝对位置算 → 窗口动 30px 又弹回原位（实测十步只走 60%，来回跳）；
  ///   * 按 delta 累加   → 每步只能拿到一半的位移（实测反向快甩正好 -150/期望 -300）。
  /// 这不是算错，是相对坐标里根本推不出指针的屏幕绝对位置 —— 信息不足。
  /// 所以下面改用 `GetCursorPos` 的屏幕坐标（鼠标）/ 重建坐标（触摸）。
  ///
  /// 鼠标捕获不用我们自己管：Flutter 的 Windows embedder 在 WM_LBUTTONDOWN 时
  /// 已经 `SetCapture`、WM_LBUTTONUP 时 `ReleaseCapture`
  /// （`flutter_window.cc` 里"Capture the pointer in case the user drags outside
  /// the client area"）。自己再调一次反而会把它的捕获还回去（踩过一次）。
  void beginDrag(
    double x,
    double y, [
    PointerDeviceKind kind = PointerDeviceKind.mouse,
  ]) {
    if (_hwnd == 0) return;
    if (_startSystemMove()) {
      _dragging = false;
      return;
    }
    if (!_systemMoveLogged) {
      _systemMoveLogged = true;
      AppLog.info('$tag: 系统移动循环在本窗口上不可用，改用逐帧拖动');
    }
    _beginDartDrag(x, y, kind);
  }

  /// 触发系统移动循环。返回 true 表示真的拖动过。
  bool _startSystemMove() {
    final before = _windowRect();
    final sw = Stopwatch()..start();
    final out = calloc<ffi.UintPtr>();
    try {
      _sendMessageTimeout(
        _hwnd,
        _wmNcLButtonDown,
        _htCaption,
        0,
        _smtoAbortIfHung,
        _nativeDragWaitMs,
        out,
      );
    } catch (e, s) {
      AppLog.error('$tag: 系统窗口拖动失败', e, s);
      return false;
    } finally {
      calloc.free(out);
      sw.stop();
    }
    // 真拖动过：模态循环要跑到松手才回来，耗时远大于几十毫秒
    if (sw.elapsedMilliseconds < 50 && _windowRect() == before) return false;
    return true;
  }

  ({int left, int top})? _windowRect() {
    final rc = calloc<_Rect>();
    try {
      if (_getWindowRect(_hwnd, rc) == 0) return null;
      return (left: rc.ref.left, top: rc.ref.top);
    } finally {
      calloc.free(rc);
    }
  }

  ({int x, int y})? _cursorPos() {
    final pt = calloc<_Point>();
    try {
      if (_getCursorPos(pt) == 0) return null;
      return (x: pt.ref.x, y: pt.ref.y);
    } finally {
      calloc.free(pt);
    }
  }

  void _beginDartDrag(double x, double y, PointerDeviceKind kind) {
    final rc = calloc<_Rect>();
    try {
      if (_getWindowRect(_hwnd, rc) != 0) {
        _dragOriginX = rc.ref.left;
        _dragOriginY = rc.ref.top;
      }
      final cur = _cursorPos();
      if (cur != null) {
        _cursorStartX = cur.x;
        _cursorStartY = cur.y;
      }
      _useCursor = kind == PointerDeviceKind.mouse && cur != null;
      _dragStartX = x;
      _dragStartY = y;
      _dragging = true;
    } finally {
      calloc.free(rc);
    }
  }

  void updateDrag(double x, double y) {
    if (_hwnd == 0 || !_dragging) return;
    final target = SubWindow.dragTarget(
      originX: _dragOriginX,
      originY: _dragOriginY,
      cursorStartX: _cursorStartX,
      cursorStartY: _cursorStartY,
      cursorX: _useCursor ? _cursorPos()?.x : null,
      cursorY: _useCursor ? _cursorPos()?.y : null,
      windowNowX: _windowRect()?.left,
      windowNowY: _windowRect()?.top,
      startX: _dragStartX,
      startY: _dragStartY,
      x: x,
      y: y,
      scale: _scale,
    );
    _setWindowPos(
      _hwnd,
      0,
      target.x,
      target.y,
      0,
      0,
      _swpAsyncWindowPos | _swpNoSize | _swpNoZOrder | _swpNoActivate,
    );
  }

  /// 拖动时的目标窗口位置（纯函数，方便单测）。
  ///
  /// 关键点：**Flutter 给的指针坐标是相对窗口的**。
  /// 窗口一跟着指针动，指针相对窗口的位置就变了 —— 直接用这个坐标算位置，
  /// "指针走了多少"和"窗口走了多少"会互相抵消：实测窗口动 30px 又弹回原位，
  /// 十步只走了 60%；改用 delta 累加每步只剩一半（实测 FAST-BACK 也正好一半）。
  /// 这是信息不足，不是算错。
  ///
  /// 所以鼠标拖动直接读 **GetCursorPos 的屏幕绝对坐标**（[cursorX]/[cursorY]），
  /// 与 Flutter 的坐标语义无关，1:1 跟手。
  ///
  /// 触摸没有光标位置，用**重建**屏幕坐标：窗口当前位置 + 指针相对窗口的位置
  /// （[windowNowX] + ([x] - [startX]) × [scale]）。窗口自己动多少就补回多少，
  /// 反馈被抵消掉，同样 1:1。
  /// 触摸的事件坐标同样是相对窗口的：embedder 收到 `WM_POINTERDOWN/UPDATE`
  /// 之后先 `ScreenToClient`（`flutter_window.cc` 617-618 行），和鼠标那条路一样。
  ///
  /// [scale] 是 devicePixelRatio：Flutter 给的是**逻辑**像素，SetWindowPos 要**物理**像素。
  static ({int x, int y}) dragTarget({
    required int originX,
    required int originY,
    required int cursorStartX,
    required int cursorStartY,
    int? cursorX,
    int? cursorY,
    int? windowNowX,
    int? windowNowY,
    required double startX,
    required double startY,
    required double x,
    required double y,
    required double scale,
  }) {
    if (cursorX != null && cursorY != null) {
      // 鼠标：屏幕绝对坐标做差，最准
      return (
        x: originX + (cursorX - cursorStartX),
        y: originY + (cursorY - cursorStartY),
      );
    }
    // 触摸/触控笔：窗口当前位置 + 相对位移（把窗口自己的位移补回来）
    final dx = ((x - startX) * scale).round();
    final dy = ((y - startY) * scale).round();
    if (windowNowX != null && windowNowY != null) {
      return (x: windowNowX + dx, y: windowNowY + dy);
    }
    return (x: originX + dx, y: originY + dy);
  }

  /// 拖动结束（松手或手势被取消）。
  ///
  /// 不需要还什么系统资源：鼠标捕获是 Flutter embedder 在 WM_LBUTTONUP 时
  /// 自己 ReleaseCapture 的，我们没动过它。
  void endDrag() {
    _dragging = false;
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
    _setWindowPos(
      _hwnd,
      _isTopMost ? _hwndTopMost : _hwndNoTopMost,
      0,
      0,
      0,
      0,
      _swpAsyncWindowPos | _swpNoMove | _swpNoSize | _swpNoActivate,
    );
    return _isTopMost;
  }

  /// 全屏：铺满当前显示器（含任务栏区域），再次调用还原。
  ///
  /// 关键：进入时要把窗口设为 **HWND_TOPMOST**。任务栏本身也是 topmost，
  /// 普通窗口即使铺满 rcMonitor 也会被任务栏压在下面 —— 那就成了"伪全屏"
  /// （看起来跟最大化没区别）。置顶之后才能真正盖住任务栏（B 站全屏就是这效果）。
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
          _hwndTopMost,
          m.left,
          m.top,
          m.right - m.left,
          m.bottom - m.top,
          _swpAsyncWindowPos | _swpFrameChanged | _swpNoActivate,
        );
      } finally {
        calloc.free(mi);
      }
    } else {
      _isFullscreen = false;
      _applyFrame();
      // 退出全屏：恢复 z 序（开了"置顶"就保持置顶，否则还原为普通层级）
      _setWindowPos(
        _hwnd,
        _isTopMost ? _hwndTopMost : _hwndNoTopMost,
        0,
        0,
        0,
        0,
        _swpAsyncWindowPos | _swpNoMove | _swpNoSize | _swpNoActivate,
      );
    }
    return _isFullscreen;
  }

  void dispose() {
    _locateTimer?.cancel();
    _locateTimer = null;
  }
}
