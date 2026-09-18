import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/adaptive_scaffold.dart';
import '../../../core/widgets/empty_state.dart';
import '../application/ai_providers.dart';
import '../domain/ai_message.dart';
import 'widgets/message_bubble.dart';
import 'widgets/proposal_card.dart';

/// Owner-only AI chat (design.md §19). Lives inside the shell as a tab on
/// compact widths and as the 300dp trailing pane on expanded. Proposed
/// changes always wait for UPDATE.
class AiChatScreen extends ConsumerStatefulWidget {
  const AiChatScreen({super.key});

  @override
  ConsumerState<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends ConsumerState<AiChatScreen> {
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();
  final _inputFocusNode = FocusNode();

  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _inputController.text;
    if (text.trim().isEmpty) return;
    _inputController.clear();
    await ref.read(aiChatControllerProvider.notifier).sendMessage(text);
    if (!mounted) return;
    _scrollToEnd();
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(aiChatControllerProvider);
    final latestProposal = state.messages
        .map((m) => m.proposal)
        .whereType<AiProposal>()
        .fold<AiProposal?>(null, (prev, p) => p);

    return LayoutBuilder(
      builder: (context, constraints) {
        final docked = constraints.maxWidth <= AdaptiveScaffold.aiPaneWidth + 1;
        final showSidePanel =
            AdaptiveScaffold.isExpanded(constraints.maxWidth) &&
            latestProposal != null &&
            !docked;
        final conversation = Column(
          children: [
            _AskHeader(compact: docked),
            const Divider(height: 1),
            Expanded(child: _body(state)),
            if (state.error != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.md,
                  0,
                  AppSpacing.md,
                  AppSpacing.sm,
                ),
                child: Text(
                  state.error!.detail,
                  style: const TextStyle(color: AppColors.error),
                ),
              ),
            _composer(state),
          ],
        );

        if (!showSidePanel) return conversation;

        return Row(
          children: [
            Expanded(flex: 3, child: conversation),
            const VerticalDivider(width: 1),
            Expanded(
              flex: 2,
              child: ListView(
                padding: const EdgeInsets.all(AppSpacing.md),
                children: [
                  Text(
                    'Proposed update',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  ProposalCard(
                    proposal: latestProposal,
                    onRetry: _inputFocusNode.requestFocus,
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _body(AiChatState state) {
    if (state.messages.isEmpty) {
      return const EmptyState(
        icon: Icons.auto_awesome,
        title: 'Ask about your business',
        message:
            'Questions are answered from your tables. '
            'Proposed changes always wait for you to tap UPDATE.',
      );
    }
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: state.messages.length + (state.isSending ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == state.messages.length) {
          return const Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: EdgeInsets.all(AppSpacing.md),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          );
        }
        return MessageBubble(
          message: state.messages[index],
          onRetryProposal: _inputFocusNode.requestFocus,
        );
      },
    );
  }

  Widget _composer(AiChatState state) {
    final busy = state.isStartingSession || state.isSending;
    return Material(
      color: AppColors.surface,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.md,
          AppSpacing.sm,
          AppSpacing.md,
          AppSpacing.md,
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _inputController,
                enabled: !busy,
                decoration: const InputDecoration(hintText: 'Ask Velmart…'),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            IconButton.filled(
              tooltip: 'Send',
              style: IconButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.primary,
                foregroundColor: Theme.of(context).colorScheme.onPrimary,
              ),
              onPressed: busy ? null : _send,
              icon: const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}

class _AskHeader extends StatelessWidget {
  const _AskHeader({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.sm,
      ),
      child: Row(
        children: [
          Icon(
            Icons.auto_awesome,
            size: compact ? 18 : 22,
            color: AppColors.brandPrimaryDark,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'Ask Velmart',
              style: compact
                  ? Theme.of(context).textTheme.titleMedium
                  : Theme.of(context).textTheme.headlineSmall,
            ),
          ),
        ],
      ),
    );
  }
}
