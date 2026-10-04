import 'package:flutter/material.dart';

/// 全局主题。
///
/// 定位是"老师站在大屏幕/讲台前操作"：
/// 字号比默认 Material 略大、按钮点击区域更大、对比度足够。
/// 同时提供浅色 / 深色两套，跟随系统或手动切换（设置页）。
class AppTheme {
  AppTheme._();

  static const Color seed = Color(0xFF1A73E8);

  static ThemeData light() => _build(Brightness.light);

  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData of(Brightness brightness) => _build(brightness);

  static ThemeData _build(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: brightness);
    final isDark = brightness == Brightness.dark;
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      fontFamily: 'NotoSansSC',
      visualDensity: VisualDensity.comfortable,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      scaffoldBackgroundColor:
          isDark ? const Color(0xFF15171A) : const Color(0xFFF2F4F8),
    );

    // 必须在**带颜色的**基础样式上 copyWith。
    // 直接写 TextStyle(fontSize: xx) 会得到 color 为 null 的样式，
    // 一旦继承链断开就是"看不见的文字"（浅色模式下真实出现过）。
    final t = base.textTheme;
    return base.copyWith(
      textTheme: t.copyWith(
        // 比默认大一号：投影/远距离也能看清
        displayLarge:
            t.displayLarge!.copyWith(fontSize: 64, fontWeight: FontWeight.w700),
        headlineMedium: t.headlineMedium!
            .copyWith(fontSize: 30, fontWeight: FontWeight.w700),
        titleLarge: t.titleLarge!.copyWith(
            fontSize: 24, fontWeight: FontWeight.w700, color: scheme.onSurface),
        titleMedium: t.titleMedium!.copyWith(
            fontSize: 18, fontWeight: FontWeight.w600, color: scheme.onSurface),
        titleSmall: t.titleSmall!.copyWith(
            fontSize: 16, fontWeight: FontWeight.w600, color: scheme.onSurface),
        bodyLarge: t.bodyLarge!.copyWith(
            fontSize: 16, fontWeight: FontWeight.w500, color: scheme.onSurface),
        bodyMedium: t.bodyMedium!.copyWith(
            fontSize: 15, fontWeight: FontWeight.w400, color: scheme.onSurface),
        bodySmall: t.bodySmall!.copyWith(
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: scheme.onSurfaceVariant),
        labelLarge:
            t.labelLarge!.copyWith(fontSize: 16, fontWeight: FontWeight.w600),
        labelMedium:
            t.labelMedium!.copyWith(fontSize: 14, fontWeight: FontWeight.w500),
        labelSmall:
            t.labelSmall!.copyWith(fontSize: 13, fontWeight: FontWeight.w400),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: scheme.primary,
        titleTextStyle: TextStyle(
          fontSize: 17,
          fontWeight: FontWeight.w600,
          color: scheme.onSurface,
        ),
        subtitleTextStyle: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w400,
          color: scheme.onSurfaceVariant,
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: isDark ? const Color(0xFF1E2126) : Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      // 卡片必须有可见的"框"：浅色下 M3 的 surfaceContainerLowest 是纯白，
      // 页面底色也很浅 → 只有极淡边框，用户反馈"这个框看不见"。
      // 改成白底 + 阴影 + 明确边框。
      cardTheme: CardThemeData(
        color: isDark ? const Color(0xFF1E2126) : Colors.white,
        surfaceTintColor: Colors.transparent,
        shadowColor: Colors.black.withValues(alpha: 0.22),
        elevation: isDark ? 0 : 1.5,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(
              color: isDark
                  ? const Color(0xFF3C424B)
                  : const Color(0xFFD6DAE3),
              width: 1),
        ),
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor:
            isDark ? const Color(0xFF1B1E23) : scheme.surfaceContainerLow,
        indicatorColor: scheme.primaryContainer,
        labelType: NavigationRailLabelType.all,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: isDark ? const Color(0xFF2A2E35) : const Color(0xFF323232),
        contentTextStyle: const TextStyle(fontSize: 15, color: Colors.white),
      ),
      dividerTheme: DividerThemeData(
        color: isDark ? const Color(0xFF2E333A) : const Color(0xFFE1E4EB),
      ),
    );
  }
}
