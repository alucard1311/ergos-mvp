"""Step 4: Test Orpheus TTS standalone with local speaker output."""
import numpy as np
import sounddevice as sd
from ergos.tts.orpheus_synthesizer import OrpheusSynthesizer
from ergos.tts.types import SynthesisConfig


def test():
    # n_gpu_layers=-1 = full GPU offload (needs ~2GB VRAM, fine on 16GB 5080)
    synth = OrpheusSynthesizer(n_gpu_layers=-1)
    config = SynthesisConfig(orpheus_voice="tara")

    tests = [
        ("Basic speech", "Hello, I'm your voice assistant."),
        ("Laugh emotion", "That's hilarious <laugh> I can't believe you said that."),
        ("Sigh emotion", "<sigh> Fine, I'll do it myself."),
        ("Chuckle", "<chuckle> You're not wrong about that."),
        ("Sarcasm with pause", "Oh, what a surprise, another meeting."),
        ("Multiple emotions", "Well <sigh> I suppose <laugh> that is pretty funny."),
        ("Question intonation", "Are you seriously asking me that right now?"),
        ("Command tone", "Stop what you're doing and listen to me."),
    ]

    for name, text in tests:
        print(f"\n=== {name} ===")
        print(f"Text: {text}")
        input("Press Enter to play...")
        result = synth.synthesize(text, config)
        sd.play(result.audio_samples, samplerate=result.sample_rate)
        sd.wait()
        print(f"Done. ({result.duration_ms:.0f}ms)")

    print("\n=== All tests complete ===")


if __name__ == "__main__":
    test()
