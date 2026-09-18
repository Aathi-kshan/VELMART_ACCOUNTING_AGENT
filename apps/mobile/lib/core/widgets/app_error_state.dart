import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Failed-load state (design.md §20.5). Distinct from [EmptyState] — a
/// failed fetch is not "nothing here yet".
class AppErrorState extends StatelessWidget {
  const AppErrorState({
    super.key,
    required this.message,
    this.title = 'Something went wrong',
    this.onRetry,
    this.retryLabel = 'Retry',
  });

  final String title;
  final String message;
  final VoidCallback? onRetry;
  final String retryLabel;

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
              Icon(Icons.error_outline, size: 40, color: colorScheme.error),
              const SizedBox(height: AppSpacing.md),
              Text(title, style: textTheme.titleLarge, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.sm),
              Text(
                message,
                textAlign: TextAlign.center,
                style: textTheme.bodyLarge?.copyWith(color: colorScheme.onSurfaceVariant),
              ),
              if (onRetry != null) ...[
                const SizedBox(height: AppSpacing.xl),
                FilledButton(onPressed: onRetry, child: Text(retryLabel)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
