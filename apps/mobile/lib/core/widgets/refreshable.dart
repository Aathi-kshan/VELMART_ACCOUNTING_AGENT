import 'package:flutter/material.dart';

/// [RefreshIndicator] that works for both scrolling lists and non-scrolling
/// loading/error/empty bodies (which otherwise have no overscroll to trigger).
/// Named to avoid clashing with Riverpod's `Refreshable`.
class PullToRefresh extends StatelessWidget {
  const PullToRefresh({
    super.key,
    required this.onRefresh,
    required this.child,
    this.childScrolls = false,
  });

  final Future<void> Function() onRefresh;
  final Widget child;
  final bool childScrolls;

  @override
  Widget build(BuildContext context) {
    if (childScrolls) {
      return RefreshIndicator(onRefresh: onRefresh, child: child);
    }
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: constraints.maxHeight),
              child: child,
            ),
          );
        },
      ),
    );
  }
}
