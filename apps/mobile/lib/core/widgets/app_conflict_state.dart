import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// A stale-write 409 (design.md §17.4, §20 "VERSION CONFLICT" reference
/// card) — optimistic locking caught someone else's newer save. Verbatim
/// copy from the mockups; never phrased as "If-Match failed" or similar
/// implementation language (design.md §32).
///
/// Two shapes for one piece of copy: [AppConflictState] itself for a
/// full-screen state, and [presentDialog] for the common case — the Owner
/// is mid-edit in a form and shouldn't lose the screen, just be told to
/// reload before trying again.
class AppConflictState extends StatelessWidget {
  const AppConflictState({super.key, this.onReload});

  final VoidCallback? onReload;

  static const _title = 'This record changed since you opened it';
  static const _message = "Your edits weren't saved. Reload to see the latest values.";

  /// Shows the same copy as a dismiss-by-reload dialog. `onReload` should
  /// re-fetch the record and reset any local edit state; the dialog closes
  /// itself first so `onReload` never runs while it's still on screen.
  static Future<void> presentDialog(BuildContext context, {required VoidCallback onReload}) {
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text(_title),
        content: const Text(_message),
        actions: [
          FilledButton(
            onPressed: () {
              Navigator.of(context).pop();
              onReload();
            },
            child: const Text('Reload latest'),
          ),
        ],
      ),
    );
  }

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
              Icon(Icons.sync_problem_outlined, size: 40, color: colorScheme.outline),
              const SizedBox(height: AppSpacing.md),
              Text(_title, style: textTheme.titleLarge, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.sm),
              Text(
                _message,
                textAlign: TextAlign.center,
                style: textTheme.bodyLarge?.copyWith(color: colorScheme.onSurfaceVariant),
              ),
              if (onReload != null) ...[
                const SizedBox(height: AppSpacing.xl),
                FilledButton(onPressed: onReload, child: const Text('Reload latest')),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
