import 'package:flutter/material.dart';

import '../../domain/ai_message.dart';
import 'proposal_card.dart';
import 'tool_activity_chip.dart';

/// One chat bubble — the Owner's own message, or the assistant's answer
/// with its tool activity and provenance (plan section 16.5: every figure
/// must be traceable to a page, record count, and date range).
class MessageBubble extends StatelessWidget {
  const MessageBubble({super.key, required this.message});

  final AiChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == AiMessageRole.user;
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isUser ? colorScheme.primaryContainer : colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (message.toolCalls.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: [
                    for (final call in message.toolCalls) ToolActivityChip(toolCall: call),
                  ],
                ),
              ),
            Text(message.content),
            if (message.provenance.isNotEmpty) ...[
              const SizedBox(height: 8),
              for (final provenance in message.provenance)
                Text(
                  provenance.summary,
                  style: textTheme.bodySmall?.copyWith(color: colorScheme.onSurfaceVariant),
                ),
            ],
            if (message.partial) ...[
              const SizedBox(height: 6),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.info_outline, size: 14, color: colorScheme.error),
                  const SizedBox(width: 4),
                  Text(
                    'Partial answer',
                    style: textTheme.labelSmall?.copyWith(color: colorScheme.error),
                  ),
                ],
              ),
            ],
            if (message.proposal != null) ProposalCard(proposal: message.proposal!),
          ],
        ),
      ),
    );
  }
}
