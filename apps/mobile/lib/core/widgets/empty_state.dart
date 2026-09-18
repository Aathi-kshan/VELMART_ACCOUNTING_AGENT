import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Canonical empty state (design.md §20.2 / §25.23): icon, optional title,
/// message, optional primary action. Compact, never a full-page illustration.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.message,
    this.title,
    this.icon = Icons.inbox_outlined,
    this.actionLabel,
    this.onAction,
  }) : totalCount = null;

  /// A page that has records, but the current filter/search matched none
  /// (design.md §16.4) — distinct copy from the true-empty case above, so
  /// the Owner isn't told to "add the first record" onto a page that
  /// already has 1,284 of them. Verbatim from the mockups' own "FILTERED
  /// EMPTY" reference card and the record-list screen itself.
  const EmptyState.filtered({super.key, this.totalCount, required VoidCallback onClear})
    : icon = Icons.filter_alt_off_outlined,
      title = 'No records match these filters',
      message = totalCount == null
          ? 'Try a different value, or clear the filters to see every record on this page.'
          : 'The page still has $totalCount records.',
      actionLabel = 'Clear filters',
      onAction = onClear;

  final String message;
  final String? title;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;

  /// `EmptyState.filtered` only: when known, folded into [message] as "The
  /// page still has N records." instead of the generic "try a different
  /// value" copy.
  final int? totalCount;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 40, color: colorScheme.outline),
              const SizedBox(height: AppSpacing.md),
              if (title != null) ...[
                Text(title!, style: textTheme.titleLarge, textAlign: TextAlign.center),
                const SizedBox(height: AppSpacing.sm),
              ],
              Text(
                message,
                textAlign: TextAlign.center,
                style: textTheme.bodyLarge?.copyWith(color: colorScheme.onSurfaceVariant),
              ),
              if (actionLabel != null && onAction != null) ...[
                const SizedBox(height: AppSpacing.xl),
                FilledButton(onPressed: onAction, child: Text(actionLabel!)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
