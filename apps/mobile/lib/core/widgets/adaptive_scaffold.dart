import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radii.dart';
import '../theme/app_spacing.dart';
import 'velmart_logo.dart';

class AdaptiveDestination {
  const AdaptiveDestination({
    required this.icon,
    required this.selectedIcon,
    required this.label,
    this.path,
  });

  final IconData icon;
  final IconData selectedIcon;
  final String label;
  final String? path;
}

/// One app, three layouts. Breakpoints are exact (design.md §21.1):
///
/// | Width       | Shell |
/// |-------------|-------|
/// | < 600dp     | 5-slot bar with center + |
/// | 600–1024dp  | Navigation rail |
/// | > 1024dp    | Sidebar + body + optional AI pane |
class AdaptiveScaffold extends StatelessWidget {
  const AdaptiveScaffold({
    super.key,
    required this.destinations,
    required this.selectedIndex,
    required this.onDestinationSelected,
    required this.body,
    this.title,
    this.actions,
    this.footer,
    this.ownerDestinations = const [],
    this.onOwnerDestinationSelected,
    this.selectedOwnerIndex,
    this.centerAction,
    this.centerActionTooltip = 'Add record',
    this.showNavigation = true,
    this.trailingPane,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final List<Widget>? actions;
  final Widget? footer;
  final List<AdaptiveDestination> ownerDestinations;
  final ValueChanged<int>? onOwnerDestinationSelected;
  final int? selectedOwnerIndex;
  final VoidCallback? centerAction;
  final String centerActionTooltip;
  final bool showNavigation;
  final Widget? trailingPane;

  static const double railBreakpoint = 600;
  /// Dense record table from the rail breakpoint up. 600–1024 still uses
  /// the rail; the old master-detail split in that band duplicated dates
  /// and left an empty "Select a record" pane.
  static const double tableBreakpoint = railBreakpoint;
  static const double sidebarBreakpoint = 1024;
  static const double sidebarWidth = 212;
  static const double aiPaneWidth = 300;

  static bool isCompact(double width) => width < railBreakpoint;
  static bool isMedium(double width) => width >= railBreakpoint && width < sidebarBreakpoint;
  static bool isExpanded(double width) => width >= sidebarBreakpoint;
  static bool isTableLayout(double width) => width >= tableBreakpoint;

  @override
  Widget build(BuildContext context) {
    if (!showNavigation) {
      return Scaffold(backgroundColor: AppColors.background, body: body);
    }

    final width = MediaQuery.sizeOf(context).width;
    if (width >= sidebarBreakpoint) {
      return _SidebarLayout(
        destinations: destinations,
        selectedIndex: selectedIndex,
        onDestinationSelected: onDestinationSelected,
        title: title,
        actions: actions,
        body: body,
        footer: footer,
        ownerDestinations: ownerDestinations,
        onOwnerDestinationSelected: onOwnerDestinationSelected,
        selectedOwnerIndex: selectedOwnerIndex,
        trailingPane: trailingPane,
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
        centerAction: centerAction,
        centerActionTooltip: centerActionTooltip,
      );
    }
    return _BottomNavLayout(
      destinations: destinations,
      selectedIndex: selectedIndex,
      onDestinationSelected: onDestinationSelected,
      title: title,
      actions: actions,
      body: body,
      centerAction: centerAction,
      centerActionTooltip: centerActionTooltip,
    );
  }
}

class _CenterPlus extends StatelessWidget {
  const _CenterPlus({required this.onPressed, required this.tooltip, this.size = 48});

  final VoidCallback? onPressed;
  final String tooltip;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: AppColors.brandPrimaryDark,
        shape: const CircleBorder(),
        elevation: 3,
        shadowColor: AppColors.brandPrimaryDeep.withValues(alpha: 0.3),
        child: InkWell(
          key: const Key('nav-center-plus'),
          customBorder: const CircleBorder(),
          onTap: onPressed,
          child: SizedBox(
            width: size,
            height: size,
            child: const Icon(Icons.add, color: AppColors.textOnBrand),
          ),
        ),
      ),
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
    this.centerAction,
    required this.centerActionTooltip,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final List<Widget>? actions;
  final VoidCallback? centerAction;
  final String centerActionTooltip;

  @override
  Widget build(BuildContext context) {
    // Extra destination goes left so a 3-tab Manager bar is
    // Home | Pages | Add | More — not Home | + | Pages | More.
    final mid = (destinations.length + 1) ~/ 2;
    final left = destinations.take(mid).toList();
    final right = destinations.skip(mid).toList();

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: title == null ? null : AppBar(title: Text(title!), actions: actions),
      body: body,
      bottomNavigationBar: Material(
        color: AppColors.surface,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Divider(height: 1),
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(4, 4, 4, 0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    for (var i = 0; i < left.length; i++)
                      Expanded(
                        child: _TabButton(
                          destination: left[i],
                          selected: selectedIndex == i,
                          onTap: () => onDestinationSelected(i),
                        ),
                      ),
                    Expanded(
                      child: _AddTab(
                        onPressed: centerAction,
                        tooltip: centerActionTooltip,
                      ),
                    ),
                    for (var i = 0; i < right.length; i++)
                      Expanded(
                        child: _TabButton(
                          destination: right[i],
                          selected: selectedIndex == mid + i,
                          onTap: () => onDestinationSelected(mid + i),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AddTab extends StatelessWidget {
  const _AddTab({required this.onPressed, required this.tooltip});

  final VoidCallback? onPressed;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        key: const Key('nav-center-plus'),
        customBorder: const CircleBorder(),
        onTap: onPressed,
        child: SizedBox(
          height: 52,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: const BoxDecoration(
                  color: AppColors.brandPrimaryDark,
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.add, size: 18, color: AppColors.textOnBrand),
              ),
              const SizedBox(height: 4),
              Text(
                'Add',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: AppColors.brandPrimaryDark,
                  fontWeight: FontWeight.w600,
                  fontSize: 10.5,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TabButton extends StatelessWidget {
  const _TabButton({
    required this.destination,
    required this.selected,
    required this.onTap,
  });

  final AdaptiveDestination destination;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.brandPrimaryDark : AppColors.textTertiary;
    return InkWell(
      onTap: onTap,
      child: SizedBox(
        height: 52,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              selected ? destination.selectedIcon : destination.icon,
              size: 22,
              color: color,
            ),
            const SizedBox(height: 4),
            Text(
              destination.label,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: color,
                fontWeight: FontWeight.w600,
                fontSize: 10.5,
              ),
            ),
          ],
        ),
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
    this.centerAction,
    required this.centerActionTooltip,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final List<Widget>? actions;
  final VoidCallback? centerAction;
  final String centerActionTooltip;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: title == null ? null : AppBar(title: Text(title!), actions: actions),
      body: Row(
        children: [
          NavigationRail(
            backgroundColor: AppColors.surface,
            selectedIndex: selectedIndex.clamp(0, destinations.length - 1),
            onDestinationSelected: onDestinationSelected,
            labelType: NavigationRailLabelType.all,
            leading: centerAction == null
                ? const SizedBox(height: AppSpacing.md)
                : Padding(
                    padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
                    child: _CenterPlus(
                      onPressed: centerAction,
                      tooltip: centerActionTooltip,
                      size: 44,
                    ),
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
    this.footer,
    this.ownerDestinations = const [],
    this.onOwnerDestinationSelected,
    this.selectedOwnerIndex,
    this.trailingPane,
  });

  final List<AdaptiveDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;
  final Widget body;
  final String? title;
  final List<Widget>? actions;
  final Widget? footer;
  final List<AdaptiveDestination> ownerDestinations;
  final ValueChanged<int>? onOwnerDestinationSelected;
  final int? selectedOwnerIndex;
  final Widget? trailingPane;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Row(
        children: [
          SizedBox(
            width: AdaptiveScaffold.sidebarWidth,
            child: Material(
              color: AppColors.surface,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Padding(
                    padding: EdgeInsets.fromLTRB(18, 16, 12, 8),
                    child: VelmartLogo(
                      variant: VelmartLogoVariant.markWordmark,
                      markSize: 32,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Expanded(
                    child: ListView(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      children: [
                        for (var i = 0; i < destinations.length; i++)
                          _SidebarTile(
                            destination: destinations[i],
                            selected: i == selectedIndex,
                            onTap: () => onDestinationSelected(i),
                          ),
                        if (ownerDestinations.isNotEmpty) ...[
                          const Padding(
                            padding: EdgeInsets.fromLTRB(10, 10, 10, 4),
                            child: Text(
                              'OWNER',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.06 * 11,
                                color: AppColors.textDisabled,
                              ),
                            ),
                          ),
                          for (var i = 0; i < ownerDestinations.length; i++)
                            _SidebarTile(
                              destination: ownerDestinations[i],
                              selected: i == selectedOwnerIndex,
                              onTap: () => onOwnerDestinationSelected?.call(i),
                            ),
                        ],
                      ],
                    ),
                  ),
                  if (footer != null)
                    Padding(
                      padding: const EdgeInsets.all(AppSpacing.sm),
                      child: footer!,
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
                if (title != null || (actions != null && actions!.isNotEmpty))
                  Material(
                    color: AppColors.surface,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.sm,
                      ),
                      child: SizedBox(
                        height: 52,
                        child: Row(
                          children: [
                            if (title != null)
                              Expanded(
                                child: Text(
                                  title!,
                                  style: Theme.of(context).textTheme.titleLarge,
                                ),
                              )
                            else
                              const Spacer(),
                            if (actions != null) ...actions!,
                          ],
                        ),
                      ),
                    ),
                  ),
                if (title != null || (actions != null && actions!.isNotEmpty))
                  const Divider(height: 1),
                Expanded(child: body),
              ],
            ),
          ),
          if (trailingPane != null) ...[
            const VerticalDivider(width: 1),
            SizedBox(
              width: AdaptiveScaffold.aiPaneWidth,
              child: Material(color: AppColors.surface, child: trailingPane),
            ),
          ],
        ],
      ),
    );
  }
}

class _SidebarTile extends StatelessWidget {
  const _SidebarTile({
    required this.destination,
    required this.selected,
    required this.onTap,
  });

  final AdaptiveDestination destination;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: ListTile(
        dense: true,
        shape: const RoundedRectangleBorder(borderRadius: AppRadii.smRadius),
        selected: selected,
        selectedTileColor: AppColors.brandPrimarySoft,
        contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
        leading: Icon(
          selected ? destination.selectedIcon : destination.icon,
          color: selected ? AppColors.brandPrimaryDeep : AppColors.textTertiary,
          size: 18,
        ),
        title: Text(
          destination.label,
          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
            color: selected ? AppColors.brandPrimaryDeep : AppColors.textSecondary,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
            fontSize: 13.5,
          ),
        ),
        onTap: onTap,
      ),
    );
  }
}
