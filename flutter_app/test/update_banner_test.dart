import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/update_banner.dart';

/// 回归：横幅绝不能把"没查成"说成"已是最新"。
///
/// 真实事故（beta29 装机版）：Supabase 查询因为 Accept 头被判 406、
/// GitHub 兜底又用着构建时塞进去的临时 token（早失效），更新检查
/// 静默失败，界面却一直显示"当前已是最新版本 v3.0.0.0-beta29"。
UpdateBannerCopy _copy({
  bool ready = false,
  bool downloading = false,
  double progress = 0,
  String pending = '',
  String dlVersion = '',
  String latest = '',
  String downloadStatus = '',
  bool checking = false,
  String current = '3.0.0.0-beta29',
  bool? checkOk = true,
  String checkDetail = '',
  String lastCheckText = '上次检查：3 分钟前',
}) {
  // 和 main.dart 里一样：优先用下载中的版本号，其次最新版本，最后待安装版本
  final shownVersion = dlVersion.isNotEmpty
      ? dlVersion
      : (latest.isNotEmpty ? latest : pending);
  return updateBannerCopy(
    ready: ready,
    downloading: downloading,
    progress: progress,
    pending: pending,
    shownVersion: shownVersion,
    latest: latest,
    downloadStatus: downloadStatus,
    checking: checking,
    current: current,
    checkOk: checkOk,
    checkDetail: checkDetail,
    lastCheckText: lastCheckText,
  );
}

void main() {
  test('查失败时不许说"已是最新"', () {
    final copy = _copy(checkOk: false, checkDetail: '连不上更新服务器');
    expect(copy.kind, UpdateBannerKind.checkFailed);
    expect(copy.title.contains('已是最新'), isFalse);
    expect(copy.title, contains('检查更新失败'));
    expect(copy.subtitle, contains('连不上更新服务器'));
    expect(copy.subtitle, contains('上次检查'));
  });

  test('还没查过时也不许说"已是最新"', () {
    final copy = _copy(checkOk: null);
    expect(copy.kind, UpdateBannerKind.neverChecked);
    expect(copy.title.contains('已是最新'), isFalse);
  });

  test('只有明确查过、且没有新版本时才说"已是最新"', () {
    final copy = _copy(checkOk: true, current: '3.0.0.0-beta29');
    expect(copy.kind, UpdateBannerKind.upToDate);
    expect(copy.title, '当前已是最新版本 v3.0.0.0-beta29');
  });

  test('后端没回版本号时不要显示成"已是最新版本 v"', () {
    final copy = _copy(checkOk: true, current: '');
    expect(copy.title, '当前已是最新版本');
  });

  test('有新版本就报新版本，即使还没开始下载', () {
    final copy = _copy(latest: '3.0.0.0-beta32', downloadStatus: '');
    expect(copy.kind, UpdateBannerKind.hasUpdate);
    expect(copy.title, contains('beta32'));
  });

  test('下载失败要说失败，不能退回"已是最新"', () {
    final copy = _copy(latest: '3.0.0.0-beta32', downloadStatus: 'failed');
    expect(copy.kind, UpdateBannerKind.downloadFailed);
    expect(copy.title, contains('下载失败'));
  });

  test('正在下载时显示版本与百分比', () {
    final copy = _copy(
        downloading: true, latest: '3.0.0.0-beta32', progress: 0.42);
    expect(copy.kind, UpdateBannerKind.downloading);
    expect(copy.title, contains('beta32'));
    expect(copy.subtitle, contains('42%'));
  });

  test('检查中优先于"已是最新"（避免刚点完还显示已是最新）', () {
    final copy = _copy(checking: true, checkOk: true);
    expect(copy.kind, UpdateBannerKind.checking);
  });

  test('下载好了就给一键更新', () {
    final copy = _copy(ready: true, pending: '3.0.0.0-beta32');
    expect(copy.kind, UpdateBannerKind.ready);
    expect(copy.title, contains('一键更新'));
  });
}
