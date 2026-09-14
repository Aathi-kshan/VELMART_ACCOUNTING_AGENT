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
    this.proposalStatuses = const {},
    this.pendingProposalActions = const {},
  });

  final String? sessionId;
  final List<AiChatMessage> messages;
  final bool isStartingSession;
  final bool isSending;
  final ApiException? error;

  /// proposal id -> its resolved status (`"APPLIED"`/`"CANCELLED"`), once
  /// the Owner has acted on it. A proposal with no entry here is still
  /// `PENDING` from this client's point of view.
  final Map<String, String> proposalStatuses;

  /// proposal ids currently mid apply/cancel — lets the card show a
  /// spinner and disable its own buttons while the request is in flight.
  final Set<String> pendingProposalActions;

  AiChatState copyWith({
    String? sessionId,
    List<AiChatMessage>? messages,
    bool? isStartingSession,
    bool? isSending,
    ApiException? error,
    bool clearError = false,
    Map<String, String>? proposalStatuses,
    Set<String>? pendingProposalActions,
  }) => AiChatState(
    sessionId: sessionId ?? this.sessionId,
    messages: messages ?? this.messages,
    isStartingSession: isStartingSession ?? this.isStartingSession,
    isSending: isSending ?? this.isSending,
    error: clearError ? null : (error ?? this.error),
    proposalStatuses: proposalStatuses ?? this.proposalStatuses,
    pendingProposalActions: pendingProposalActions ?? this.pendingProposalActions,
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

  Future<void> applyProposal(String proposalId) => _resolveProposal(
    proposalId,
    (id) => _repository.applyProposal(id),
  );

  Future<void> cancelProposal(String proposalId) => _resolveProposal(
    proposalId,
    (id) => _repository.cancelProposal(id),
  );

  Future<void> _resolveProposal(
    String proposalId,
    Future<String> Function(String id) action,
  ) async {
    if (state.pendingProposalActions.contains(proposalId)) return;
    state = state.copyWith(
      pendingProposalActions: {...state.pendingProposalActions, proposalId},
      clearError: true,
    );
    try {
      final status = await action(proposalId);
      state = state.copyWith(
        proposalStatuses: {...state.proposalStatuses, proposalId: status},
        pendingProposalActions: state.pendingProposalActions.difference({proposalId}),
      );
    } on ApiException catch (e) {
      state = state.copyWith(
        pendingProposalActions: state.pendingProposalActions.difference({proposalId}),
        error: e,
      );
    }
  }
}
