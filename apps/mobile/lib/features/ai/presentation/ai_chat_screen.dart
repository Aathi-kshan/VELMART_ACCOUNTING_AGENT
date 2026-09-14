import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/widgets/empty_state.dart';
import '../application/ai_providers.dart';
import 'widgets/message_bubble.dart';

/// The Owner-only AI chat (plan sections 16.2, 16.12; docs/API.md §9).
/// Gated by `canUseAi` at the call site (`more_screen.dart`/`app_router.dart`)
/// — this screen never checks the role itself, matching "Flutter hides
/// buttons; Flutter never decides anything" (`routing/guards.dart`).
class AiChatScreen extends ConsumerStatefulWidget {
  const AiChatScreen({super.key});

  @override
  ConsumerState<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends ConsumerState<AiChatScreen> {
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
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

    return Scaffold(
      appBar: AppBar(title: const Text('Ask about your business')),
      body: Column(
        children: [
          Expanded(child: _body(state)),
          if (state.error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text(
                state.error!.detail,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          _composer(state),
        ],
      ),
    );
  }

  Widget _body(AiChatState state) {
    if (state.messages.isEmpty) {
      return const EmptyState(
        icon: Icons.chat_bubble_outline,
        message:
            'Ask a question about your business data, e.g. '
            '"How much did we spend on fuel last month?"',
      );
    }
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(12),
      itemCount: state.messages.length + (state.isSending ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == state.messages.length) {
          return const Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: EdgeInsets.all(12),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          );
        }
        return MessageBubble(message: state.messages[index]);
      },
    );
  }

  Widget _composer(AiChatState state) {
    final busy = state.isStartingSession || state.isSending;
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _inputController,
              enabled: !busy,
              decoration: const InputDecoration(
                hintText: 'Ask a question…',
                border: OutlineInputBorder(),
              ),
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => _send(),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(onPressed: busy ? null : _send, icon: const Icon(Icons.send)),
        ],
      ),
    );
  }
}
