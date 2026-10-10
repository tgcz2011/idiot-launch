import 'dart:ffi' as ffi;

import 'package:ffi/ffi.dart';

// ============================================================================
// 全屏计时/秒表 → 临时压住 countdown 的屏保
//
// countdown（另一个进程）会在系统空闲达到阈值时弹出全屏屏保。老师正拿计时/
// 秒表全屏展示时，屏保糊上来就尴尬了。这里用一个**命名互斥量**做跨进程信号：
//   * 进入全屏：创建并**持有** IdiotLaunch_ToolFullscreen 句柄；
//   * 退出全屏 / 窗口关闭 / 进程崩溃：句柄被关闭（崩溃时由系统回收），
//     对象随之消失，countdown 那边就"看不见"它了 → 屏保恢复正常。
// countdown 侧只需 OpenMutexW 一下：能打开 = 有工具正在全屏 = 别弹屏保。
// 壁纸不受影响（它不是屏保）。
// ============================================================================

final ffi.DynamicLibrary _kernel32 = ffi.DynamicLibrary.open('kernel32.dll');

typedef _CreateMutexWNative = ffi.IntPtr Function(
  ffi.Pointer<ffi.Void>,
  ffi.Int32,
  ffi.Pointer<ffi.Uint16>,
);
typedef _CreateMutexWDart = int Function(
  ffi.Pointer<ffi.Void>,
  int,
  ffi.Pointer<ffi.Uint16>,
);
final _CreateMutexWDart _createMutexW = _kernel32
    .lookupFunction<_CreateMutexWNative, _CreateMutexWDart>('CreateMutexW');

typedef _CloseHandleNative = ffi.Int32 Function(ffi.IntPtr);
typedef _CloseHandleDart = int Function(int);
final _CloseHandleDart _closeHandle = _kernel32
    .lookupFunction<_CloseHandleNative, _CloseHandleDart>('CloseHandle');

class ToolFullscreenGuard {
  ToolFullscreenGuard._();

  static const String _name = 'IdiotLaunch_ToolFullscreen';
  static int _handle = 0;

  /// 进入全屏时调用（幂等）。
  static void acquire() {
    if (_handle != 0) return;
    final ptr = _name.toNativeUtf16();
    try {
      _handle = _createMutexW(ffi.nullptr, 0, ptr.cast<ffi.Uint16>());
    } catch (_) {
      _handle = 0;
    } finally {
      malloc.free(ptr);
    }
  }

  /// 退出全屏 / 窗口销毁时调用（幂等）。
  static void release() {
    if (_handle == 0) return;
    try {
      _closeHandle(_handle);
    } catch (_) {}
    _handle = 0;
  }
}
