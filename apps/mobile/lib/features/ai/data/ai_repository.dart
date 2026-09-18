import 'package:dio/dio.dart';

import '../../../core/network/api_exception.dart';
import '../domain/ai_message.dart';

/// `POST /ai/sessions` / `POST /ai/sessions/{id}/messages` /
/// `POST /ai/proposals/{id}/apply` / `.../cancel` (plan section 16.2,
/// P7.6, P8 Lite; docs/API.md §9). Thin, like every other repository in
/// this app: no decisions, just send and parse — Owner-only enforcement,
/// version checks, and expiry are all the server's job, not this client's.
class AiRepository {
  AiRepository({required this.dio});

  final Dio dio;

  Future<String> startSession() => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>('/ai/sessions');
    return response.data!['id'] as String;
  });

  Future<AiChatMessage> sendMessage(String sessionId, String message) =>
      mapApiErrors(() async {
        final response = await dio.post<Map<String, dynamic>>(
          '/ai/sessions/$sessionId/messages',
          data: {'message': message},
        );
        return AiChatMessage.fromResponseJson(response.data!);
      });

  /// Returns the proposal's new status (`"APPLIED"`) — a stale-version
  /// conflict or an expired proposal surfaces as an [ApiException] with
  /// `code` `PROPOSAL_STALE`/`PROPOSAL_EXPIRED`, for the caller to show.
  Future<String> applyProposal(String proposalId) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/ai/proposals/$proposalId/apply',
    );
    return response.data!['status'] as String;
  });

  /// Returns the proposal's new status (`"CANCELLED"`).
  Future<String> cancelProposal(String proposalId) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/ai/proposals/$proposalId/cancel',
    );
    return response.data!['status'] as String;
  });
}
