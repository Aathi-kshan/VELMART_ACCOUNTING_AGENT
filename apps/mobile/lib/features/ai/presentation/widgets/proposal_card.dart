import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
  const ProposalCard({super.key, required this.proposal});

  final AiProposal proposal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(aiChatControllerProvider);
    final resolvedStatus = state.proposalStatuses[proposal.id];
    final isPending = resolvedStatus == null;
    final isBusy = state.pendingProposalActions.contains(proposal.id);
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        border: Border.all(color: colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(10),
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
                style: textTheme.labelLarge?.copyWith(fontWeight: FontWeight.bold),
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
              style: textTheme.bodySmall?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: isBusy
                      ? null
                      : () => ref.read(aiChatControllerProvider.notifier).cancelProposal(
                          proposal.id,
                        ),
                  child: const Text('CANCEL'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: isBusy
                      ? null
                      : () => ref.read(aiChatControllerProvider.notifier).applyProposal(
                          proposal.id,
                        ),
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
          ] else
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
    final color = applied ? Colors.green : colorScheme.error;
    return Row(
      children: [
        Icon(applied ? Icons.check_circle : Icons.cancel, size: 16, color: color),
        const SizedBox(width: 4),
        Text(
          applied ? 'Applied' : 'Cancelled',
          style: Theme.of(
            context,
          ).textTheme.labelMedium?.copyWith(color: color, fontWeight: FontWeight.bold),
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
                  child: Icon(Icons.arrow_forward, size: 14, color: colorScheme.onSurfaceVariant),
                ),
                Text(
                  change.afterDisplay,
                  style: textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
