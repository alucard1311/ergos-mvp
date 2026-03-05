"""Combined test: EmotionMarkup transforms → Orpheus TTS playback."""
import numpy as np
import sounddevice as sd
from ergos.tts.emotion_markup import EmotionMarkupProcessor
from ergos.tts.orpheus_synthesizer import OrpheusSynthesizer
from ergos.tts.types import SynthesisConfig


def test():
    markup = EmotionMarkupProcessor()
    synth = OrpheusSynthesizer(n_gpu_layers=-1)
    config = SynthesisConfig(orpheus_voice="tara")

    tests = [
        ("Basic speech", "Hello, I'm your voice assistant."),
        ("Laugh hint", "That's funny *laughs* really funny"),
        ("Sigh hint", "Oh great *sighs* another one"),
        ("Chuckle hint", "*chuckles* You're not wrong"),
        ("Ellipsis to pause", "Well... I suppose... if you insist"),
        ("Sarcasm combo", "Sure... I'd *love* to help with that"),
        ("Multiple emotions", "*sighs* Fine *laughs* that is pretty funny"),
        ("Gasp", "*gasps* I can't believe that happened"),
        ("Question intonation", "Are you seriously asking me that right now?"),
        ("No hints (passthrough)", "Just a normal sentence with no emotion."),
    ]

    print("Combined Markup → TTS Test")
    print("=" * 60)

    for name, text in tests:
        processed = markup.process(text)
        changed = " (markup applied)" if processed != text else ""
        print(f"\n=== {name}{changed} ===")
        print(f"  LLM output: {text}")
        print(f"  TTS input:  {processed}")
        input("  Press Enter to play...")
        result = synth.synthesize(processed, config)
        sd.play(result.audio_samples, samplerate=result.sample_rate)
        sd.wait()
        print(f"  Done. ({result.duration_ms:.0f}ms)")

    print("\n" + "=" * 60)
    print("All tests complete.")


if __name__ == "__main__":
    test()
