import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_radii.dart';
import '../../../../core/theme/app_spacing.dart';
import '../../domain/ai_message.dart';
import 'proposal_card.dart';
import 'tool_activity_chip.dart';

/// One chat bubble — the Owner's own message, or the assistant's answer
/// with its tool activity and provenance (plan section 16.5: every figure
/// must be traceable to a page, record count, and date range).
class MessageBubble extends StatelessWidget {
  const MessageBubble({super.key, required this.message, this.onRetryProposal});

  final AiChatMessage message;

  /// Passed straight through to this bubble's [ProposalCard], if it has
  /// one — see that widget's own `onRetry` doc comment.
  final VoidCallback? onRetryProposal;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == AiMessageRole.user;
    final textTheme = Theme.of(context).textTheme;

    return LayoutBuilder(
      builder: (context, constraints) {
        final parentWidth = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : MediaQuery.sizeOf(context).width;
        return Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            constraints: BoxConstraints(maxWidth: parentWidth * 0.92),
            margin: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
            padding: const EdgeInsets.all(AppSpacing.smMd),
            decoration: BoxDecoration(
              color: isUser ? AppColors.brandPrimaryDark : AppColors.surface,
              borderRadius: AppRadii.mdRadius,
              border: isUser ? null : Border.all(color: AppColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (message.toolCalls.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        for (final call in message.toolCalls)
                          ToolActivityChip(toolCall: call),
                      ],
                    ),
                  ),
                Text(
                  message.content,
                  style: textTheme.bodyLarge?.copyWith(
                    color: isUser
                        ? AppColors.textOnBrand
                        : AppColors.textPrimary,
                  ),
                ),
                if (message.provenance.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.sm),
                  for (final provenance in message.provenance)
                    Text(
                      provenance.summary,
                      style: textTheme.bodySmall?.copyWith(
                        color: isUser
                            ? AppColors.textOnBrand.withValues(alpha: 0.8)
                            : AppColors.textSecondary,
                      ),
                    ),
                ],
                if (message.partial) ...[
                  const SizedBox(height: 6),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.info_outline,
                        size: 14,
                        color: isUser ? AppColors.textOnBrand : AppColors.error,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        'Partial answer',
                        style: textTheme.labelSmall?.copyWith(
                          color: isUser
                              ? AppColors.textOnBrand
                              : AppColors.error,
                        ),
                      ),
                    ],
                  ),
                ],
                if (message.proposal != null)
                  ProposalCard(
                    proposal: message.proposal!,
                    onRetry: onRetryProposal,
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
