import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// A 403 rendered as a screen state (design.md §20.6) rather than a raw
/// exception — a Manager who deep-links into an Owner-only screen sees
/// this, never a stack trace or the server's own error string. Verbatim
/// copy from the mockups' "PERMISSION" reference card.
class AppPermissionState extends StatelessWidget {
  const AppPermissionState({
    super.key,
    this.message = 'Ask the Owner if you need access to this page.',
    this.onGoBack,
  });

  final String message;
  final VoidCallback? onGoBack;

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
              Icon(Icons.lock_outline, size: 40, color: colorScheme.outline),
              const SizedBox(height: AppSpacing.md),
              Text(
                "You don't have permission to do that",
                style: textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                message,
                textAlign: TextAlign.center,
                style: textTheme.bodyLarge?.copyWith(color: colorScheme.onSurfaceVariant),
              ),
              if (onGoBack != null) ...[
                const SizedBox(height: AppSpacing.xl),
                FilledButton(onPressed: onGoBack, child: const Text('Go back')),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
