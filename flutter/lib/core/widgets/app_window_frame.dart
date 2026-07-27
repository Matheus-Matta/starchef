import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

class AppWindowFrame extends StatelessWidget {
  const AppWindowFrame({
    super.key,
    required this.child,
    this.title = 'StarChef PDV',
  });

  final Widget child;
  final String title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final background = dark ? const Color(0xFF18181B) : Colors.white;
    final border = dark ? const Color(0xFF27272A) : const Color(0xFFE7DFD3);

    return ColoredBox(
      color: background,
      child: Column(
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: background,
              border: Border(bottom: BorderSide(color: border)),
            ),
            child: SizedBox(
              height: 38,
              child: WindowCaption(
                brightness: theme.brightness,
                backgroundColor: background,
                title: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Image.asset(
                      'assets/logoicon.png',
                      width: 20,
                      height: 20,
                      filterQuality: FilterQuality.high,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      title,
                      style: TextStyle(
                        color: dark ? Colors.white : const Color(0xFF2B261F),
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          Expanded(child: child),
        ],
      ),
    );
  }
}
