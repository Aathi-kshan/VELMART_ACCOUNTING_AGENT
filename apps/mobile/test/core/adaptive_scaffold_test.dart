import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/adaptive_scaffold.dart';

// Plan section 22.4's three breakpoints, checked at representative widths:
// bottom nav below 600dp, a rail between 600 and 1024dp, a permanent
// sidebar above 1024dp.
void main() {
  const destinations = [
    AdaptiveDestination(icon: Icons.home_outlined, selectedIcon: Icons.home, label: 'Home'),
    AdaptiveDestination(icon: Icons.list_outlined, selectedIcon: Icons.list, label: 'Pages'),
  ];

  Widget buildAt(double width) {
    return MediaQuery(
      data: MediaQueryData(size: Size(width, 800)),
      child: MaterialApp(
        home: AdaptiveScaffold(
          destinations: destinations,
          selectedIndex: 0,
          onDestinationSelected: (_) {},
          body: const Text('content'),
        ),
      ),
    );
  }

  testWidgets('renders a bottom NavigationBar below 600dp', (tester) async {
    await tester.pumpWidget(buildAt(500));
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.text('content'), findsOneWidget);
  });

  testWidgets('renders a NavigationRail between 600 and 1024dp', (tester) async {
    await tester.pumpWidget(buildAt(800));
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });

  testWidgets('renders a permanent sidebar above 1024dp', (tester) async {
    await tester.pumpWidget(buildAt(1200));
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.byType(NavigationBar), findsNothing);
    // The sidebar lists destinations as ListTiles rather than a nav widget.
    expect(find.widgetWithText(ListTile, 'Home'), findsOneWidget);
    expect(find.widgetWithText(ListTile, 'Pages'), findsOneWidget);
  });

  testWidgets('tapping a destination invokes the callback', (tester) async {
    var selected = -1;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(500, 800)),
        child: MaterialApp(
          home: AdaptiveScaffold(
            destinations: destinations,
            selectedIndex: 0,
            onDestinationSelected: (index) => selected = index,
            body: const SizedBox(),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Pages'));
    await tester.pumpAndSettle();
    expect(selected, 1);
  });
}
