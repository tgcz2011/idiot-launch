import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:window_manager/window_manager.dart';
import 'package:audioplayers/audioplayers.dart';

// ==================== 倒计时页面 ====================
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
      appBar: AppBar(
        title: const Text('倒计时'),
        actions: [
          IconButton(
            icon: const Icon(Icons.fullscreen),
            tooltip: '全屏',
            onPressed: _toggleFullscreen,
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: selecting ? _buildPicker() : _buildDisplay(),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 32),
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
                            horizontal: 32, vertical: 14)),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause),
                    label: const Text('暂停'),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 32, vertical: 14)),
                  ),
                const SizedBox(width: 16),
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
      appBar: AppBar(
        title: const Text('秒表'),
        actions: [
          IconButton(
            icon: const Icon(Icons.fullscreen),
            tooltip: '全屏',
            onPressed: _toggleFullscreen,
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 32),
            child: Text(
              _fmt(_elapsed),
              style: const TextStyle(
                fontSize: 64,
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
            padding: const EdgeInsets.only(bottom: 32),
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
                            horizontal: 32, vertical: 14)),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause),
                    label: const Text('暂停'),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 32, vertical: 14)),
                  ),
                const SizedBox(width: 16),
                if (_running)
                  TextButton.icon(
                    onPressed: _lap,
                    icon: const Icon(Icons.flag),
                    label: const Text('记次'),
                  ),
                const SizedBox(width: 16),
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
}
