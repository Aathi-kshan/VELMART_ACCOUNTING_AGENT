import 'package:flutter/material.dart';

import '../theme/app_radii.dart';
import '../theme/app_spacing.dart';

/// Default application card (design.md §11.1): white, 12 dp radius, 1 dp
/// border, no decorative shadow.
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.onTap,
    this.padding,
    this.margin,
    this.selected = false,
  });

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      margin: margin ?? EdgeInsets.zero,
      color: selected ? colorScheme.primaryContainer : null,
      clipBehavior: Clip.antiAlias,
      child: onTap == null
          ? Padding(
              padding: padding ?? const EdgeInsets.all(AppSpacing.cardPadding),
              child: child,
            )
          : InkWell(
              onTap: onTap,
              borderRadius: AppRadii.mdRadius,
              child: Padding(
                padding: padding ?? const EdgeInsets.all(AppSpacing.cardPadding),
                child: child,
              ),
            ),
    );
  }
}
