import 'package:flutter/material.dart';

/// 大按钮：给老师站在讲台前用，图标和字都放大。
///
/// 手感想尽量"活"一点（参考 FlClash）：
///   * 悬停时抬起来（渐变变亮、彩色投影变大）；
///   * 按下去时轻微缩小（AnimatedScale），有"真的按到了"的反馈；
///   * 点击有水波纹（InkWell splash，颜色取自按钮主色）。
/// [disabledHint] 会出现在按钮下方，说明"为什么是灰的"。
class BigButton extends StatefulWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback? onPressed;
  final String? disabledHint;

  const BigButton({
    super.key,
    required this.icon,
    required this.label,
    required this.color,
    this.onPressed,
    this.disabledHint,
  });

  @override
  State<BigButton> createState() => _BigButtonState();
}

class _BigButtonState extends State<BigButton> {
  bool _hover = false;
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final disabled = widget.onPressed == null;
    final accent = disabled ? scheme.onSurfaceVariant : widget.color;
    final scale = (_pressed && !disabled) ? 0.955 : 1.0;

    // 背景：以 surface 为底、把主色按透明度叠上去（深浅色主题都成立）。
    final Color top = disabled
        ? scheme.surfaceContainerHighest
        : Color.alphaBlend(
            accent.withValues(alpha: _hover ? 0.26 : 0.16),
            scheme.surface,
          );
    final Color bottom = disabled
        ? scheme.surfaceContainerHighest
        : Color.alphaBlend(
            accent.withValues(alpha: _hover ? 0.12 : 0.05),
            scheme.surface,
          );

    final shadows = disabled
        ? const <BoxShadow>[]
        : <BoxShadow>[
            BoxShadow(
              color: accent.withValues(alpha: _hover ? 0.30 : 0.14),
              blurRadius: _hover ? 22 : 12,
              offset: Offset(0, _hover ? 8 : 4),
            ),
          ];

    final button = AnimatedScale(
      scale: scale,
      duration: const Duration(milliseconds: 90),
      curve: Curves.easeOut,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        curve: Curves.easeOut,
        width: 168,
        height: 104,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: <Color>[top, bottom],
          ),
          border: Border.all(
            color: disabled
                ? scheme.outlineVariant
                : accent.withValues(alpha: _hover ? 0.55 : 0.28),
            width: 1,
          ),
          boxShadow: shadows,
        ),
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(18),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: widget.onPressed,
            onTapDown: disabled ? null : (_) => setState(() => _pressed = true),
            onTapUp: disabled ? null : (_) => setState(() => _pressed = false),
            onTapCancel: disabled
                ? null
                : () => setState(() => _pressed = false),
            splashColor: accent.withValues(alpha: 0.20),
            highlightColor: accent.withValues(alpha: 0.08),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    color: disabled
                        ? scheme.onSurfaceVariant.withValues(alpha: 0.10)
                        : accent.withValues(alpha: _hover ? 0.22 : 0.14),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    widget.icon,
                    size: 28,
                    color: disabled
                        ? scheme.onSurfaceVariant.withValues(alpha: 0.5)
                        : accent,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  widget.label,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: disabled
                        ? scheme.onSurfaceVariant.withValues(alpha: 0.6)
                        : scheme.onSurface,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    final hint = (disabled && widget.disabledHint != null)
        ? Padding(
            padding: const EdgeInsets.only(top: 4),
            child: SizedBox(
              width: 168,
              child: Text(
                widget.disabledHint!,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              ),
            ),
          )
        : null;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        MouseRegion(
          onEnter: (_) => setState(() => _hover = true),
          onExit: (_) => setState(() {
            _hover = false;
            _pressed = false;
          }),
          cursor: disabled
              ? SystemMouseCursors.basic
              : SystemMouseCursors.click,
          child: button,
        ),
        ?hint,
      ],
    );
  }
}
