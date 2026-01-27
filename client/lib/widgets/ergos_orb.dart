import 'package:flutter/material.dart';
import 'orb_painter.dart';

/// Animated orb widget that visualizes server state.
///
/// The orb changes color and animation based on [serverState]:
/// - IDLE: Grey, no animation
/// - LISTENING: Blue, gentle pulsing
/// - PROCESSING: Amber, faster pulsing
/// - SPEAKING: Green, gentle pulsing (tap to barge-in)
class ErgosOrb extends StatefulWidget {
  /// Current server state: IDLE, LISTENING, PROCESSING, or SPEAKING.
  final String serverState;

  /// Callback invoked when user taps during SPEAKING state (barge-in).
  final VoidCallback? onBargeIn;

  const ErgosOrb({
    super.key,
    required this.serverState,
    this.onBargeIn,
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

    _updateForState(widget.serverState);
  }

  /// Updates animation and color based on the given state.
  void _updateForState(String state) {
    _currentColor = _colorForState(state);

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
      default:
        _controller.stop();
        _controller.value = 0.5;
    }
  }

  /// Returns the appropriate color for each server state.
  Color _colorForState(String state) {
    switch (state) {
      case 'IDLE':
        return const Color(0xFF6B7280); // Grey
      case 'LISTENING':
        return const Color(0xFF3B82F6); // Blue
      case 'PROCESSING':
        return const Color(0xFFF59E0B); // Amber
      case 'SPEAKING':
        return const Color(0xFF10B981); // Green
      default:
        return const Color(0xFF6B7280); // Grey
    }
  }

  @override
  void didUpdateWidget(ErgosOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.serverState != oldWidget.serverState) {
      setState(() {
        _updateForState(widget.serverState);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.serverState == 'SPEAKING' ? widget.onBargeIn : null,
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
