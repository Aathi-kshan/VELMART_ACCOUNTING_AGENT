import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

/// Gradient **V** mark from the prototype (login + sidebar). The logo
/// gradient is allowed here only — never behind business controls.
enum VelmartLogoVariant { mark, full, markWordmark }

class VelmartLogo extends StatelessWidget {
  const VelmartLogo({
    super.key,
    this.variant = VelmartLogoVariant.mark,
    this.markSize = 40,
  });

  final VelmartLogoVariant variant;
  final double markSize;

  @override
  Widget build(BuildContext context) {
    final mark = _GradientV(size: markSize);
    final wordmark = Text(
      'Velmart',
      style: Theme.of(context).textTheme.titleLarge?.copyWith(
        fontWeight: FontWeight.w700,
        letterSpacing: -0.2,
      ),
    );

    return switch (variant) {
      VelmartLogoVariant.mark => mark,
      VelmartLogoVariant.full => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          mark,
          const SizedBox(height: AppSpacing.md),
          wordmark,
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Business data and accounting',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
      VelmartLogoVariant.markWordmark => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          mark,
          const SizedBox(width: AppSpacing.smMd),
          Flexible(child: wordmark),
        ],
      ),
    };
  }
}

class _GradientV extends StatelessWidget {
  const _GradientV({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    final radius = size >= 64 ? 24.0 : 8.0;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.brandSecondary, AppColors.brandPrimary],
        ),
      ),
      alignment: Alignment.center,
      child: Text(
        'V',
        style: TextStyle(
          color: AppColors.textOnBrand,
          fontWeight: FontWeight.w700,
          fontSize: size * 0.48,
          height: 1,
        ),
      ),
    );
  }
}
