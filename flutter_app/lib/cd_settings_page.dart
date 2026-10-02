import 'package:flutter/material.dart';
import 'api.dart';

/// Countdown Desktop 设置界面（Flutter 重写版）
/// 左侧导航 + 右侧内容区 + 底部保存/取消
class CdSettingsDialog extends StatefulWidget {
  const CdSettingsDialog({super.key});

  @override
  State<CdSettingsDialog> createState() => _CdSettingsDialogState();
}

class _CdSettingsDialogState extends State<CdSettingsDialog> {
  final ApiService _api = ApiService();
  int _selectedPage = 0;
  bool _loading = true;
  String? _error;

  // 配置数据
  Map<String, dynamic> _config = {};
  Map<String, String> _examLabels = {};
  Map<String, String> _fitLabels = {};
  String _cdVersion = '';

  // 编辑控制器
  final _wallUrlCtrl = TextEditingController();
  final _ssUrlCtrl = TextEditingController();

  static const _navItems = [
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

  Future<void> _loadConfig() async {
    try {
      final r = await _api.getCdConfig();
      setState(() {
        _config = Map<String, dynamic>.from(r['config'] ?? {});
        _examLabels = Map<String, String>.from(r['exam_labels'] ?? {});
        _fitLabels = Map<String, String>.from(r['fit_labels'] ?? {});
        _cdVersion = r['cd_version'] ?? '';
        _wallUrlCtrl.text = _config['wallpaper']?['url'] ?? '';
        _ssUrlCtrl.text = _config['screensaver']?['url'] ?? '';
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  bool get _isCustomExam => _config['exam_type'] == 'custom';

  void _setExamType(String value) {
    setState(() {
      _config['exam_type'] = value;
      if (value != 'custom') {
        // 预设模式：URL 跟随预设
        final defaultUrl = value == 'zhongkao'
            ? 'https://zztool.free.nf/countdown-junior'
            : 'https://zztool.free.nf/countdown';
        _wallUrlCtrl.text = defaultUrl;
        _ssUrlCtrl.text = defaultUrl;
        _config['wallpaper']?['url'] = defaultUrl;
        _config['screensaver']?['url'] = defaultUrl;
      }
    });
  }

  Future<void> _save() async {
    try {
      // 同步 URL 输入框到配置
      _config['wallpaper']?['url'] = _wallUrlCtrl.text.trim();
      _config['screensaver']?['url'] = _ssUrlCtrl.text.trim();
      await _api.saveCdConfig(_config);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('设置已保存')),
        );
        Navigator.pop(context, true);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败：$e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
      child: Container(
        width: 680,
        height: 480,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          color: Theme.of(context).colorScheme.surface,
        ),
        child: Column(
          children: [
            // 标题栏
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 12, 8),
              child: Row(
                children: [
                  Text('壁纸&屏保设置', style: Theme.of(context).textTheme.titleLarge),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            // 主体：左侧导航 + 右侧内容
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null
                      ? Center(child: Text('加载失败：$_error'))
                      : Row(
                          children: [
                            _buildNav(),
                            const VerticalDivider(width: 1),
                            Expanded(child: _buildPage()),
                          ],
                        ),
            ),
            // 底部按钮
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('取消'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _loading ? null : _save,
                    child: const Text('保存'),
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
    return Container(
      width: 140,
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: ListView.builder(
        itemCount: _navItems.length,
        itemBuilder: (context, i) {
          final (label, icon) = _navItems[i];
          final selected = i == _selectedPage;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            child: Material(
              color: selected
                  ? Theme.of(context).colorScheme.primaryContainer
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
              child: InkWell(
                borderRadius: BorderRadius.circular(8),
                onTap: () => setState(() => _selectedPage = i),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      Icon(icon, size: 18, color: selected ? Theme.of(context).colorScheme.primary : Colors.grey[600]),
                      const SizedBox(width: 10),
                      Text(label, style: TextStyle(fontSize: 13, fontWeight: selected ? FontWeight.w600 : FontWeight.w400)),
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
        return _buildCountdownPage();
      case 1:
        return _buildWallpaperPage();
      case 2:
        return _buildScreensaverPage();
      case 3:
        return _buildGeneralPage();
      case 4:
        return _buildAboutPage();
      default:
        return const SizedBox.shrink();
    }
  }

  // ========== 倒计时页 ==========
  Widget _buildCountdownPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('倒计时类型', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          ..._examLabels.entries.map((e) => RadioListTile<String>(
                title: Text(e.value),
                value: e.key,
                groupValue: _config['exam_type'] ?? 'gaokao',
                onChanged: (v) => _setExamType(v!),
                dense: true,
              )),
          const SizedBox(height: 8),
          Text(
            _isCustomExam
                ? '自定义：壁纸与屏保可在各自页面分别设置地址。'
                : '高考/中考：壁纸与屏保统一使用对应倒计时页面。',
            style: TextStyle(fontSize: 12, color: Colors.grey[600]),
          ),
        ],
      ),
    );
  }

  // ========== 动态壁纸页 ==========
  Widget _buildWallpaperPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SwitchListTile(
            title: const Text('启用动态壁纸'),
            value: _config['wallpaper']?['enabled'] ?? true,
            onChanged: (v) => setState(() => _config['wallpaper']?['enabled'] = v),
            contentPadding: EdgeInsets.zero,
          ),
          const SizedBox(height: 8),
          Text('壁纸源', style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 6),
          TextField(
            controller: _wallUrlCtrl,
            enabled: _isCustomExam,
            decoration: InputDecoration(
              hintText: _isCustomExam ? '网页地址，或本地 视频/图片/动图 文件' : '跟随倒计时页预设',
              isDense: true,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Text('画幅', style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 6),
          DropdownButtonFormField<String>(
            value: _config['wallpaper']?['fit'] ?? 'cover',
            isDense: true,
            decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true),
            items: _fitLabels.entries
                .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                .toList(),
            onChanged: (v) => setState(() => _config['wallpaper']?['fit'] = v),
          ),
          const SizedBox(height: 12),
          SwitchListTile(
            title: const Text('静音（网页与视频）'),
            value: _config['wallpaper']?['mute'] ?? true,
            onChanged: (v) => setState(() => _config['wallpaper']?['mute'] = v),
            contentPadding: EdgeInsets.zero,
          ),
        ],
      ),
    );
  }

  // ========== 屏幕保护页 ==========
  Widget _buildScreensaverPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SwitchListTile(
              title: const Text('启用屏保（自绘全屏窗口）'),
              value: _config['screensaver']?['enabled'] ?? true,
              onChanged: (v) => setState(() => _config['screensaver']?['enabled'] = v),
              contentPadding: EdgeInsets.zero,
            ),
            const SizedBox(height: 8),
            Text('屏保源', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 6),
            TextField(
              controller: _ssUrlCtrl,
              enabled: _isCustomExam,
              decoration: InputDecoration(
                hintText: _isCustomExam ? '网页地址，或本地 视频/图片/动图 文件' : '跟随倒计时页预设',
                isDense: true,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Text('空闲触发时长（秒）', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: Slider(
                    value: (_config['screensaver']?['timeout'] ?? 600).toDouble(),
                    min: 30,
                    max: 3600,
                    divisions: 119,
                    label: '${_config['screensaver']?['timeout'] ?? 600}秒',
                    onChanged: (v) => setState(() => _config['screensaver']?['timeout'] = v.round()),
                  ),
                ),
                SizedBox(
                  width: 60,
                  child: Text('${_config['screensaver']?['timeout'] ?? 600}秒', textAlign: TextAlign.right),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text('画幅', style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 6),
            DropdownButtonFormField<String>(
              value: _config['screensaver']?['fit'] ?? 'cover',
              isDense: true,
              decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true),
              items: _fitLabels.entries
                  .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                  .toList(),
              onChanged: (v) => setState(() => _config['screensaver']?['fit'] = v),
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              title: const Text('静音（网页与视频）'),
              value: _config['screensaver']?['mute'] ?? true,
              onChanged: (v) => setState(() => _config['screensaver']?['mute'] = v),
              contentPadding: EdgeInsets.zero,
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              icon: const Icon(Icons.play_circle_outline, size: 18),
              label: const Text('立即测试屏保'),
              onPressed: () => _api.testCdScreensaver(),
            ),
          ],
        ),
      ),
    );
  }

  // ========== 通用页 ==========
  Widget _buildGeneralPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('通用', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          SwitchListTile(
            title: const Text('开机自启'),
            subtitle: const Text('写入注册表 HKCU，卸载自动清理'),
            value: _config['run_at_startup'] ?? false,
            onChanged: (v) => setState(() => _config['run_at_startup'] = v),
            contentPadding: EdgeInsets.zero,
          ),
          const SizedBox(height: 8),
          Text('播放', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          SwitchListTile(
            title: const Text('视频循环播放'),
            subtitle: const Text('壁纸与屏保均生效'),
            value: _config['playback']?['video_loop'] ?? true,
            onChanged: (v) => setState(() => _config['playback']?['video_loop'] = v),
            contentPadding: EdgeInsets.zero,
          ),
        ],
      ),
    );
  }

  // ========== 关于页 ==========
  Widget _buildAboutPage() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('关于', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 16),
          _aboutRow('程序', 'Countdown Desktop（傻瓜启动器特供版）'),
          _aboutRow('版本', 'v$_cdVersion'),
          _aboutRow('功能', '动态壁纸 + 屏幕保护（网页/视频/图片/动图）'),
          _aboutRow('渲染', 'pywebview + WebView2（Chromium）'),
          _aboutRow('更新', '已由傻瓜启动器统一管理'),
          const SizedBox(height: 20),
          Text('开源许可与鸣谢', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(
            '本软件基于 GPL-3.0 授权开源。壁纸嵌入实现学习并借鉴了 Lively Wallpaper（GPL-3.0），在此向作者 rocksdanister 及社区贡献者致谢。',
            style: TextStyle(fontSize: 12, color: Colors.grey[600], height: 1.5),
          ),
        ],
      ),
    );
  }

  Widget _aboutRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 60, child: Text(label, style: TextStyle(color: Colors.grey[600], fontSize: 13))),
          Expanded(child: Text(value, style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}
