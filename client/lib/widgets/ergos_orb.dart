import 'package:flutter/material.dart';
import 'orb_painter.dart';

/// Animated orb widget that visualizes server state.
///
/// The orb changes color and animation based on [serverState]:
/// - IDLE: Grey, no animation
/// - LISTENING: Blue, gentle pulsing
/// - PROCESSING: Amber, faster pulsing
/// - SPEAKING: Green, gentle pulsing (tap to barge-in)
/// - SPEAKING_AND_LISTENING: Cyan, fast pulsing (tap to barge-in)
///
/// When [isKitchenMode] is true, uses a warmer color palette
/// with orange/red tones to indicate cooking mode.
class ErgosOrb extends StatefulWidget {
  /// Current server state: IDLE, LISTENING, PROCESSING, or SPEAKING.
  final String serverState;

  /// Callback invoked when user taps during SPEAKING state (barge-in).
  final VoidCallback? onBargeIn;

  /// Whether kitchen mode is active (uses different color scheme).
  final bool isKitchenMode;

  const ErgosOrb({
    super.key,
    required this.serverState,
    this.onBargeIn,
    this.isKitchenMode = false,
  });

  @override
  State<ErgosOrb> createState() => _ErgosOrbState();
}

class _ErgosOrbState extends State<ErgosOrb>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;
  Color _currentColor = const Color(0xFF6B7280);

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );

    _scaleAnimation = Tween<double>(
      begin: 0.95,
      end: 1.05,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOut,
    ));

    _updateForState(widget.serverState, isKitchenMode: widget.isKitchenMode);
  }

  /// Updates animation and color based on the given state.
  void _updateForState(String state, {bool isKitchenMode = false}) {
    _currentColor = _colorForState(state, isKitchenMode: isKitchenMode);

    switch (state) {
      case 'IDLE':
        _controller.stop();
        _controller.value = 0.5;
        break;
      case 'LISTENING':
        _controller.repeat(reverse: true);
        break;
      case 'PROCESSING':
        _controller.repeat(
          reverse: true,
          period: const Duration(milliseconds: 600),
        );
        break;
      case 'SPEAKING':
        _controller.repeat(reverse: true);
        break;
      case 'SPEAKING_AND_LISTENING':
        // Fast pulse: 400ms period to distinguish from SPEAKING (1200ms default)
        _controller.repeat(
          reverse: true,
          period: const Duration(milliseconds: 400),
        );
        break;
      default:
        _controller.stop();
        _controller.value = 0.5;
    }
  }

  /// Returns the appropriate color for each server state.
  ///
  /// When [isKitchenMode] is true, uses warmer cooking-themed colors.
  Color _colorForState(String state, {bool isKitchenMode = false}) {
    if (isKitchenMode) {
      // Kitchen mode: warmer colors (orange, red, yellow tones)
      switch (state) {
        case 'IDLE':
          return const Color(0xFF8B5A2B); // Warm brown
        case 'LISTENING':
          return const Color(0xFFFF6B35); // Cooking orange
        case 'PROCESSING':
          return const Color(0xFFFFD700); // Golden yellow
        case 'SPEAKING':
          return const Color(0xFF4CAF50); // Chef green
        case 'SPEAKING_AND_LISTENING':
          return const Color(0xFF06B6D4); // Cyan (same in kitchen mode for consistency)
        default:
          return const Color(0xFF8B5A2B); // Warm brown
      }
    }

    // Normal mode: cool colors (blue, grey tones)
    switch (state) {
      case 'IDLE':
        return const Color(0xFF6B7280); // Grey
      case 'LISTENING':
        return const Color(0xFF3B82F6); // Blue
      case 'PROCESSING':
        return const Color(0xFFF59E0B); // Amber
      case 'SPEAKING':
        return const Color(0xFF10B981); // Green
      case 'SPEAKING_AND_LISTENING':
        return const Color(0xFF06B6D4); // Cyan — distinct from green (SPEAKING) and blue (LISTENING)
      default:
        return const Color(0xFF6B7280); // Grey
    }
  }

  @override
  void didUpdateWidget(ErgosOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.serverState != oldWidget.serverState ||
        widget.isKitchenMode != oldWidget.isKitchenMode) {
      setState(() {
        _updateForState(widget.serverState, isKitchenMode: widget.isKitchenMode);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: (widget.serverState == 'SPEAKING' || widget.serverState == 'SPEAKING_AND_LISTENING')
          ? widget.onBargeIn
          : null,
      behavior: HitTestBehavior.opaque,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return Transform.scale(
            scale: _scaleAnimation.value,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              child: CustomPaint(
                size: const Size(200, 200),
                painter: OrbPainter(
                  color: _currentColor,
                  glowIntensity: _controller.value,
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}
