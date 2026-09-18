import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_radii.dart';
import '../../../../core/theme/app_spacing.dart';
import '../../application/ai_providers.dart';
import '../../domain/ai_message.dart';

/// The Owner's review of one AI-prepared change (P8 Lite). Nothing has
/// been written yet — this card is the only place that changes: tapping
/// UPDATE calls the real apply endpoint, which re-validates and version-
/// checks server-side; tapping CANCEL leaves the record untouched.
///
/// Current and proposed values are never rendered ambiguously: "before" is
/// always struck through and muted, "after" is always bold, with an arrow
/// between them.
class ProposalCard extends ConsumerWidget {
  const ProposalCard({super.key, required this.proposal, this.onRetry});

  final AiProposal proposal;

  /// Wired to focus the message composer, so "Ask again" / "Create a new
  /// proposal" is a real action (design.md §32: never a fake button) — the
  /// Owner's next typed question is the actual retry, there is no client-
  /// side "resend the same request" since the server itself must recompute
  /// a proposal from fresh data, not replay the old one.
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(aiChatControllerProvider);
    final resolvedStatus = state.proposalStatuses[proposal.id];
    final isPending = resolvedStatus == null;
    final isExpired = resolvedStatus == 'EXPIRED';
    final isStale = resolvedStatus == 'STALE';
    final isBusy = state.pendingProposalActions.contains(proposal.id);
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return Container(
      margin: const EdgeInsets.only(top: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.smMd),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border.all(color: AppColors.border),
        borderRadius: AppRadii.mdRadius,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(Icons.edit_note, size: 18, color: colorScheme.primary),
              const SizedBox(width: 6),
              Text(
                'AI Proposed Update',
                style: textTheme.labelLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(proposal.summary, style: textTheme.bodyMedium),
          const SizedBox(height: 8),
          for (final change in proposal.changes) _ChangeRow(change: change),
          const SizedBox(height: 10),
          if (isPending) ...[
            Text(
              proposal.expiryLabel,
              style: textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: isBusy
                      ? null
                      : () => ref
                            .read(aiChatControllerProvider.notifier)
                            .cancelProposal(proposal.id),
                  child: const Text('CANCEL'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: isBusy
                      ? null
                      : () => ref
                            .read(aiChatControllerProvider.notifier)
                            .applyProposal(proposal.id),
                  child: isBusy
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('UPDATE'),
                ),
              ],
            ),
          ] else if (isExpired)
            _RetryNotice(
              title: 'This update expired',
              message: "Proposals last ten minutes so they can't be applied to changed data.",
              actionLabel: 'Ask again',
              onRetry: onRetry,
            )
          else if (isStale)
            _RetryNotice(
              title: 'This record changed after the proposal was created',
              message: 'Nothing was applied. Create a new proposal to see the current values.',
              actionLabel: 'Create a new proposal',
              onRetry: onRetry,
            )
          else
            _ResolvedBadge(status: resolvedStatus),
        ],
      ),
    );
  }
}

class _ResolvedBadge extends StatelessWidget {
  const _ResolvedBadge({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final applied = status == 'APPLIED';
    final colorScheme = Theme.of(context).colorScheme;
    final color = applied
        ? Theme.of(context).colorScheme.primary
        : colorScheme.error;
    return Row(
      children: [
        Icon(
          applied ? Icons.check_circle : Icons.cancel,
          size: 16,
          color: color,
        ),
        const SizedBox(width: 4),
        Text(
          applied ? 'Applied' : 'Cancelled',
          style: Theme.of(context).textTheme.labelMedium
              ?.copyWith(color: color, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}

/// The expired/stale outcome (design.md §19.9 "States"): explains what
/// happened in plain words and offers the one real next step — never
/// silently re-applying a proposal built from data that's no longer
/// current.
class _RetryNotice extends StatelessWidget {
  const _RetryNotice({
    required this.title,
    required this.message,
    required this.actionLabel,
    required this.onRetry,
  });

  final String title;
  final String message;
  final String actionLabel;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              Icons.schedule_outlined,
              size: 16,
              color: colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                title,
                style: textTheme.labelLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          message,
          style: textTheme.bodySmall?.copyWith(
            color: colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(onPressed: onRetry, child: Text(actionLabel)),
        ),
      ],
    );
  }
}

class _ChangeRow extends StatelessWidget {
  const _ChangeRow({required this.change});

  final AiProposalChange change;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(change.column, style: textTheme.labelMedium),
          ),
          Expanded(
            child: Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  change.beforeDisplay,
                  style: textTheme.bodyMedium?.copyWith(
                    decoration: TextDecoration.lineThrough,
                    color: colorScheme.onSurfaceVariant,
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  child: Icon(
                    Icons.arrow_forward,
                    size: 14,
                    color: colorScheme.onSurfaceVariant,
                  ),
                ),
                Text(
                  change.afterDisplay,
                  style: textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
