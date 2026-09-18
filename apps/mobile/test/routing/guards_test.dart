import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/features/auth/application/auth_controller.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/routing/guards.dart';

void main() {
  const owner = User(
    id: 'o',
    companyId: 'c',
    fullName: 'Owner',
    email: 'o@x.lk',
    role: UserRole.owner,
    storeIds: [],
  );
  const manager = User(
    id: 'm',
    companyId: 'c',
    fullName: 'Manager',
    email: 'm@x.lk',
    role: UserRole.manager,
    storeIds: [],
  );

  test('record list location is only the records index', () {
    expect(isRecordListLocation('/pages/abc/records'), isTrue);
    expect(isRecordListLocation('/pages/abc/records/new'), isFalse);
    expect(isRecordListLocation('/pages'), isFalse);
    expect(isRecordListLocation('/home'), isFalse);
  });

  test('manager is redirected off owner-only screens', () {
    final state = AuthAuthenticated(manager);
    expect(authRedirect(state, '/ai'), '/home');
    expect(authRedirect(state, '/users'), '/home');
    expect(authRedirect(state, '/pages/new'), '/home');
    expect(authRedirect(state, '/pages/p1/columns'), '/home');
    expect(authRedirect(state, '/pages/p1/access'), '/home');
    expect(authRedirect(state, '/records/r1/edit'), '/home');
    expect(authRedirect(state, '/home'), isNull);
    expect(authRedirect(state, '/pages'), isNull);
    expect(authRedirect(state, '/pages/p1/records'), isNull);
  });

  test('owner is not redirected off owner-only screens', () {
    final state = AuthAuthenticated(owner);
    expect(authRedirect(state, '/ai'), isNull);
    expect(authRedirect(state, '/users'), isNull);
    expect(authRedirect(state, '/login'), '/home');
  });
}
