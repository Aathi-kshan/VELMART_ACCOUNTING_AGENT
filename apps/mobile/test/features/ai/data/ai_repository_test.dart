import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:velmart/core/network/api_exception.dart';
import 'package:velmart/features/ai/data/ai_repository.dart';
import 'package:velmart/features/ai/domain/ai_message.dart';

class MockDio extends Mock implements Dio {}

class _FakeRequestOptions extends Fake implements RequestOptions {}

void main() {
  setUpAll(() {
    registerFallbackValue(_FakeRequestOptions());
  });

  group('AiRepository.startSession', () {
    test('returns the new session id', () async {
      final dio = MockDio();
      final repository = AiRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/ai/sessions');

      when(() => dio.post<Map<String, dynamic>>('/ai/sessions')).thenAnswer(
        (_) async => Response(
          requestOptions: requestOptions,
          statusCode: 201,
          data: {'id': 'session-1', 'started_at': '2026-09-14T09:00:00+05:30'},
        ),
      );

      final id = await repository.startSession();

      expect(id, 'session-1');
    });
  });

  group('AiRepository.sendMessage', () {
    test('parses a real API response shape, including provenance and tool_calls', () async {
      final dio = MockDio();
      final repository = AiRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/ai/sessions/session-1/messages');

      when(
        () => dio.post<Map<String, dynamic>>(
          '/ai/sessions/session-1/messages',
          data: {'message': 'How much did we spend on electricity this month?'},
        ),
      ).thenAnswer(
        (_) async => Response(
          requestOptions: requestOptions,
          statusCode: 200,
          data: {
            'message_id': 'msg-1',
            'answer':
                'Rs. 587,400 — from 23 records in Expenses, 1-30 September, '
                'where Category is Electricity.',
            'provenance': [
              {
                'page': 'Expenses',
                'record_count': 23,
                'from': '2026-09-01',
                'to': '2026-09-30',
              },
            ],
            'tool_calls': [
              {'tool': 'aggregate_records', 'duration_ms': 34},
            ],
            'proposal': null,
            'cost_usd': '0.0042',
            'partial': false,
          },
        ),
      );

      final reply = await repository.sendMessage(
        'session-1',
        'How much did we spend on electricity this month?',
      );

      expect(reply.role, AiMessageRole.assistant);
      expect(reply.content, contains('Rs. 587,400'));
      expect(reply.provenance, hasLength(1));
      expect(reply.provenance.single.page, 'Expenses');
      expect(reply.provenance.single.recordCount, 23);
      expect(reply.provenance.single.dateFrom, '2026-09-01');
      expect(reply.toolCalls, hasLength(1));
      expect(reply.toolCalls.single.tool, 'aggregate_records');
      expect(reply.toolCalls.single.durationMs, 34);
      expect(reply.costUsd, '0.0042');
      expect(reply.partial, isFalse);
    });

    test('a partial answer with no provenance parses to empty lists', () async {
      final dio = MockDio();
      final repository = AiRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/ai/sessions/session-1/messages');

      when(
        () => dio.post<Map<String, dynamic>>(
          '/ai/sessions/session-1/messages',
          data: {'message': 'irrelevant'},
        ),
      ).thenAnswer(
        (_) async => Response(
          requestOptions: requestOptions,
          statusCode: 200,
          data: {
            'message_id': 'msg-2',
            'answer': 'I ran out of time gathering data for this answer.',
            'provenance': <dynamic>[],
            'tool_calls': <dynamic>[],
            'proposal': null,
            'cost_usd': '0.0010',
            'partial': true,
          },
        ),
      );

      final reply = await repository.sendMessage('session-1', 'irrelevant');

      expect(reply.provenance, isEmpty);
      expect(reply.toolCalls, isEmpty);
      expect(reply.partial, isTrue);
    });

    test('parses a non-null proposal with its field changes', () async {
      final dio = MockDio();
      final repository = AiRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/ai/sessions/session-1/messages');

      when(
        () => dio.post<Map<String, dynamic>>(
          '/ai/sessions/session-1/messages',
          data: {'message': "Change John's salary to 75000."},
        ),
      ).thenAnswer(
        (_) async => Response(
          requestOptions: requestOptions,
          statusCode: 200,
          data: {
            'message_id': 'msg-3',
            'answer': "I've prepared an update to John's salary.",
            'provenance': <dynamic>[],
            'tool_calls': <dynamic>[],
            'proposal': {
              'id': 'proposal-1',
              'summary': 'Update Staff',
              'expires_at': DateTime.now().add(const Duration(minutes: 10)).toIso8601String(),
              'page': 'Staff',
              'changes': [
                {'column': 'salary', 'before': '60000.00', 'after': '75000.00'},
              ],
            },
            'cost_usd': '0.0031',
            'partial': false,
          },
        ),
      );

      final reply = await repository.sendMessage('session-1', "Change John's salary to 75000.");

      expect(reply.proposal, isNotNull);
      expect(reply.proposal!.id, 'proposal-1');
      expect(reply.proposal!.page, 'Staff');
      expect(reply.proposal!.changes, hasLength(1));
      expect(reply.proposal!.changes.single.column, 'salary');
      expect(reply.proposal!.changes.single.before, '60000.00');
      expect(reply.proposal!.changes.single.after, '75000.00');
      expect(reply.proposal!.isExpired, isFalse);
    });
  });

  group('AiRepository.applyProposal', () {
    test('posts to the apply endpoint and returns the new status', () async {
      final dio = MockDio();
      final repository = AiRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/ai/proposals/proposal-1/apply');

      when(() => dio.post<Map<String, dynamic>>('/ai/proposals/proposal-1/apply')).thenAnswer(
        (_) async => Response(
          requestOptions: requestOptions,
          statusCode: 200,
          data: {'id': 'proposal-1', 'status': 'APPLIED'},
        ),
      );

      final status = await repository.applyProposal('proposal-1');

      expect(status, 'APPLIED');
    });

    test('a stale-version conflict maps to ApiException.isVersionConflict', () async {
      final dio = MockDio();
      final repository = AiRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/ai/proposals/proposal-1/apply');

      when(() => dio.post<Map<String, dynamic>>('/ai/proposals/proposal-1/apply')).thenThrow(
        DioException(
          requestOptions: requestOptions,
          response: Response(
            requestOptions: requestOptions,
            statusCode: 409,
            data: {
              'code': 'PROPOSAL_STALE',
              'detail': 'This record has changed since the proposal was created.',
              'current_version': 4,
            },
          ),
        ),
      );

      await expectLater(
        () => repository.applyProposal('proposal-1'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', 'PROPOSAL_STALE')
              .having((e) => e.currentVersion, 'currentVersion', 4),
        ),
      );
    });
  });

  group('AiRepository.cancelProposal', () {
    test('posts to the cancel endpoint and returns the new status', () async {
      final dio = MockDio();
      final repository = AiRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/ai/proposals/proposal-1/cancel');

      when(() => dio.post<Map<String, dynamic>>('/ai/proposals/proposal-1/cancel')).thenAnswer(
        (_) async => Response(
          requestOptions: requestOptions,
          statusCode: 200,
          data: {'id': 'proposal-1', 'status': 'CANCELLED'},
        ),
      );

      final status = await repository.cancelProposal('proposal-1');

      expect(status, 'CANCELLED');
    });
  });
}
