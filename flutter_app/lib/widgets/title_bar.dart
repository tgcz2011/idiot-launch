import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

class CustomTitleBar extends StatelessWidget {
  final String title;
  final bool showMaximize;
  const CustomTitleBar({super.key, required this.title, this.showMaximize = true});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 32,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(
            bottom: BorderSide(
                color: Theme.of(context).colorScheme.outlineVariant, width: 1)),
      ),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onPanStart: (_) => windowManager.startDragging(),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(
                  children: [
                    Icon(Icons.touch_app, size: 16, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(width: 8),
                    Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                  ],
                ),
              ),
            ),
          ),
          TitleBarButton(icon: Icons.remove, onPressed: () => windowManager.minimize()),
          if (showMaximize)
            TitleBarButton(
              icon: Icons.check_box_outline_blank,
              onPressed: () async {
                if (await windowManager.isMaximized()) {
                  windowManager.unmaximize();
                } else {
                  windowManager.maximize();
                }
              },
            ),
          TitleBarButton(icon: Icons.close, isClose: true, onPressed: () => windowManager.close()),
        ],
      ),
    );
  }
}

class TitleBarButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onPressed;
  final bool isClose;
  const TitleBarButton(
      {super.key,
      required this.icon,
      required this.onPressed,
      this.isClose = false});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: isClose ? '关闭窗口（最小化到托盘）' : '',
      child: SizedBox(
        width: 48,
        height: 34,
        child: InkWell(
          onTap: onPressed,
          hoverColor: isClose
              ? scheme.error.withValues(alpha: 0.85)
              : scheme.onSurface.withValues(alpha: 0.08),
          child: Icon(icon, size: 18, color: isClose ? null : scheme.onSurfaceVariant),
        ),
      ),
    );
  }
}
