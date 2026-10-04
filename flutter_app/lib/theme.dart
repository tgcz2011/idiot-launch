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
      scaffoldBackgroundColor: isDark ? const Color(0xFF15171A) : scheme.surface,
    );

    return base.copyWith(
      textTheme: base.textTheme.copyWith(
        // 比默认大一号：投影/远距离也能看清
        displayLarge: const TextStyle(fontSize: 64, fontWeight: FontWeight.w700),
        headlineMedium: const TextStyle(fontSize: 30, fontWeight: FontWeight.w700),
        titleLarge: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
        titleMedium: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        titleSmall: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        bodyLarge: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
        bodyMedium: const TextStyle(fontSize: 15, fontWeight: FontWeight.w400),
        bodySmall: const TextStyle(fontSize: 14, fontWeight: FontWeight.w400),
        labelLarge: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        labelMedium: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
        labelSmall: const TextStyle(fontSize: 13, fontWeight: FontWeight.w400),
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
        backgroundColor: isDark ? const Color(0xFF1E2126) : scheme.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      cardTheme: CardThemeData(
        color: isDark ? const Color(0xFF1E2126) : scheme.surfaceContainerLowest,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: scheme.outlineVariant.withValues(alpha: 0.6)),
        ),
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: isDark ? const Color(0xFF1B1E23) : scheme.surfaceContainerLow,
        indicatorColor: scheme.primaryContainer,
        labelType: NavigationRailLabelType.all,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: isDark ? const Color(0xFF2A2E35) : const Color(0xFF323232),
        contentTextStyle: const TextStyle(fontSize: 15, color: Colors.white),
      ),
    );
  }
}
