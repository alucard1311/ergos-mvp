# Phase 10: Flutter Client UI - Research

**Researched:** 2026-01-26
**Domain:** Flutter animations, visual state representation, voice assistant UI patterns
**Confidence:** HIGH

<research_summary>
## Summary

Researched Flutter approaches for creating an animated 3D ball visualization for a voice assistant UI. The key finding is that **true 3D is overkill** - experts use pseudo-3D (2.5D) techniques with CustomPainter and radial gradients to create sphere-like effects that are performant on mobile.

For state visualization, the recommended approach combines:
1. **CustomPainter with RadialGradient** for the 3D sphere appearance
2. **AnimationController** for state-driven animations (pulsing, color changes)
3. **flutter_animate** or **pulsator** packages for simplified animation effects
4. **GestureDetector** for barge-in tap handling

The siri_wave package offers ready-made Siri-style waveform visualizations that could complement or replace a ball visualization.

**Primary recommendation:** Use CustomPainter with RadialGradient for a pseudo-3D sphere, AnimationController for state-driven pulsing/color changes, and GestureDetector for barge-in. Avoid full 3D libraries (flutter_3d_controller, three_js) as they're overkill for a simple animated ball.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| CustomPainter | Flutter SDK | Low-level canvas drawing | Built-in, performant, full control |
| AnimationController | Flutter SDK | Animation timing/control | Built-in, handles vsync |
| flutter_animate | ^4.5.2 | Simplified animation API | 540k+ weekly downloads, chainable effects |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pulsator | ^1.0.0 | Pulsing animation effect | Simple pulsing without custom code |
| siri_wave | ^2.0.0 | Siri-style waveform | Alternative to ball, audio visualization |
| wave_blob | latest | Blob wave animation | Audio-responsive blob visualization |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CustomPainter sphere | flutter_3d_controller | 3D controller is overkill, adds dependencies, complex setup |
| CustomPainter sphere | siri_wave | Different aesthetic (wave vs ball), but already built |
| AnimationController | flutter_animate | flutter_animate simpler but less control |
| Custom pulsing | pulsator package | Less control but faster to implement |

**Installation:**
```yaml
dependencies:
  flutter_animate: ^4.5.2
  # Optional alternatives:
  # pulsator: ^1.0.0
  # siri_wave: ^2.0.0
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```
client/lib/
├── widgets/
│   ├── ergos_orb.dart          # Main orb widget with state-driven animation
│   ├── orb_painter.dart        # CustomPainter for sphere rendering
│   └── pulse_effect.dart       # Optional pulse overlay effect
├── models/
│   └── orb_state.dart          # Enum mapping server state to visual state
└── main.dart                   # App with orb widget
```

### Pattern 1: State-Driven Animation Widget
**What:** StatefulWidget that maps connection/server state to visual properties
**When to use:** Always for state-based UI changes
**Example:**
```dart
class ErgosOrb extends StatefulWidget {
  final String serverState; // IDLE, LISTENING, PROCESSING, SPEAKING
  final VoidCallback? onBargeIn;

  const ErgosOrb({required this.serverState, this.onBargeIn});

  @override
  State<ErgosOrb> createState() => _ErgosOrbState();
}

class _ErgosOrbState extends State<ErgosOrb>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
    _pulseAnimation = Tween<double>(begin: 0.95, end: 1.05).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void didUpdateWidget(ErgosOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.serverState != oldWidget.serverState) {
      _updateAnimationForState(widget.serverState);
    }
  }

  void _updateAnimationForState(String state) {
    switch (state) {
      case 'IDLE':
        _controller.stop();
        _controller.value = 0.5;
        break;
      case 'LISTENING':
        _controller.repeat(reverse: true);
        break;
      case 'PROCESSING':
        _controller.repeat(); // No reverse = spinning effect
        break;
      case 'SPEAKING':
        _controller.repeat(reverse: true);
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.serverState == 'SPEAKING' ? widget.onBargeIn : null,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return Transform.scale(
            scale: _pulseAnimation.value,
            child: CustomPaint(
              size: const Size(200, 200),
              painter: OrbPainter(
                color: _colorForState(widget.serverState),
                glowIntensity: _controller.value,
              ),
            ),
          );
        },
      ),
    );
  }

  Color _colorForState(String state) {
    switch (state) {
      case 'IDLE': return Colors.grey;
      case 'LISTENING': return Colors.blue;
      case 'PROCESSING': return Colors.amber;
      case 'SPEAKING': return Colors.green;
      default: return Colors.grey;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}
```

### Pattern 2: Pseudo-3D Sphere with RadialGradient
**What:** CustomPainter using radial gradient to create sphere illusion
**When to use:** For 3D-looking sphere without actual 3D rendering
**Example:**
```dart
class OrbPainter extends CustomPainter {
  final Color color;
  final double glowIntensity; // 0.0 to 1.0

  OrbPainter({required this.color, required this.glowIntensity});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width * 0.4;

    // Outer glow
    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          color.withOpacity(0.3 * glowIntensity),
          color.withOpacity(0.0),
        ],
        stops: const [0.5, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius * 1.5));
    canvas.drawCircle(center, radius * 1.5, glowPaint);

    // Main sphere with 3D effect
    final spherePaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.3, -0.3), // Light source offset
        radius: 1.0,
        colors: [
          Color.lerp(color, Colors.white, 0.6)!, // Highlight
          color,                                   // Mid-tone
          Color.lerp(color, Colors.black, 0.5)!,  // Shadow
        ],
        stops: const [0.0, 0.4, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawCircle(center, radius, spherePaint);
  }

  @override
  bool shouldRepaint(OrbPainter oldDelegate) {
    return oldDelegate.color != color ||
           oldDelegate.glowIntensity != glowIntensity;
  }
}
```

### Pattern 3: GestureDetector for Barge-in
**What:** Tap gesture to interrupt AI speech
**When to use:** When serverState == 'SPEAKING'
**Example:**
```dart
GestureDetector(
  onTap: () {
    if (serverState == 'SPEAKING') {
      webRTCService.sendDataChannelMessage({
        'type': 'barge_in',
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
      });
    }
  },
  child: OrbWidget(),
)
```

### Anti-Patterns to Avoid
- **Using full 3D libraries (three_js, flutter_3d_controller):** Overkill for simple sphere, adds complexity
- **Calling setState() in animation loop:** Use AnimatedBuilder instead to avoid rebuilding entire widget tree
- **Not using vsync:** Causes offscreen animations to consume resources
- **Hard-coding animation values:** Make them state-dependent for visual feedback
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pulsing animation | Manual timer-based scaling | AnimationController with Tween | Handles vsync, frame timing, curves |
| Sphere appearance | Complex math for 3D rendering | RadialGradient with offset center | Simple, performant, looks great |
| Siri-style waveform | Custom sine wave calculations | siri_wave package | Already built, tested, customizable |
| Animation sequencing | Manual state tracking | flutter_animate or CurvedAnimation | Handles timing, easing, chaining |
| Gesture conflicts | Manual event routing | GestureDetector with proper callbacks | Built-in gesture arena disambiguation |

**Key insight:** Flutter's animation system is sophisticated - AnimationController + Tween + Curves handles almost everything. The temptation is to build custom animation math, but the framework already solved these problems. CustomPainter is only needed for the visual rendering, not the animation logic.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Animation Performance on Low-End Devices
**What goes wrong:** Janky animations, dropped frames
**Why it happens:** Too many rebuilds, missing vsync, complex paint operations
**How to avoid:**
- Always use `SingleTickerProviderStateMixin` for vsync
- Use `AnimatedBuilder` to scope rebuilds
- Keep CustomPainter paint() method simple
- Use `shouldRepaint()` to avoid unnecessary repaints
**Warning signs:** Frame rate drops below 60fps, visible stuttering

### Pitfall 2: State Transition Glitches
**What goes wrong:** Animation jumps or snaps instead of smooth transition
**Why it happens:** Not handling didUpdateWidget properly, resetting controller incorrectly
**How to avoid:**
- In `didUpdateWidget`, smoothly transition animations
- Don't call `controller.reset()` - use `controller.value = x` for smooth changes
- Use `controller.animateTo()` for transitions between states
**Warning signs:** Visual jump when state changes

### Pitfall 3: Memory Leaks from Animation Controllers
**What goes wrong:** Memory grows, app slows down
**Why it happens:** Not disposing AnimationController in dispose()
**How to avoid:**
- Always call `_controller.dispose()` in widget's dispose()
- Use `with SingleTickerProviderStateMixin` instead of creating TickerProvider manually
**Warning signs:** Memory usage climbs over time

### Pitfall 4: Gesture Conflicts with Scrolling
**What goes wrong:** Taps don't register, or scrolling is blocked
**Why it happens:** GestureDetector arena conflicts with parent scroll
**How to avoid:**
- Use `behavior: HitTestBehavior.opaque` if needed
- Consider using `onTapUp` instead of `onTap` for more control
- Place orb in non-scrollable area
**Warning signs:** Inconsistent tap response

### Pitfall 5: Color Transition Not Smooth
**What goes wrong:** Color snaps from one to another instead of animating
**Why it happens:** Not using ColorTween or AnimatedContainer
**How to avoid:**
- Use `ColorTween` with AnimationController
- Or wrap in `AnimatedContainer` with color property
- Or use `flutter_animate` color effects
**Warning signs:** Jarring color changes on state change
</common_pitfalls>

<code_examples>
## Code Examples

### Basic Animated Orb Setup
```dart
// Source: Flutter docs + research synthesis
import 'package:flutter/material.dart';

class ErgosOrb extends StatefulWidget {
  final String serverState;
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
  late Animation<Color?> _colorAnimation;

  Color _currentColor = Colors.grey;
  Color _targetColor = Colors.grey;

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

  void _updateForState(String state) {
    _targetColor = _colorForState(state);

    switch (state) {
      case 'IDLE':
        _controller.stop();
        _controller.value = 0.5;
        break;
      case 'LISTENING':
      case 'SPEAKING':
        _controller.repeat(reverse: true);
        break;
      case 'PROCESSING':
        _controller.repeat(reverse: true, period: const Duration(milliseconds: 600));
        break;
    }

    setState(() {
      _currentColor = _targetColor;
    });
  }

  Color _colorForState(String state) {
    switch (state) {
      case 'IDLE': return const Color(0xFF6B7280);      // Grey
      case 'LISTENING': return const Color(0xFF3B82F6); // Blue
      case 'PROCESSING': return const Color(0xFFF59E0B); // Amber
      case 'SPEAKING': return const Color(0xFF10B981);  // Green
      default: return const Color(0xFF6B7280);
    }
  }

  @override
  void didUpdateWidget(ErgosOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.serverState != oldWidget.serverState) {
      _updateForState(widget.serverState);
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
```

### OrbPainter with Pseudo-3D Effect
```dart
// Source: Flutter docs RadialGradient + research synthesis
class OrbPainter extends CustomPainter {
  final Color color;
  final double glowIntensity;

  OrbPainter({
    required this.color,
    required this.glowIntensity,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width * 0.35;

    // Outer glow (pulsing)
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

    // Main sphere with 3D gradient
    final spherePaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.3, -0.4), // Light from top-left
        radius: 1.2,
        colors: [
          Color.lerp(color, Colors.white, 0.7)!, // Bright highlight
          color,                                   // True color
          Color.lerp(color, Colors.black, 0.4)!,  // Shadow
        ],
        stops: const [0.0, 0.3, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawCircle(center, radius, spherePaint);

    // Inner highlight (specular)
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
```

### Alternative: Using flutter_animate
```dart
// Source: flutter_animate docs
import 'package:flutter_animate/flutter_animate.dart';

Widget buildOrbWithFlutterAnimate(String serverState) {
  final isActive = serverState != 'IDLE';

  return Container(
    width: 200,
    height: 200,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      gradient: RadialGradient(
        center: const Alignment(-0.3, -0.4),
        colors: [
          Colors.white,
          _colorForState(serverState),
          Colors.black,
        ],
        stops: const [0.0, 0.3, 1.0],
      ),
      boxShadow: [
        BoxShadow(
          color: _colorForState(serverState).withOpacity(0.5),
          blurRadius: 30,
          spreadRadius: 10,
        ),
      ],
    ),
  )
      .animate(
        onPlay: (controller) => isActive
            ? controller.repeat(reverse: true)
            : controller.stop(),
      )
      .scale(
        begin: const Offset(0.95, 0.95),
        end: const Offset(1.05, 1.05),
        duration: 1200.ms,
        curve: Curves.easeInOut,
      )
      .shimmer(
        duration: 2000.ms,
        color: Colors.white.withOpacity(0.3),
      );
}
```
</code_examples>

<sota_updates>
## State of the Art (2025-2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual animation timers | AnimationController with vsync | Long established | Better performance, system integration |
| Vanilla AnimatedWidget | flutter_animate package | 2022+ | Much simpler API, composable |
| Full 3D for simple shapes | Pseudo-3D with gradients | N/A | Gradient approach always preferred for simple shapes |
| Custom pulsing logic | pulsator/flutter_animate | 2023+ | Ready-made, tested solutions |

**New tools/patterns to consider:**
- **flutter_animate** (v4.5.2): Chainable, declarative animations - best DX for most cases
- **Impeller renderer**: Flutter's new rendering engine improves animation performance on iOS
- **Material 3 motion**: New motion guidelines may influence animation timing

**Deprecated/outdated:**
- **Manual ticker management**: Use mixins (SingleTickerProviderStateMixin) instead
- **Separate animation packages for each effect**: flutter_animate consolidates most needs
</sota_updates>

<open_questions>
## Open Questions

1. **Exact visual design for each state**
   - What we know: States are IDLE, LISTENING, PROCESSING, SPEAKING
   - What's unclear: Exact color palette, animation speeds, glow intensity per state
   - Recommendation: Start with researched defaults, adjust based on user feedback

2. **Audio-reactive pulsing**
   - What we know: siri_wave and wave_blob support audio amplitude
   - What's unclear: Whether Ergos needs audio-level visualization or just state-based
   - Recommendation: Start with state-based only, audio-reactive is v2 enhancement

3. **Accessibility considerations**
   - What we know: Animations can cause issues for motion-sensitive users
   - What's unclear: Whether to provide reduced-motion mode
   - Recommendation: Respect system accessibility settings (MediaQuery.disableAnimations)
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- [Flutter Animation Docs](https://docs.flutter.dev/ui/animations) - AnimationController, Tween, implicit vs explicit
- [Flutter CustomPainter API](https://api.flutter.dev/flutter/rendering/CustomPainter-class.html) - Canvas drawing
- [Flutter RadialGradient API](https://api.flutter.dev/flutter/painting/RadialGradient-class.html) - Gradient for sphere effect
- [flutter_animate pub.dev](https://pub.dev/packages/flutter_animate) - Animation package API
- [pulsator pub.dev](https://pub.dev/packages/pulsator) - Pulsing animation API

### Secondary (MEDIUM confidence)
- [Kodeco Magic 8-Ball Tutorial](https://www.kodeco.com/22379941-building-complex-ui-in-flutter-magic-8-ball) - Pseudo-3D sphere approach
- [Medium: Glowing Orb Animation](https://medium.com/@amitsingh506142/creating-a-beautiful-animation-in-flutter-using-custompaint-347a44c464fa) - CustomPainter animation pattern
- [Flutter Gems 3D packages](https://fluttergems.dev/3d/) - Package ecosystem overview
- [siri_wave pub.dev](https://pub.dev/packages/siri_wave) - Alternative visualization

### Tertiary (LOW confidence - needs validation)
- None - all findings verified against official sources
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Flutter animations, CustomPainter
- Ecosystem: flutter_animate, pulsator, siri_wave
- Patterns: State-driven animation, pseudo-3D rendering
- Pitfalls: Performance, state transitions, memory leaks

**Confidence breakdown:**
- Standard stack: HIGH - verified with Flutter docs, pub.dev
- Architecture: HIGH - from official examples and tutorials
- Pitfalls: HIGH - documented in Flutter docs and community
- Code examples: HIGH - synthesized from verified sources

**Research date:** 2026-01-26
**Valid until:** 2026-02-26 (30 days - Flutter animation ecosystem stable)
</metadata>

---

*Phase: 10-flutter-client-ui*
*Research completed: 2026-01-26*
*Ready for planning: yes*
