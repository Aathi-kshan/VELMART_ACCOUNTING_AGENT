import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:velmart/core/theme/app_colors.dart';
import 'package:velmart/core/theme/app_theme.dart';
import 'package:velmart/features/ai/application/ai_providers.dart';
import 'package:velmart/features/ai/data/ai_repository.dart';
import 'package:velmart/features/ai/presentation/ai_chat_screen.dart';

class MockAiRepository extends Mock implements AiRepository {}

// Regression test: a blanket `foregroundColor` on the app-wide
// `iconButtonTheme` was muting every `IconButton.filled` (including this
// send button) to grey-on-green instead of the brand white-on-green —
// a contrast failure design.md §22.2 explicitly calls out. Proves the send
// button actually resolves to the deep brand green with a white icon under
// the real app theme, not just that it compiles.
void main() {
  testWidgets('the send button is brand green with a white icon', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          aiChatControllerProvider.overrideWith(
            (ref) => AiChatController(MockAiRepository()),
          ),
        ],
        child: MaterialApp(theme: AppTheme.light(), home: const Scaffold(body: AiChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    final iconButton = tester.widget<IconButton>(find.widgetWithIcon(IconButton, Icons.send));
    final resolvedBackground = iconButton.style!.backgroundColor!.resolve({});
    final resolvedForeground = iconButton.style!.foregroundColor!.resolve({});

    expect(resolvedBackground, AppColors.brandPrimaryDark);
    expect(resolvedForeground, AppColors.textOnBrand);
  });
}
