"""
Text Simplifier for Dyslexia using Groq API (Free)
---------------------------------------------------
Setup:
    1. Go to https://console.groq.com and sign up free
    2. Go to API Keys → Create API Key → copy it
    3. Replace YOUR_GROQ_API_KEY_HERE below with your key
    4. pip install groq textstat

Run:
    python simplifier_groq.py
"""

from groq import Groq
import textstat
import os
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are a text simplification assistant helping people with dyslexia.
Your job is to rewrite complex text into simple, easy-to-read English.

Rules:
- Replace difficult or technical words with simple everyday words
- Break long sentences into shorter ones
- Keep ALL the original meaning — do not remove important information
- Use active voice instead of passive voice
- Aim for a reading level of grade 6-8
- Return ONLY the simplified text, no explanations, no preamble"""

def simplify_text(text):
    try:
        if not text or len(text.strip()) == 0:
            return {"error": "Text is empty", "success": False}

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # best free model on Groq
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Simplify this text:\n\n{text}"}
            ],
            temperature=0.3,      # low = more consistent output
            max_tokens=1024,
        )

        simplified = response.choices[0].message.content.strip()

        original_flesch  = textstat.flesch_reading_ease(text)
        simplified_flesch = textstat.flesch_reading_ease(simplified)
        improvement      = simplified_flesch - original_flesch

        return {
            "original":          text,
            "simplified":        simplified,
            "original_flesch":   original_flesch,
            "simplified_flesch": simplified_flesch,
            "improvement":       improvement,
            "success":           True
        }

    except Exception as e:
        return {"error": str(e), "success": False}


if __name__ == "__main__":
    test_texts = [
        "Myocardial infarction occurs when blood flow decreases or stops to a part of the heart, causing damage to the heart muscle. The most common symptom is chest pain or discomfort which may travel into the shoulder, arm, back, neck or jaw.",

        "The defendant, pursuant to the aforementioned contractual obligations stipulated in section 4.2 of the binding agreement, shall be held liable for any consequential damages arising from the negligent misrepresentation of the financial instruments therein described.",

        "Quantum entanglement is a physical phenomenon that occurs when a group of particles are generated, interact, or share spatial proximity in a way such that the quantum state of each particle of the group cannot be described independently of the state of the others.",

        "The Byzantine Empire, also referred to as the Eastern Roman Empire or Byzantium, was the continuation of the Roman Empire primarily in its eastern provinces during Late Antiquity and the Middle Ages, when its capital city was Constantinople.",

        "Deoxyribonucleic acid is a molecule composed of two polynucleotide chains that coil around each other to form a double helix carrying genetic instructions for the development, functioning, growth and reproduction of all known organisms.",
    ]

    print("🧪 Text Simplifier for Dyslexia — powered by Groq\n")
    print("=" * 70)

    for text in test_texts:
        result = simplify_text(text)

        if result.get("success"):
            improvement = result["improvement"]
            sign        = "+" if improvement >= 0 else ""

            print(f"\n📝 Original  (Flesch: {result['original_flesch']:.1f}):")
            print(f"   {result['original']}")
            print(f"\n✨ Simplified (Flesch: {result['simplified_flesch']:.1f}):")
            print(f"   {result['simplified']}")
            print(f"\n📊 Readability improvement: {sign}{improvement:.1f} points")
            print("=" * 70)
        else:
            print(f"\n❌ Error: {result['error']}")
            print("=" * 70)