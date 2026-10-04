import 'package:flutter/material.dart';

/// 大按钮：给老师站在讲台前用，图标和字都放大。
///
/// [disabledHint] 会出现在按钮下方，说明"为什么是灰的"——
/// 之前的实现只有一个灰按钮，三种不同原因长得一模一样。
class BigButton extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    final scheme = Theme.of(context).colorScheme;
    final button = SizedBox(
      width: 168,
      height: 104,
      child: Material(
        color: disabled ? scheme.surfaceContainerHighest : color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              Icon(icon,
                  size: 38,
                  color: disabled ? scheme.onSurfaceVariant.withValues(alpha: 0.5) : color),
              const SizedBox(height: 8),
              Text(
                label,
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
    );

    final hint = (disabled && disabledHint != null)
        ? Padding(
            padding: const EdgeInsets.only(top: 4),
            child: SizedBox(
              width: 168,
              child: Text(disabledHint!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontSize: 12, color: scheme.onSurfaceVariant)),
            ),
          )
        : null;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[button, ?hint],
    );
  }
}

