import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../data/ai_repository.dart';
import '../domain/ai_message.dart';

final aiRepositoryProvider = Provider<AiRepository>((ref) {
  final client = ref.watch(apiClientProvider);
  return AiRepository(dio: client.dio);
});

/// One chat session's state — a `StateNotifier`, not a plain
/// `FutureProvider`, since sending a message appends to an existing
/// conversation rather than recomputing it (same reasoning as
/// `AuditLogController`'s "load more").
final aiChatControllerProvider = StateNotifierProvider<AiChatController, AiChatState>((ref) {
  final repository = ref.watch(aiRepositoryProvider);
  return AiChatController(repository);
});

class AiChatState {
  const AiChatState({
    this.sessionId,
    this.messages = const [],
    this.isStartingSession = false,
    this.isSending = false,
    this.error,
  });

  final String? sessionId;
  final List<AiChatMessage> messages;
  final bool isStartingSession;
  final bool isSending;
  final ApiException? error;

  AiChatState copyWith({
    String? sessionId,
    List<AiChatMessage>? messages,
    bool? isStartingSession,
    bool? isSending,
    ApiException? error,
    bool clearError = false,
  }) => AiChatState(
    sessionId: sessionId ?? this.sessionId,
    messages: messages ?? this.messages,
    isStartingSession: isStartingSession ?? this.isStartingSession,
    isSending: isSending ?? this.isSending,
    error: clearError ? null : (error ?? this.error),
  );
}

class AiChatController extends StateNotifier<AiChatState> {
  AiChatController(this._repository) : super(const AiChatState());

  final AiRepository _repository;

  Future<String?> _ensureSession() async {
    if (state.sessionId != null) return state.sessionId;
    state = state.copyWith(isStartingSession: true, clearError: true);
    try {
      final sessionId = await _repository.startSession();
      state = state.copyWith(sessionId: sessionId, isStartingSession: false);
      return sessionId;
    } on ApiException catch (e) {
      state = state.copyWith(isStartingSession: false, error: e);
      return null;
    }
  }

  Future<void> sendMessage(String content) async {
    final trimmed = content.trim();
    if (trimmed.isEmpty || state.isSending) return;

    final sessionId = await _ensureSession();
    if (sessionId == null) return;

    state = state.copyWith(
      messages: [...state.messages, AiChatMessage.user(trimmed)],
      isSending: true,
      clearError: true,
    );

    try {
      final reply = await _repository.sendMessage(sessionId, trimmed);
      state = state.copyWith(messages: [...state.messages, reply], isSending: false);
    } on ApiException catch (e) {
      state = state.copyWith(isSending: false, error: e);
    }
  }
}
