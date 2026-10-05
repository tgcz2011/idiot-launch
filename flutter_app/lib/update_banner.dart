/// 主页顶部「更新」横幅该说什么话。
///
/// 抽成纯函数是为了能被单测钉住 —— 这里的每一句话都是用户会当真的：
/// beta29 装机实测过，更新检查其实一直在静默失败（Supabase 因为
/// `Accept: application/vnd.github+json` 判 406，GitHub 兜底又用着构建时
/// 塞进去的临时 token），界面却一直显示"当前已是最新版本"。
/// 所以规矩是：**只有后端明确说"这次查到结论了"（check_ok == true）
/// 才允许显示"已是最新"**；查失败要说失败，没查过要说没查过。
library;

enum UpdateBannerKind {
  /// 新版本已经下载好，可以一键安装
  ready,

  /// 正在后台下载
  downloading,

  /// 发现了新版本，但还没下载/下载失败
  hasUpdate,

  /// 新版本下载失败
  downloadFailed,

  /// 正在检查
  checking,

  /// 检查失败（连不上渠道）
  checkFailed,

  /// 还没查过（后端没回话或首次运行）
  neverChecked,

  /// 查过了，确实是最新
  upToDate,
}

class UpdateBannerCopy {
  const UpdateBannerCopy(this.kind, this.title, this.subtitle);

  final UpdateBannerKind kind;
  final String title;
  final String subtitle;
}

/// 纯决策：给定后端状态，决定横幅说什么。
UpdateBannerCopy updateBannerCopy({
  required bool ready,
  required bool downloading,
  required double progress,
  required String pending,
  required String shownVersion,
  required String latest,
  required String downloadStatus,
  required bool checking,
  required String current,
  required bool? checkOk,
  required String checkDetail,
  required String lastCheckText,
}) {
  if (ready) {
    return UpdateBannerCopy(UpdateBannerKind.ready, '可一键更新至 v$pending',
        '安装包已经下载好了，点一下就会开始安装（会显示安装进度）');
  }
  if (downloading) {
    return UpdateBannerCopy(
        UpdateBannerKind.downloading,
        '正在后台下载 v$shownVersion',
        progress > 0.005
            ? '${(progress * 100).toStringAsFixed(0)}% · 下载完成后这里会出现「一键更新」'
            : '正在连接下载源…（教室网络慢时会比较久，不影响倒计时和早晚读）');
  }
  if (latest.isNotEmpty) {
    // 有新版本却既没在下载、也没下载好：要么刚失败，要么还没轮到它 —— 必须说出来。
    final failed = downloadStatus == 'failed';
    return UpdateBannerCopy(
        failed ? UpdateBannerKind.downloadFailed : UpdateBannerKind.hasUpdate,
        failed ? '新版本 v$latest 下载失败' : '发现新版本 v$latest',
        failed
            ? '会自动延后重试；也可以点右边立即重试（不影响倒计时和早晚读）'
            : '稍后会自动在后台下载，也可以点右边立刻开始');
  }
  if (checking) {
    return const UpdateBannerCopy(
        UpdateBannerKind.checking, '正在检查更新…', '教室网络较慢时可能要等十几秒');
  }
  if (checkOk != true) {
    final failed = checkOk == false;
    if (!failed) {
      return const UpdateBannerCopy(UpdateBannerKind.neverChecked, '还没有检查过更新',
          '点右边检查一下（教室网络较慢时可能要等十几秒）');
    }
    final detail = checkDetail.isEmpty ? '' : '· $checkDetail';
    return UpdateBannerCopy(UpdateBannerKind.checkFailed, '检查更新失败，暂时不知道有没有新版本',
        '$lastCheckText$detail（稍后会自动重试）');
  }
  // 后端还没回话时 version 可能是空的，别显示成"当前已是最新版本 v"
  return UpdateBannerCopy(UpdateBannerKind.upToDate,
      current.isEmpty ? '当前已是最新版本' : '当前已是最新版本 v$current', lastCheckText);
}
