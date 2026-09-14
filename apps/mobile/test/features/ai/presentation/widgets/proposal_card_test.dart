import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/features/ai/application/ai_providers.dart';
import 'package:velmart/features/ai/data/ai_repository.dart';
import 'package:velmart/features/ai/domain/ai_message.dart';
import 'package:velmart/features/ai/presentation/widgets/proposal_card.dart';

/// P8 Lite Slice 8 — the proposal card must never let the Owner confuse
/// the current value with the proposed one, and its buttons must call the
/// right repository method exactly once.
class _FakeAiRepository extends AiRepository {
  _FakeAiRepository() : super(dio: Dio());

  int applyCalls = 0;
  int cancelCalls = 0;
  String? lastAppliedId;
  String? lastCancelledId;

  @override
  Future<String> applyProposal(String proposalId) async {
    applyCalls++;
    lastAppliedId = proposalId;
    return 'APPLIED';
  }

  @override
  Future<String> cancelProposal(String proposalId) async {
    cancelCalls++;
    lastCancelledId = proposalId;
    return 'CANCELLED';
  }
}

AiProposal _proposal({String id = 'proposal-1'}) => AiProposal(
  id: id,
  summary: 'Update Staff — salary',
  expiresAt: DateTime.now().add(const Duration(minutes: 8)),
  page: 'Staff',
  changes: const [AiProposalChange(column: 'salary', before: '60000.00', after: '75000.00')],
);

Widget _pumpable(AiProposal proposal, {_FakeAiRepository? repository}) {
  return ProviderScope(
    overrides: [
      if (repository != null) aiRepositoryProvider.overrideWithValue(repository),
    ],
    child: MaterialApp(
      home: Scaffold(body: ProposalCard(proposal: proposal)),
    ),
  );
}

void main() {
  testWidgets('shows both the current and proposed value, clearly distinguishable', (
    tester,
  ) async {
    await tester.pumpWidget(_pumpable(_proposal()));

    expect(find.text('60000.00'), findsOneWidget);
    expect(find.text('75000.00'), findsOneWidget);

    final beforeText = tester.widget<Text>(find.text('60000.00'));
    final afterText = tester.widget<Text>(find.text('75000.00'));
    expect(beforeText.style?.decoration, TextDecoration.lineThrough);
    expect(afterText.style?.fontWeight, FontWeight.bold);
    expect(afterText.style?.decoration, isNot(TextDecoration.lineThrough));
  });

  testWidgets('shows the column name and an expiry label while pending', (tester) async {
    await tester.pumpWidget(_pumpable(_proposal()));

    expect(find.text('salary'), findsOneWidget);
    expect(find.textContaining('Expires in'), findsOneWidget);
    expect(find.text('CANCEL'), findsOneWidget);
    expect(find.text('UPDATE'), findsOneWidget);
  });

  testWidgets('tapping UPDATE calls applyProposal exactly once with the right id', (tester) async {
    final repository = _FakeAiRepository();
    await tester.pumpWidget(_pumpable(_proposal(id: 'proposal-42'), repository: repository));

    await tester.tap(find.text('UPDATE'));
    await tester.pump();
    await tester.pump();

    expect(repository.applyCalls, 1);
    expect(repository.cancelCalls, 0);
    expect(repository.lastAppliedId, 'proposal-42');
  });

  testWidgets('tapping CANCEL calls cancelProposal exactly once with the right id', (
    tester,
  ) async {
    final repository = _FakeAiRepository();
    await tester.pumpWidget(_pumpable(_proposal(id: 'proposal-42'), repository: repository));

    await tester.tap(find.text('CANCEL'));
    await tester.pump();
    await tester.pump();

    expect(repository.cancelCalls, 1);
    expect(repository.applyCalls, 0);
    expect(repository.lastCancelledId, 'proposal-42');
  });

  testWidgets('after applying, the buttons are replaced by a resolved badge', (tester) async {
    final repository = _FakeAiRepository();
    await tester.pumpWidget(_pumpable(_proposal(), repository: repository));

    await tester.tap(find.text('UPDATE'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Applied'), findsOneWidget);
    expect(find.text('UPDATE'), findsNothing);
    expect(find.text('CANCEL'), findsNothing);
  });
}
