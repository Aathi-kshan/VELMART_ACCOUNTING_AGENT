import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/features/ai/domain/ai_message.dart';
import 'package:velmart/features/ai/presentation/widgets/message_bubble.dart';

void main() {
  testWidgets('bubble width is capped by the parent, not the window', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 300,
            child: MessageBubble(
              message: AiChatMessage(role: AiMessageRole.user, content: 'Hello from the dock'),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final box = tester.renderObject<RenderBox>(find.text('Hello from the dock'));
    expect(box.size.width, lessThan(300));
  });
}
