import 'package:dio/dio.dart';

import '../../../core/network/api_exception.dart';
import '../domain/ai_message.dart';

/// `POST /ai/sessions` / `POST /ai/sessions/{id}/messages` (plan section
/// 16.2, P7.6; docs/API.md §9). Thin, like every other repository in this
/// app: no decisions, just send and parse — Owner-only enforcement is the
/// server's job (`require_owner`), not this client's.
class AiRepository {
  AiRepository({required this.dio});

  final Dio dio;

  Future<String> startSession() => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>('/ai/sessions');
    return response.data!['id'] as String;
  });

  Future<AiChatMessage> sendMessage(String sessionId, String message) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/ai/sessions/$sessionId/messages',
      data: {'message': message},
    );
    return AiChatMessage.fromResponseJson(response.data!);
  });
}
