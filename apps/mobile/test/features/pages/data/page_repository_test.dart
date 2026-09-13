import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:velmart/core/network/api_exception.dart';
import 'package:velmart/features/pages/data/page_repository.dart';

class MockDio extends Mock implements Dio {}

class _FakeRequestOptions extends Fake implements RequestOptions {}

void main() {
  setUpAll(() {
    registerFallbackValue(_FakeRequestOptions());
    registerFallbackValue(Options());
  });

  // Mirrors apps/api/tests/test_record_validation.py's 422 shape and
  // test_optimistic_locking.py's 409 shape — the client must decode both
  // the same way the server actually sends them, not how a generic REST
  // client might assume errors look.
  group('ApiException.fromDio', () {
    DioException dioError({required int status, required Map<String, dynamic> body}) {
      final requestOptions = RequestOptions(path: '/pages/1/records');
      return DioException(
        requestOptions: requestOptions,
        response: Response(requestOptions: requestOptions, statusCode: status, data: body),
      );
    }

    test('decodes a 422 into field errors keyed by column', () {
      final exception = ApiException.fromDio(
        dioError(
          status: 422,
          body: {
            'type': 'https://velmart.app/errors/validation-failed',
            'title': 'Validation failed',
            'status': 422,
            'detail': "The record data did not match this page's schema.",
            'code': 'VALIDATION_FAILED',
            'errors': [
              {'loc': ['category'], 'msg': "Input should be 'Rent' or 'Electricity'"},
              {'loc': ['amount'], 'msg': 'must not be negative'},
            ],
          },
        ),
      );

      expect(exception.isValidationFailure, isTrue);
      expect(exception.code, 'VALIDATION_FAILED');
      expect(exception.fieldErrors['category'], "Input should be 'Rent' or 'Electricity'");
      expect(exception.fieldErrors['amount'], 'must not be negative');
    });

    test('strips framework path segments from loc, keeping the column key', () {
      final exception = ApiException.fromDio(
        dioError(
          status: 422,
          body: {
            'code': 'VALIDATION_FAILED',
            'detail': 'bad',
            'errors': [
              {'loc': ['body', 'data', 'amount'], 'msg': 'bad amount'},
            ],
          },
        ),
      );
      expect(exception.fieldErrors.keys, ['amount']);
    });

    test('decodes a 409 VERSION_CONFLICT and exposes current_version', () {
      final exception = ApiException.fromDio(
        dioError(
          status: 409,
          body: {
            'code': 'VERSION_CONFLICT',
            'detail': 'This record has changed since version 3.',
            'current_version': 4,
          },
        ),
      );
      expect(exception.isVersionConflict, isTrue);
      expect(exception.currentVersion, 4);
    });

    test('falls back to a generic message when the body is not problem+json', () {
      final requestOptions = RequestOptions(path: '/pages');
      final exception = ApiException.fromDio(
        DioException(
          requestOptions: requestOptions,
          type: DioExceptionType.connectionError,
        ),
      );
      expect(exception.code, isEmpty);
      expect(exception.detail, isNotEmpty);
    });

    test('a 404 with no field errors carries no fieldErrors entries', () {
      final exception = ApiException.fromDio(
        dioError(status: 404, body: {'code': 'NOT_FOUND', 'detail': 'No such page.'}),
      );
      expect(exception.isNotFound, isTrue);
      expect(exception.fieldErrors, isEmpty);
    });
  });

  group('PageRepository.createRecord', () {
    test('sends the same client_uuid as the Idempotency-Key header', () async {
      final dio = MockDio();
      final repository = PageRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/pages/page-1/records');

      when(
        () => dio.post<Map<String, dynamic>>(
          any(),
          data: any(named: 'data'),
          options: any(named: 'options'),
        ),
      ).thenAnswer(
        (invocation) async => Response(
          requestOptions: requestOptions,
          statusCode: 201,
          data: {
            'id': 'rec-1',
            'company_id': 'company-1',
            'page_id': 'page-1',
            'store_id': null,
            'occurred_at': '2026-09-07T10:00:00+05:30',
            'business_date': '2026-09-07',
            'status': 'ACTIVE',
            'data': <String, dynamic>{},
            'needs_review': false,
            'version': 1,
            'created_by': 'user-1',
            'updated_by': null,
          },
        ),
      );

      await repository.createRecord(
        'page-1',
        occurredAt: '2026-09-07T10:00:00+05:30',
        data: {},
      );

      final captured = verify(
        () => dio.post<Map<String, dynamic>>(
          captureAny(),
          data: captureAny(named: 'data'),
          options: captureAny(named: 'options'),
        ),
      ).captured;

      final sentData = captured[1] as Map<String, dynamic>;
      final sentOptions = captured[2] as Options;
      expect(sentData['client_uuid'], isNotEmpty);
      expect(sentOptions.headers?['Idempotency-Key'], sentData['client_uuid']);
    });
  });

  group('PageRepository.updateRecord', () {
    test('sends the version as an If-Match header', () async {
      final dio = MockDio();
      final repository = PageRepository(dio: dio);
      final requestOptions = RequestOptions(path: '/records/rec-1');

      when(
        () => dio.patch<Map<String, dynamic>>(
          any(),
          data: any(named: 'data'),
          options: any(named: 'options'),
        ),
      ).thenAnswer(
        (invocation) async => Response(
          requestOptions: requestOptions,
          statusCode: 200,
          data: {
            'id': 'rec-1',
            'company_id': 'company-1',
            'page_id': 'page-1',
            'store_id': null,
            'occurred_at': '2026-09-07T10:00:00+05:30',
            'business_date': '2026-09-07',
            'status': 'ACTIVE',
            'data': <String, dynamic>{},
            'needs_review': false,
            'version': 4,
            'created_by': 'user-1',
            'updated_by': 'user-1',
          },
        ),
      );

      await repository.updateRecord('rec-1', version: 3, data: {});

      final captured = verify(
        () => dio.patch<Map<String, dynamic>>(
          any(),
          data: any(named: 'data'),
          options: captureAny(named: 'options'),
        ),
      ).captured;

      final sentOptions = captured.single as Options;
      expect(sentOptions.headers?['If-Match'], '3');
    });
  });
}
