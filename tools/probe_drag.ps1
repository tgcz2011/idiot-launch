# 真机验证"窗口拖动跟不跟手"（Windows，需要先 flutter build windows --debug）。
#
# 为什么要这个脚本：Flutter 给的指针坐标是**相对窗口**的，窗口一跟手移动，
# 指针相对窗口的位置就跟着变 —— 只看代码/单测很容易想当然。
# beta28、beta29 两轮都是"看着像修好了"，真机一跑才发现窗口只走了一半、
# 或者动 30px 又弹回原位。这个脚本用真实的子窗口 + 真实的鼠标消息量误差。
#
#   pwsh -File tools\probe_drag.ps1                 # 默认测倒计时窗口
#   pwsh -File tools\probe_drag.ps1 -Auto stopwatch
#
# 通过标准：每步 off 在几个像素内，END moved 与 expected 一致
# （反向 FAST-BACK 也不能少走，那一趟专门测事件合并）。
#
# 注意：pwsh 是 DPI-unaware 进程，截图是物理像素，GetWindowRect/SetCursorPos
# 是虚拟化坐标，两者差一个系统缩放比例（125% 时差 1.25 倍），别拿截图量。

param(
  [string]$Exe = '',
  [string]$Auto = 'timer',
  [int]$Steps = 10,
  [int]$StepPx = 30
)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

if (-not $Exe) {
  $root = Split-Path -Parent $PSScriptRoot
  $Exe = Join-Path $root 'flutter_app\build\windows\x64\runner\Debug\IdiotLaunch.exe'
}
if (-not (Test-Path $Exe)) {
  Write-Host "exe not found: $Exe (run: flutter build windows --debug)"
  exit 1
}

Add-Type -Namespace W -Name Api -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
[DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int x, y; }
public delegate bool EnumProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);

public class Win {
  public IntPtr H; public bool Visible; public int TitleLen; public string Cls;
  public int Left; public int Top; public int W; public int H2;
  public override string ToString() {
    return string.Format("hwnd={0} visible={1} titleLen={2} cls={3} rect=({4},{5}) {6}x{7}",
      H, Visible, TitleLen, Cls, Left, Top, W, H2);
  }
}

public static System.Collections.Generic.List<Win> WindowsOf(int pid) {
  var list = new System.Collections.Generic.List<Win>();
  EnumWindows(delegate(IntPtr h, IntPtr l) {
    uint p; GetWindowThreadProcessId(h, out p);
    if (p != (uint)pid) return true;
    RECT r; GetWindowRect(h, out r);
    var sb = new System.Text.StringBuilder(256); GetClassName(h, sb, 256);
    list.Add(new Win { H = h, Visible = IsWindowVisible(h), TitleLen = GetWindowTextLength(h),
      Cls = sb.ToString(), Left = r.Left, Top = r.Top, W = r.Right - r.Left, H2 = r.Bottom - r.Top });
    return true;
  }, IntPtr.Zero);
  return list;
}

public static Win RectOf(IntPtr h) {
  RECT r; GetWindowRect(h, out r);
  return new Win { H = h, Left = r.Left, Top = r.Top, W = r.Right - r.Left, H2 = r.Bottom - r.Top };
}

/// 光标下面到底是哪个窗口 —— 拖动没反应时先看这个（多半是被别的窗口挡着）
public static IntPtr UnderCursor(int x, int y) {
  POINT p; p.x = x; p.y = y;
  return WindowFromPoint(p);
}

public static string Describe(IntPtr h) {
  RECT r; GetWindowRect(h, out r);
  var sb = new System.Text.StringBuilder(256); GetClassName(h, sb, 256);
  uint pid; GetWindowThreadProcessId(h, out pid);
  return string.Format("hwnd={0} cls={1} pid={2} rect=({3},{4}) {5}x{6}",
    h, sb.ToString(), pid, r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top);
}

public static void Down(int x, int y) {
  SetCursorPos(x, y); System.Threading.Thread.Sleep(200);
  mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero); System.Threading.Thread.Sleep(150);
}
public static void MoveTo(int x, int y) { SetCursorPos(x, y); System.Threading.Thread.Sleep(90); }
public static void MoveFast(int x, int y) { SetCursorPos(x, y); System.Threading.Thread.Sleep(12); }
public static void Up(int x, int y) {
  SetCursorPos(x, y); System.Threading.Thread.Sleep(80);
  mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero); System.Threading.Thread.Sleep(250);
}
'@

Get-Process IdiotLaunch -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
# 应用里的开发钩子：启动 3 秒后自动打开工具窗口（手动点脚本做不到）
$env:IDIOT_LAUNCH_AUTO_WINDOW = $Auto
$p = Start-Process -FilePath $Exe -PassThru
Write-Host "started pid=$($p.Id) auto=$Auto"

$child = $null
for ($t = 0; $t -lt 45; $t++) {
  Start-Sleep -Seconds 1
  $wins = [W.Api]::WindowsOf($p.Id)
  $child = $wins | Where-Object { $_.Visible -and $_.W -lt 620 -and $_.H2 -lt 760 -and $_.W -gt 150 } |
    Select-Object -First 1
  if ($child) { Write-Host "child found after $t s"; break }
}
if (-not $child) {
  Write-Host "NO CHILD WINDOW - check D:\IdiotLaunch\data\ui.log for the create line"
  [W.Api]::WindowsOf($p.Id) | ForEach-Object { Write-Host "  $_" }
  exit 1
}
Write-Host "child: $child"
# 抬到最前：主窗口挡着的话鼠标事件全被主窗口吃掉，测出来是"窗口没动"
[void][W.Api]::SetWindowPos($child.H, [IntPtr]::Zero, 0, 0, 0, 0, 0x0001 -bor 0x0002 -bor 0x0010)
Start-Sleep -Milliseconds 600
$child = [W.Api]::RectOf($child.H)
Write-Host "child raised: $child"

$grabX = $child.Left + 120
$grabY = $child.Top + 22
Write-Host "grab at ($grabX,$grabY)"
Write-Host "  under cursor: $([W.Api]::Describe([W.Api]::UnderCursor($grabX,$grabY)))  <- must be the child window"
[W.Api]::Down($grabX, $grabY)
$start = [W.Api]::RectOf($child.H)
Write-Host "start rect = ($($start.Left),$($start.Top))"

$bad = 0
for ($i = 1; $i -le $Steps; $i++) {
  $cx = $grabX + $i * $StepPx
  $cy = $grabY + [int]($i * $StepPx / 3)
  [W.Api]::MoveTo($cx, $cy)
  $r = [W.Api]::RectOf($child.H)
  $expX = $start.Left + $i * $StepPx
  $expY = $start.Top + [int]($i * $StepPx / 3)
  $dx = $r.Left - $expX
  $dy = $r.Top - $expY
  if ([math]::Abs($dx) -gt 6 -or [math]::Abs($dy) -gt 6) { $bad++ }
  Write-Host ("step {0,2}: cursor=({1},{2}) win=({3},{4}) expect=({5},{6}) off=({7},{8})" -f `
      $i, $cx, $cy, $r.Left, $r.Top, $expX, $expY, $dx, $dy)
}
[W.Api]::Up($grabX + $Steps * $StepPx, $grabY + [int]($Steps * $StepPx / 3))
$end = [W.Api]::RectOf($child.H)
Write-Host "END moved=($($end.Left - $start.Left),$($end.Top - $start.Top)) expected=($($Steps * $StepPx),$([int]($Steps * $StepPx / 3)))"
Write-Host "steps off by >6px: $bad / $Steps"

# 反向快速甩一趟：事件会被合并，delta 累加的写法在这条路上会少走一半
$g2x = $end.Left + 120
$g2y = $end.Top + 22
# 松手之后先停一下再按：太快的"点一下再拖"会撞上系统的双击判定，
# 而且此时窗口可能已经不是最前面的了 —— 两种情况都会让第二次拖动毫无反应，
# 那是测试脚本的问题，不是被测量的拖动逻辑的问题。
Start-Sleep -Milliseconds 700
[void][W.Api]::SetWindowPos($child.H, [IntPtr]::Zero, 0, 0, 0, 0, 0x0001 -bor 0x0002 -bor 0x0010)
Start-Sleep -Milliseconds 300
Write-Host "fast-back grab at ($g2x,$g2y)"
Write-Host "  under cursor: $([W.Api]::Describe([W.Api]::UnderCursor($g2x,$g2y)))  <- must be the child window"
[W.Api]::Down($g2x, $g2y)
$s2 = [W.Api]::RectOf($child.H)
for ($i = 1; $i -le $Steps; $i++) { [W.Api]::MoveFast($g2x - $i * $StepPx, $g2y) }
[W.Api]::Up($g2x - $Steps * $StepPx, $g2y)
Start-Sleep -Milliseconds 500
$e2 = [W.Api]::RectOf($child.H)
Write-Host "FAST-BACK moved=($($e2.Left - $s2.Left),$($e2.Top - $s2.Top)) expected=($(-$Steps * $StepPx),0)"

Get-Process -Id $p.Id -ErrorAction SilentlyContinue | Stop-Process -Force
if ($bad -eq 0) { Write-Host "OK" } else { Write-Host "FAIL" }
