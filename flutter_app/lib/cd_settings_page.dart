import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import 'api.dart';
import 'app_log.dart';

/// 壁纸 & 屏保设置（Flutter 版）。
///
/// 注意：这里改的是 countdown_app 的 config.json。如果壁纸正在运行，
/// 改动要等壁纸重启后才生效，保存后会明确提示用户。
class CdSettingsDialog extends StatefulWidget {
  const CdSettingsDialog({super.key});

  @override
  State<CdSettingsDialog> createState() => _CdSettingsDialogState();
}

class _CdSettingsDialogState extends State<CdSettingsDialog> {
  final ApiService _api = ApiService();
  int _selectedPage = 0;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  Map<String, dynamic> _config = <String, dynamic>{};
  Map<String, String> _examLabels = <String, String>{};
  Map<String, String> _fitLabels = <String, String>{};
  String _cdVersion = '';
  String _defaultUrl = '';
  bool _running = false;

  final TextEditingController _wallUrlCtrl = TextEditingController();
  final TextEditingController _ssUrlCtrl = TextEditingController();

  static const List<(String, IconData)> _navItems = <(String, IconData)>[
    ('倒计时', Icons.timer_outlined),
    ('动态壁纸', Icons.wallpaper_outlined),
    ('屏幕保护', Icons.screen_lock_portrait_outlined),
    ('通用', Icons.settings_outlined),
    ('关于', Icons.info_outline),
  ];

  @override
  void initState() {
    super.initState();
    _loadConfig();
  }

  @override
  void dispose() {
    _wallUrlCtrl.dispose();
    _ssUrlCtrl.dispose();
    super.dispose();
  }

  // ---- 读取配置时的兜底：任何一段缺失都补上默认值，避免显示 (null) ----
  Map<String, dynamic> _section(String key) {
    final v = _config[key];
    if (v is Map) {
      final m = v.cast<String, dynamic>();
      _config[key] = m;
      return m;
    }
    final created = <String, dynamic>{};
    _config[key] = created;
    return created;
  }

  Future<void> _loadConfig() async {
    try {
      final r = await _api.getCdConfig();
      final cfg = Map<String, dynamic>.from(
          (r['config'] as Map?)?.cast<String, dynamic>() ?? <String, dynamic>{});
      setState(() {
        _config = cfg;
        _examLabels = Map<String, String>.from(
            (r['exam_labels'] as Map?)?.cast<String, String>() ?? <String, String>{});
        _fitLabels = Map<String, String>.from(
            (r['fit_labels'] as Map?)?.cast<String, String>() ?? <String, String>{});
        _cdVersion = ApiService.asString(r['cd_version']);
        _defaultUrl = ApiService.asString(r['default_url']);
        _running = ApiService.asBool(r['running']);
        _wallUrlCtrl.text = ApiService.asString(_section('wallpaper')['url']);
        _ssUrlCtrl.text = ApiService.asString(_section('screensaver')['url']);
        _loading = false;
      });
    } catch (e, s) {
      AppLog.error('读取壁纸配置失败', e, s);
      setState(() {
        _error = '读取设置失败：$e';
        _loading = false;
      });
    }
  }

  bool get _isCustomExam => ApiService.asString(_config['exam_type']) == 'custom';

  void _setExamType(String value) {
    setState(() {
      _config['exam_type'] = value;
      if (value == 'custom') return;
      // 预设模式：地址跟随预设（用后端返回的默认地址，不在这里硬编码）
      final preset = _defaultUrl.isNotEmpty ? _defaultUrl : _wallUrlCtrl.text;
      final url = value == 'zhongkao'
          ? (preset.contains('countdown')
              ? preset.replaceFirst(RegExp(r'countdown[^/]*$'), 'countdown-junior')
              : preset)
          : preset;
      _wallUrlCtrl.text = url;
      _ssUrlCtrl.text = url;
      _section('wallpaper')['url'] = url;
      _section('screensaver')['url'] = url;
    });
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      _section('wallpaper')['url'] = _wallUrlCtrl.text.trim();
      _section('screensaver')['url'] = _ssUrlCtrl.text.trim();
      final r = await _api.saveCdConfig(_config);
      if (!mounted) return;
      if (!ApiService.asBool(r['success'])) {
        _showSnack('保存失败：${ApiService.asString(r['error'])}', error: true);
        return;
      }
      final needRestart = ApiService.asBool(r['restart_required']);
      Navigator.pop(context, true);
      // 提示放在主界面（弹窗已经关了）
      final messenger = ScaffoldMessenger.maybeOf(context);
      messenger?.showSnackBar(SnackBar(
        content: Text(needRestart
            ? '设置已保存。壁纸正在运行，重新启动壁纸后生效。'
            : '设置已保存'),
      ));
    } catch (e, s) {
      AppLog.error('保存壁纸配置失败', e, s);
      if (mounted) _showSnack('保存失败：$e', error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _showSnack(String msg, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Theme.of(context).colorScheme.error : null,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final width = (size.width - 60).clamp(320.0, 720.0);
    final height = (size.height - 80).clamp(320.0, 560.0);
    return Dialog(
      insetPadding: const EdgeInsets.all(20),
      child: SizedBox(
        width: width,
        height: height,
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 14, 10, 10),
              child: Row(
                children: <Widget>[
                  Text('壁纸 & 屏保设置',
                      style: Theme.of(context).textTheme.titleLarge),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.close, size: 22),
                    tooltip: '关闭',
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Text(_error!, textAlign: TextAlign.center),
                          ),
                        )
                      : Row(
                          children: <Widget>[
                            _buildNav(),
                            const VerticalDivider(width: 1),
                            Expanded(child: _buildPage()),
                          ],
                        ),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                children: <Widget>[
                  if (_running)
                    Expanded(
                      child: Text('壁纸正在运行：部分设置需要重新启动壁纸后生效',
                          style: TextStyle(
                              fontSize: 13,
                              color: Theme.of(context).colorScheme.onSurfaceVariant)),
                    )
                  else
                    const Spacer(),
                  TextButton(
                    onPressed: _saving ? null : () => Navigator.pop(context),
                    child: const Text('取消'),
                  ),
                  const SizedBox(width: 10),
                  FilledButton(
                    onPressed: (_loading || _saving) ? null : _save,
                    child: _saving
                        ? const SizedBox(
                            width: 20, height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Text('保存'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNav() {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: 150,
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: ListView.builder(
        itemCount: _navItems.length,
        itemBuilder: (context, i) {
          final (label, icon) = _navItems[i];
          final selected = i == _selectedPage;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            child: Material(
              color: selected ? scheme.primaryContainer : Colors.transparent,
              borderRadius: BorderRadius.circular(10),
              child: InkWell(
                borderRadius: BorderRadius.circular(10),
                onTap: () => setState(() => _selectedPage = i),
                child: Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                  child: Row(
                    children: <Widget>[
                      Icon(icon,
                          size: 20,
                          color: selected ? scheme.primary : scheme.onSurfaceVariant),
                      const SizedBox(width: 10),
                      Text(label,
                          style: TextStyle(
                              fontSize: 15,
                              // 颜色必须显式写：浅色/深色主题下都能看清
                              color: selected
                                  ? scheme.onPrimaryContainer
                                  : scheme.onSurface,
                              fontWeight:
                                  selected ? FontWeight.w600 : FontWeight.w400)),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildPage() {
    switch (_selectedPage) {
      case 0:
        return _page(_buildCountdownPage());
      case 1:
        return _page(_buildWallpaperPage());
      case 2:
        return _page(_buildScreensaverPage());
      case 3:
        return _page(_buildGeneralPage());
      default:
        return _page(_buildAboutPage());
    }
  }

  Widget _page(Widget child) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: child,
      );

  // ---------- 倒计时 ----------
  Widget _buildCountdownPage() {
    final examType = ApiService.asString(_config['exam_type']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text('倒计时类型', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        RadioGroup<String>(
          groupValue: examType,
          onChanged: (v) {
            if (v != null) _setExamType(v);
          },
          child: Column(
            children: _examLabels.entries
                .map((e) => RadioListTile<String>(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(e.value, style: const TextStyle(fontSize: 16)),
                      value: e.key,
                    ))
                .toList(),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _isCustomExam
              ? '自定义：壁纸与屏保可以在各自页面分别设置地址。'
              : '高考 / 中考：壁纸与屏保统一使用对应倒计时页面。',
          style: TextStyle(
              fontSize: 14,
              height: 1.6,
              color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      ],
    );
  }

  // ---------- 动态壁纸 ----------
  Widget _buildWallpaperPage() {
    final wall = _section('wallpaper');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('启用动态壁纸'),
          value: wall['enabled'] != false,
          onChanged: (v) => setState(() => wall['enabled'] = v),
        ),
        const SizedBox(height: 8),
        const Text('壁纸源'),
        const SizedBox(height: 6),
        _mediaSourceField(
          controller: _wallUrlCtrl,
          enabled: _isCustomExam,
          hint: _isCustomExam
              ? '网页地址，或点"浏览…"选本地 视频/图片/动图 文件'
              : '跟随倒计时页预设（切换类型即可修改）',
        ),
        const SizedBox(height: 14),
        const Text('画幅'),
        const SizedBox(height: 6),
        DropdownButtonFormField<String>(
          initialValue: ApiService.asString(wall['fit']).isEmpty
              ? 'cover'
              : ApiService.asString(wall['fit']),
          isDense: true,
          decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true),
          items: _fitLabels.entries
              .map((e) => DropdownMenuItem<String>(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: (v) => setState(() => wall['fit'] = v),
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('静音（网页与视频）'),
          value: wall['mute'] != false,
          onChanged: (v) => setState(() => wall['mute'] = v),
        ),
      ],
    );
  }

  // ---------- 屏幕保护 ----------
  Widget _buildScreensaverPage() {
    final ss = _section('screensaver');
    final timeout = ApiService.asInt(ss['timeout']) == 0 ? 600 : ApiService.asInt(ss['timeout']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('启用屏保'),
          value: ss['enabled'] != false,
          onChanged: (v) => setState(() => ss['enabled'] = v),
        ),
        const SizedBox(height: 8),
        const Text('屏保源'),
        const SizedBox(height: 6),
        _mediaSourceField(
          controller: _ssUrlCtrl,
          enabled: _isCustomExam,
          hint: _isCustomExam
              ? '网页地址，或点"浏览…"选本地 视频/图片/动图 文件'
              : '跟随倒计时页预设',
        ),
        const SizedBox(height: 14),
        Text('空闲 $timeout 秒后启动屏保'),
        Slider(
          value: timeout.toDouble().clamp(30, 3600),
          min: 30,
          max: 3600,
          divisions: 119,
          label: '$timeout 秒',
          onChanged: (v) => setState(() => ss['timeout'] = v.round()),
        ),
        const SizedBox(height: 6),
        const Text('画幅'),
        const SizedBox(height: 6),
        DropdownButtonFormField<String>(
          initialValue: ApiService.asString(ss['fit']).isEmpty
              ? 'cover'
              : ApiService.asString(ss['fit']),
          isDense: true,
          decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true),
          items: _fitLabels.entries
              .map((e) => DropdownMenuItem<String>(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: (v) => setState(() => ss['fit'] = v),
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('静音（网页与视频）'),
          value: ss['mute'] != false,
          onChanged: (v) => setState(() => ss['mute'] = v),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          icon: const Icon(Icons.play_circle_outline, size: 20),
          label: const Text('立即测试屏保'),
          onPressed: () async {
            if (ss['enabled'] == false) {
              _showSnack('请先勾选「启用屏保」再测试', error: true);
              return;
            }
            try {
              await _api.testCdScreensaver();
              _showSnack('屏保已启动，动一下鼠标或按键盘即可退出');
            } catch (e) {
              _showSnack('测试屏保失败：$e', error: true);
            }
          },
        ),
      ],
    );
  }

  // ---------- 通用 ----------
  Widget _buildGeneralPage() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('开机自动启动壁纸'),
          subtitle: const Text('写入当前用户注册表，卸载时会自动清理'),
          value: _config['run_at_startup'] == true,
          onChanged: (v) => setState(() => _config['run_at_startup'] = v),
        ),
        const Divider(),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('视频循环播放'),
          subtitle: const Text('壁纸与屏保均生效'),
          value: _section('playback')['video_loop'] != false,
          onChanged: (v) => setState(() => _section('playback')['video_loop'] = v),
        ),
      ],
    );
  }

  // ---------- 关于 ----------
  Widget _buildAboutPage() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text('Countdown Desktop（傻瓜启动器特供版）',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        _aboutRow('版本', 'v$_cdVersion'),
        _aboutRow('功能', '动态壁纸 + 屏幕保护（网页/视频/图片/动图）'),
        _aboutRow('渲染', 'pywebview + WebView2（Chromium）'),
        _aboutRow('更新', '由傻瓜启动器统一管理，在首页横幅一键更新'),
        const SizedBox(height: 18),
        Text('开源许可与鸣谢',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(
          '本软件基于 GPL-3.0 授权开源。壁纸嵌入实现学习并借鉴了 '
          'Lively Wallpaper（GPL-3.0），在此向作者 rocksdanister 及社区贡献者致谢。',
          style: TextStyle(
              fontSize: 13, height: 1.7,
              color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      ],
    );
  }

  // ---------- 本地文件选择（系统文件选择窗口） ----------
  //
  // Qt 版设置里就有"浏览…"按钮（QFileDialog），Flutter 版一直没有，
  // 用户只能手打路径。这里用 file_selector（官方插件，调的是系统原生对话框），
  // 选出来的路径直接填进输入框；后端 media.resolve() 认本地文件路径，
  // 会自己起 127.0.0.1 的临时服务喂给 WebView2。

  static const List<String> _mediaExtensions = <String>[
    'mp4', 'webm', 'mkv', 'mov', 'm4v', 'ogv',
    'gif', 'png', 'jpg', 'jpeg', 'bmp', 'webp', 'svg', 'ico',
  ];

  Future<void> _pickMediaFile(TextEditingController controller) async {
    try {
      final XFile? file = await openFile(
        confirmButtonText: '选择',
        acceptedTypeGroups: <XTypeGroup>[
          XTypeGroup(label: '视频/图片/动图', extensions: _mediaExtensions),
          XTypeGroup(label: '视频', extensions: <String>[
            'mp4', 'webm', 'mkv', 'mov', 'm4v', 'ogv',
          ]),
          XTypeGroup(label: '图片/动图', extensions: <String>[
            'gif', 'png', 'jpg', 'jpeg', 'bmp', 'webp', 'svg', 'ico',
          ]),
          XTypeGroup(label: '全部文件'),
        ],
      );
      if (file == null || file.path.isEmpty) return;
      if (!mounted) return;
      final wasPreset = !_isCustomExam;
      setState(() {
        controller.text = file.path;
        // 选了本地文件就必须走"自定义"：中/高考预设会把地址覆盖回预设页面，
        // 不切的话用户会发现"选了文件但壁纸没变"。
        _config['exam_type'] = 'custom';
        _section('wallpaper')['url'] = _wallUrlCtrl.text.trim();
        _section('screensaver')['url'] = _ssUrlCtrl.text.trim();
      });
      _showSnack(wasPreset
          ? '已选好文件，倒计时类型自动切到「自定义」才会用它（记得点保存）'
          : '已选好文件（记得点保存）');
    } catch (e, s) {
      AppLog.error('打开文件选择窗口失败', e, s);
      if (mounted) _showSnack('打不开文件选择窗口：$e', error: true);
    }
  }

  /// 壁纸/屏保源输入框 + "浏览…"按钮。
  Widget _mediaSourceField({
    required TextEditingController controller,
    required String hint,
    required bool enabled,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: <Widget>[
        Expanded(
          child: TextField(
            controller: controller,
            enabled: enabled,
            // 只为刷新"清空"按钮的显示状态
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              isDense: true,
              border: const OutlineInputBorder(),
              hintText: hint,
              suffixIcon: controller.text.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.clear, size: 18),
                      tooltip: '清空',
                      onPressed: enabled
                          ? () => setState(() => controller.clear())
                          : null,
                    ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          height: 46,
          child: OutlinedButton.icon(
            // 故意不跟随 enabled：预设模式下也允许"选个文件"，
            // 选完自动切到自定义（否则按钮会是灰的，用户以为没做这个功能）。
            onPressed: () => _pickMediaFile(controller),
            icon: const Icon(Icons.folder_open, size: 18),
            label: const Text('浏览…'),
            style: OutlinedButton.styleFrom(
              foregroundColor: scheme.onSurface,
              padding: const EdgeInsets.symmetric(horizontal: 12),
            ),
          ),
        ),
      ],
    );
  }

  Widget _aboutRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 64,
            child: Text(label,
                style: TextStyle(
                    fontSize: 14,
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ),
          Expanded(
              child: Text(value,
                  style: TextStyle(
                      fontSize: 14,
                      color: Theme.of(context).colorScheme.onSurface))),
        ],
      ),
    );
  }
}
