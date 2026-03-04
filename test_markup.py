"""Step 5: Test EmotionMarkupProcessor transforms LLM output to Orpheus tags."""
from ergos.tts.emotion_markup import EmotionMarkupProcessor

proc = EmotionMarkupProcessor()

tests = [
    # (description, LLM output)
    ("Laugh hint", "That's funny *laughs* really funny"),
    ("Sigh hint", "Oh great *sighs* another one"),
    ("Chuckle hint", "*chuckles* You're not wrong"),
    ("Ellipsis to pause", "Well... I suppose... if you insist"),
    ("Sarcasm combo", "Sure... I'd *love* to help with that"),
    ("Case insensitive", "Ha *LAUGHS* that was good"),
    ("Unknown hint stripped", "He said *waves hand* goodbye"),
    ("Multiple emotions", "*sighs* Fine *laughs* that is pretty funny"),
    ("Gasp", "*gasps* I can't believe that happened"),
    ("Yawn", "*yawns* This meeting is so exciting"),
    ("No hints (passthrough)", "Just a normal sentence with no emotion."),
]

print("EmotionMarkupProcessor Transform Results")
print("=" * 60)

for desc, text in tests:
    result = proc.process(text)
    changed = "CHANGED" if result != text else "SAME"
    print(f"\n[{desc}] ({changed})")
    print(f"  IN:  {text}")
    print(f"  OUT: {result}")

print("\n" + "=" * 60)
print("Done.")
