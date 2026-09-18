import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Active-filter chips plus a quiet "Clear filters" action (design.md §16.2).
class AppFilterBar extends StatelessWidget {
  const AppFilterBar({
    super.key,
    required this.chips,
    this.onClear,
    this.clearLabel = 'Clear filters',
  });

  final List<Widget> chips;
  final VoidCallback? onClear;
  final String clearLabel;

  @override
  Widget build(BuildContext context) {
    if (chips.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(AppSpacing.md, 0, AppSpacing.md, AppSpacing.sm),
      child: Row(
        children: [
          Expanded(
            child: Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.xs,
              children: chips,
            ),
          ),
          if (onClear != null)
            TextButton(onPressed: onClear, child: Text(clearLabel)),
        ],
      ),
    );
  }
}
