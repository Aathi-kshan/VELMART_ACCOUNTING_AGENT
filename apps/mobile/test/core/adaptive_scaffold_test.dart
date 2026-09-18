import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/adaptive_scaffold.dart';

void main() {
  const twoTabs = [
    AdaptiveDestination(icon: Icons.home_outlined, selectedIcon: Icons.home, label: 'Home'),
    AdaptiveDestination(icon: Icons.list_outlined, selectedIcon: Icons.list, label: 'Pages'),
  ];

  const fiveSlotTabs = [
    AdaptiveDestination(icon: Icons.home_outlined, selectedIcon: Icons.home, label: 'Home'),
    AdaptiveDestination(
      icon: Icons.table_chart_outlined,
      selectedIcon: Icons.table_chart,
      label: 'Pages',
    ),
    AdaptiveDestination(icon: Icons.auto_awesome, selectedIcon: Icons.auto_awesome, label: 'AI'),
    AdaptiveDestination(icon: Icons.menu, selectedIcon: Icons.menu, label: 'More'),
  ];

  Widget buildAt({
    required double width,
    List<AdaptiveDestination> destinations = twoTabs,
    VoidCallback? centerAction,
    List<AdaptiveDestination> ownerDestinations = const [],
    int? selectedOwnerIndex,
    Widget? trailingPane,
  }) {
    return MediaQuery(
      data: MediaQueryData(size: Size(width, 800)),
      child: MaterialApp(
        home: AdaptiveScaffold(
          destinations: destinations,
          selectedIndex: 0,
          onDestinationSelected: (_) {},
          centerAction: centerAction,
          ownerDestinations: ownerDestinations,
          selectedOwnerIndex: selectedOwnerIndex,
          trailingPane: trailingPane,
          body: const Text('content'),
        ),
      ),
    );
  }

  testWidgets('renders a 5-slot custom bar with center + below 600dp', (tester) async {
    var plusTaps = 0;
    await tester.pumpWidget(
      buildAt(width: 500, destinations: fiveSlotTabs, centerAction: () => plusTaps++),
    );

    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Pages'), findsOneWidget);
    expect(find.text('AI'), findsOneWidget);
    expect(find.text('More'), findsOneWidget);
    expect(find.byKey(const Key('nav-center-plus')), findsOneWidget);
    expect(find.text('content'), findsOneWidget);

    await tester.tap(find.byKey(const Key('nav-center-plus')));
    expect(plusTaps, 1);
  });

  testWidgets('three-tab bar puts Add between Pages and More', (tester) async {
    const managerTabs = [
      AdaptiveDestination(icon: Icons.home_outlined, selectedIcon: Icons.home, label: 'Home'),
      AdaptiveDestination(
        icon: Icons.table_chart_outlined,
        selectedIcon: Icons.table_chart,
        label: 'Pages',
      ),
      AdaptiveDestination(icon: Icons.menu, selectedIcon: Icons.menu, label: 'More'),
    ];
    await tester.pumpWidget(
      buildAt(width: 390, destinations: managerTabs, centerAction: () {}),
    );

    final home = tester.getCenter(find.text('Home'));
    final pages = tester.getCenter(find.text('Pages'));
    final add = tester.getCenter(find.text('Add'));
    final more = tester.getCenter(find.text('More'));
    expect(home.dx, lessThan(pages.dx));
    expect(pages.dx, lessThan(add.dx));
    expect(add.dx, lessThan(more.dx));
  });

  testWidgets('renders a NavigationRail between 600 and 1024dp', (tester) async {
    await tester.pumpWidget(buildAt(width: 800, centerAction: () {}));
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byKey(const Key('nav-center-plus')), findsOneWidget);
  });

  testWidgets('renders a branded sidebar above 1024dp', (tester) async {
    await tester.pumpWidget(buildAt(width: 1200));
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.widgetWithText(ListTile, 'Home'), findsOneWidget);
    expect(find.widgetWithText(ListTile, 'Pages'), findsOneWidget);
    expect(find.text('Velmart'), findsOneWidget);
  });

  testWidgets('expanded sidebar lists OWNER destinations and a 300dp AI pane', (tester) async {
    await tester.pumpWidget(
      buildAt(
        width: 1280,
        ownerDestinations: const [
          AdaptiveDestination(
            icon: Icons.person_add_outlined,
            selectedIcon: Icons.person_add,
            label: 'Users',
          ),
          AdaptiveDestination(icon: Icons.history, selectedIcon: Icons.history, label: 'Audit'),
        ],
        selectedOwnerIndex: 0,
        trailingPane: const SizedBox(width: 300, child: Text('Ask Velmart')),
      ),
    );

    expect(find.text('OWNER'), findsOneWidget);
    expect(find.widgetWithText(ListTile, 'Users'), findsOneWidget);
    expect(find.widgetWithText(ListTile, 'Audit'), findsOneWidget);
    expect(find.text('Ask Velmart'), findsOneWidget);

    final usersTile = tester.widget<ListTile>(find.widgetWithText(ListTile, 'Users'));
    expect(usersTile.selected, isTrue);
  });

  testWidgets('tapping a destination invokes the callback', (tester) async {
    var selected = -1;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(500, 800)),
        child: MaterialApp(
          home: AdaptiveScaffold(
            destinations: twoTabs,
            selectedIndex: 0,
            onDestinationSelected: (index) => selected = index,
            centerAction: () {},
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
