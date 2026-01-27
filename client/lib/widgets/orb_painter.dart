import 'package:flutter/material.dart';

/// CustomPainter for rendering a pseudo-3D sphere with gradient lighting.
///
/// Uses RadialGradient to create the illusion of a 3D sphere with:
/// - Outer glow that pulses based on [glowIntensity]
/// - Main sphere with light source offset for 3D effect
/// - Inner specular highlight for added realism
class OrbPainter extends CustomPainter {
  /// The base color of the orb.
  final Color color;

  /// Glow intensity from 0.0 to 1.0, used for pulsing effect.
  final double glowIntensity;

  OrbPainter({
    required this.color,
    required this.glowIntensity,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width * 0.35;

    // Outer glow (pulsing based on glowIntensity)
    final glowRadius = radius * (1.2 + 0.3 * glowIntensity);
    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          color.withOpacity(0.4 * glowIntensity),
          color.withOpacity(0.1 * glowIntensity),
          color.withOpacity(0.0),
        ],
        stops: const [0.0, 0.5, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: glowRadius));
    canvas.drawCircle(center, glowRadius, glowPaint);

    // Main sphere with 3D gradient effect
    // Light source positioned at top-left via Alignment(-0.3, -0.4)
    final spherePaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.3, -0.4), // Light from top-left
        radius: 1.2,
        colors: [
          Color.lerp(color, Colors.white, 0.7)!, // Bright highlight
          color, // True color
          Color.lerp(color, Colors.black, 0.4)!, // Shadow
        ],
        stops: const [0.0, 0.3, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawCircle(center, radius, spherePaint);

    // Inner highlight (specular reflection)
    final highlightCenter = Offset(
      center.dx - radius * 0.25,
      center.dy - radius * 0.25,
    );
    final highlightPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          Colors.white.withOpacity(0.6),
          Colors.white.withOpacity(0.0),
        ],
      ).createShader(Rect.fromCircle(
        center: highlightCenter,
        radius: radius * 0.3,
      ));
    canvas.drawCircle(highlightCenter, radius * 0.2, highlightPaint);
  }

  @override
  bool shouldRepaint(OrbPainter oldDelegate) {
    return oldDelegate.color != color ||
        oldDelegate.glowIntensity != glowIntensity;
  }
}
