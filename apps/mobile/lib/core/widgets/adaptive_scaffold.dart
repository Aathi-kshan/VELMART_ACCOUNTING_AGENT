import 'package:flutter/material.dart';

/// One entry in the shell's navigation — Home, Pages, More, and so on.
class AdaptiveDestination {
  const AdaptiveDestination({
    required this.icon,
    required this.selectedIcon,
    required this.label,
  });

  final IconData icon;
  final IconData selectedIcon;
  final String label;
}

/// One app, three layouts (plan section 22.4) — the breakpoints are exact:
///
/// | Width       | Shell                                                |
/// |-------------|-------------------------------------------------------|
/// | < 600dp     | Bottom navigation, single pane, FAB to add            |
/// | 600–1024dp  | Navigation rail, master-detail                        |
/// | > 1024dp    | Permanent sidebar, dense grid, keyboard shortcuts     |
///
/// This widget owns navigation chrome only — the "dense grid" and
/// "master-detail" content behaviour belongs to each screen's own
/// `LayoutBuilder` (see `record_list_screen.dart`), which already knows its
/// own content and shouldn't be duplicated here.
class AdaptiveScaffold extends StatelessWidget {
  const AdaptiveScaffold({
    super.key,
    required this.destinations,
    required this.selectedIndex,
    required this.onDestinationSelected,
    required this.body,
    this.title,
    this.floatingActionButton,
    this.actions,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final Widget? floatingActionButton;
  final List<Widget>? actions;

  static const double railBreakpoint = 600;
  static const double sidebarBreakpoint = 1024;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width >= sidebarBreakpoint) {
      return _SidebarLayout(
        destinations: destinations,
        selectedIndex: selectedIndex,
        onDestinationSelected: onDestinationSelected,
        title: title,
        actions: actions,
        body: body,
      );
    }
    if (width >= railBreakpoint) {
      return _RailLayout(
        destinations: destinations,
        selectedIndex: selectedIndex,
        onDestinationSelected: onDestinationSelected,
        title: title,
        actions: actions,
        body: body,
        floatingActionButton: floatingActionButton,
      );
    }
    return _BottomNavLayout(
      destinations: destinations,
      selectedIndex: selectedIndex,
      onDestinationSelected: onDestinationSelected,
      title: title,
      actions: actions,
      body: body,
      floatingActionButton: floatingActionButton,
    );
  }
}

class _BottomNavLayout extends StatelessWidget {
  const _BottomNavLayout({
    required this.destinations,
    required this.selectedIndex,
    required this.onDestinationSelected,
    required this.body,
    this.title,
    this.actions,
    this.floatingActionButton,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final List<Widget>? actions;
  final Widget? floatingActionButton;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: title == null ? null : AppBar(title: Text(title!), actions: actions),
      body: body,
      floatingActionButton: floatingActionButton,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: onDestinationSelected,
        destinations: [
          for (final destination in destinations)
            NavigationDestination(
              icon: Icon(destination.icon),
              selectedIcon: Icon(destination.selectedIcon),
              label: destination.label,
            ),
        ],
      ),
    );
  }
}

class _RailLayout extends StatelessWidget {
  const _RailLayout({
    required this.destinations,
    required this.selectedIndex,
    required this.onDestinationSelected,
    required this.body,
    this.title,
    this.actions,
    this.floatingActionButton,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final List<Widget>? actions;
  final Widget? floatingActionButton;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: title == null ? null : AppBar(title: Text(title!), actions: actions),
      body: Row(
        children: [
          NavigationRail(
            selectedIndex: selectedIndex,
            onDestinationSelected: onDestinationSelected,
            labelType: NavigationRailLabelType.all,
            leading: floatingActionButton == null
                ? null
                : Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: floatingActionButton,
                  ),
            destinations: [
              for (final destination in destinations)
                NavigationRailDestination(
                  icon: Icon(destination.icon),
                  selectedIcon: Icon(destination.selectedIcon),
                  label: Text(destination.label),
                ),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: body),
        ],
      ),
    );
  }
}

class _SidebarLayout extends StatelessWidget {
  const _SidebarLayout({
    required this.destinations,
    required this.selectedIndex,
    required this.onDestinationSelected,
    required this.body,
    this.title,
    this.actions,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final List<Widget>? actions;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          SizedBox(
            width: 240,
            child: Material(
              color: Theme.of(context).colorScheme.surfaceContainerLow,
              child: Column(
                children: [
                  if (title != null)
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text(title!, style: Theme.of(context).textTheme.titleLarge),
                      ),
                    ),
                  Expanded(
                    child: ListView(
                      children: [
                        for (var i = 0; i < destinations.length; i++)
                          ListTile(
                            leading: Icon(
                              i == selectedIndex
                                  ? destinations[i].selectedIcon
                                  : destinations[i].icon,
                            ),
                            title: Text(destinations[i].label),
                            selected: i == selectedIndex,
                            onTap: () => onDestinationSelected(i),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const VerticalDivider(width: 1),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (actions != null && actions!.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    child: Row(mainAxisAlignment: MainAxisAlignment.end, children: actions!),
                  ),
                Expanded(child: body),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
