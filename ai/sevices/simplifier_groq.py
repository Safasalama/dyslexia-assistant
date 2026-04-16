"""
Text Simplifier with Minimum Bayes Risk Re-ranking
----------------------------------------------------
Same interface as before — simplify_text(text) returns the same dict.
Internally: generates N candidates via Groq, scores each with your
difficulty scorer, picks the one that minimizes difficulty while
preserving meaning above a similarity threshold.
"""

from groq import Groq
import textstat
import os
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client       = Groq(api_key=GROQ_API_KEY)
sim_model    = SentenceTransformer('paraphrase-MiniLM-L3-v2')

# Import your scorer — same as bert_scorer.py uses
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from ai.models.bert_scorer import find_difficult_words_in_text

SYSTEM_PROMPTS = [
    # Prompt 1 — conservative, word-level changes only
    """You are helping people with dyslexia read difficult text.
    Rewrite the text by replacing hard words with simpler ones.
    Keep the sentence structure identical. Keep ALL meaning.
    Return ONLY the rewritten text.""",

    # Prompt 2 — structural, break sentences
    """You are helping people with dyslexia read difficult text.
    Rewrite the text by breaking long sentences into shorter ones.
    Use simple subject-verb-object structure.
    Keep ALL meaning. Return ONLY the rewritten text.""",

    # Prompt 3 — aggressive, full rewrite
    """You are helping people with dyslexia read difficult text.
    Rewrite the text completely in simple everyday English.
    Use words a 12-year-old would know.
    Keep ALL meaning. Return ONLY the rewritten text.""",

    # Prompt 4 — active voice focus
    """You are helping people with dyslexia read difficult text.
    Rewrite the text using active voice only.
    Replace all passive constructions. Use simple words.
    Keep ALL meaning. Return ONLY the rewritten text.""",

    # Prompt 5 — concise simplification, no long explanations
    """You are helping people with dyslexia read difficult text.
    Rewrite the text in simple everyday English.
    Replace hard words with simpler ones directly — do NOT add explanations or definitions.
    Keep the output roughly the same length as the input.
    Keep ALL meaning. Return ONLY the rewritten text."""
]

# Different temperatures give genuinely different rewrites
CANDIDATE_TEMPERATURES = [0.1, 0.3, 0.7, 1.0, 1.2]

def score_difficulty(text):
    """
    Returns average difficulty score of content words.
    Lower = simpler. Uses your XGBoost scorer.
    """
    results = find_difficult_words_in_text(text, threshold=0.0)
    all_scored = results['all_scored']
    if not all_scored:
        return 5.0
    return float(np.mean([w['difficulty_score'] for w in all_scored]))


def semantic_similarity(text_a, text_b):
    """Cosine similarity between sentence embeddings."""
    emb_a = sim_model.encode(text_a, convert_to_tensor=True)
    emb_b = sim_model.encode(text_b, convert_to_tensor=True)
    return float(util.cos_sim(emb_a, emb_b))


def generate_candidate(text, temperature, system_prompt):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Simplify this text:\n\n{text}"}
        ],
        temperature=temperature,
        max_tokens=1024,
    )
    return response.choices[0].message.content.strip()


def simplify_text(text, sim_threshold=0.75, n_candidates=5, hard_words= None):
    """
    Drop-in replacement for the original simplify_text().
    Returns the same dict structure — api.py needs zero changes.
    """
    try:
        if not text or len(text.strip()) == 0:
            return {"error": "Text is empty", "success": False}

        original_score = score_difficulty(text)
        original_word_count = len(text.split())

        # --- Generate N candidates ---
        candidates = []
        for i, temp in enumerate(CANDIDATE_TEMPERATURES[:n_candidates]):
            try:
                prompt = SYSTEM_PROMPTS[i % len(SYSTEM_PROMPTS)]
                if hard_words and len(hard_words) > 0:
                    must_replace  = ', '.join(hard_words)
                    prompt = prompt + f"\n\nCRITICAL: You MUST replace ALL of these specific words with simpler alternatives: {must_replace}\nDo not use any of these words in your output under any circumstances."

                output = generate_candidate(text, temp, prompt)
        
                # skip if model returned input unchanged
                if output.strip().lower() == text.strip().lower():
                    candidates.append({
                        'text':        output,
                        'temperature': temp,
                        'prompt_type': i + 1,
                        'similarity':  1.0,
                        'difficulty':  score_difficulty(output),
                        'flagged':     'identical_to_input'
                    })
                    continue
            
                sim  = semantic_similarity(text, output)
                diff = score_difficulty(output)
                candidates.append({
                    'text':        output,
                    'temperature': temp,
                    'prompt_type': i + 1,  # which strategy generated this
                    'similarity':  round(sim,  3),
                    'difficulty':  round(diff, 3),
                    'flagged':     None
                })
            except Exception as e:
                continue

        if not candidates:
            return {"error": "All candidates failed", "success": False}

        # --- Re-rank: filter by similarity, then pick lowest difficulty ---
        # Filter only clearly bad candidates
        valid = [
            c for c in candidates
            if c['similarity'] >= 0.45          # only reject completely off-topic outputs
            and c.get('flagged') != 'identical_to_input'
            and c['difficulty'] < original_score
        ]

        if not valid:
            valid = [max(candidates, key=lambda c: c['similarity'])]

        # Combined score: weighted balance of difficulty and similarity
        # Lower difficulty = better, higher similarity = better
        # We normalize: difficulty is 0-10, similarity is 0-1
        def combined_score(c):
            difficulty_weight = 0.75
            similarity_weight = 0.25
            length_weight     = 0.15
            normalized_diff = c['difficulty'] / 10.0   # lower is better
            normalized_sim  = 1 - c['similarity']       # lower is better (we want high sim)

            candidate_word_count = len(c['text'].split())
            length_ratio = candidate_word_count / max(original_word_count, 1)
            length_penalty = max(0, length_ratio - 1.0)  # 0 if shorter, grows if longer

            return (difficulty_weight * normalized_diff + 
                    similarity_weight * normalized_sim + 
                    length_weight * length_penalty)

        best = min(valid, key=combined_score)

        simplified = best['text']

        # --- Metrics (same keys as before so api.py works unchanged) ---
        original_flesch   = textstat.flesch_reading_ease(text)
        simplified_flesch = textstat.flesch_reading_ease(simplified)
        improvement       = simplified_flesch - original_flesch

        return {
            "original":          text,
            "simplified":        simplified,
            "original_flesch":   original_flesch,
            "simplified_flesch": simplified_flesch,
            "improvement":       improvement,
            "success":           True,
            # Extra info — visible in /process response, ignored by old callers
            "reranking": {
                "candidates_generated":  len(candidates),
                "candidates_valid":      len(valid),
                "best_temperature":      best['temperature'],
                "best_similarity":       best['similarity'],
                "best_difficulty":       best['difficulty'],
                "original_difficulty":   round(original_score, 3),
                "difficulty_reduction":  round(original_score - best['difficulty'], 3),
                "all_candidates": candidates
            }
        }

    except Exception as e:
        return {"error": str(e), "success": False}

def split_sentences(text):
    """Split text into sentences."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def simplify_sentence_level(text, sim_threshold=0.75):
    """
    Simplify each sentence independently.
    Pick the best candidate per sentence using your scorer.
    Assemble the final output from the best per-sentence winners.
    """
    sentences = split_sentences(text)
    
    # Short texts — don't split, just use standard pipeline
    if len(sentences) <= 1:
        return simplify_text(text, sim_threshold=sim_threshold)
    
    result_sentences = []
    sentence_details = []
    
    for sentence in sentences:
        # Skip very short sentences — not worth simplifying
        if len(sentence.split()) < 5:
            result_sentences.append(sentence)
            sentence_details.append({
                'original':    sentence,
                'simplified':  sentence,
                'action':      'kept_unchanged',
                'reason':      'too short to simplify'
            })
            continue
        
        original_score = score_difficulty(sentence)
        
        # Only simplify sentences that are actually hard
        if original_score < 3.5:
            result_sentences.append(sentence)
            sentence_details.append({
                'original':    sentence,
                'simplified':  sentence,
                'action':      'kept_unchanged',
                'reason':      'already easy',
                'difficulty':  round(original_score, 3)
            })
            continue
        
        # Generate candidates for this sentence
        best_candidate = None
        best_score     = original_score
        all_candidates = []
        
        for i, temp in enumerate(CANDIDATE_TEMPERATURES):
            try:
                prompt    = SYSTEM_PROMPTS[i % len(SYSTEM_PROMPTS)]
                output    = generate_candidate(sentence, temp, prompt)
                sim       = semantic_similarity(sentence, output)
                diff      = score_difficulty(output)
                identical = output.strip().lower() == sentence.strip().lower()
                
                candidate = {
                    'text':        output,
                    'temperature': temp,
                    'prompt_type': i + 1,
                    'similarity':  round(sim,  3),
                    'difficulty':  round(diff, 3),
                    'flagged':     'identical' if identical else None
                }
                all_candidates.append(candidate)
                
                # Update best if this candidate passes all gates
                if (sim >= sim_threshold
                        and diff < best_score
                        and not identical):
                    best_score     = diff
                    best_candidate = candidate
                    
            except Exception:
                continue
        
        if best_candidate:
            result_sentences.append(best_candidate['text'])
            sentence_details.append({
                'original':          sentence,
                'simplified':        best_candidate['text'],
                'action':            'simplified',
                'original_difficulty': round(original_score, 3),
                'final_difficulty':  round(best_score, 3),
                'reduction':         round(original_score - best_score, 3),
                'winning_temp':      best_candidate['temperature'],
                'winning_prompt':    best_candidate['prompt_type'],
                'all_candidates':    all_candidates
            })
        else:
            # No candidate passed — keep original sentence, flag it
            result_sentences.append(sentence)
            sentence_details.append({
                'original':   sentence,
                'simplified': sentence,
                'action':     'unchanged_no_valid_candidate',
                'difficulty': round(original_score, 3),
                'note':       'All candidates failed quality gates'
            })
    
    # Assemble final text
    final_text = ' '.join(result_sentences)
    
    # Compute overall metrics
    original_flesch   = textstat.flesch_reading_ease(text)
    simplified_flesch = textstat.flesch_reading_ease(final_text)
    original_diff     = score_difficulty(text)
    final_diff        = score_difficulty(final_text)
    
    simplified_count  = sum(
        1 for s in sentence_details if s['action'] == 'simplified'
    )
    unchanged_count   = len(sentence_details) - simplified_count
    
    return {
        "original":            text,
        "simplified":          final_text,
        "original_flesch":     original_flesch,
        "simplified_flesch":   simplified_flesch,
        "improvement":         simplified_flesch - original_flesch,
        "success":             True,
        "reranking": {
            "mode":                  "sentence_level",
            "total_sentences":       len(sentences),
            "sentences_simplified":  simplified_count,
            "sentences_unchanged":   unchanged_count,
            "original_difficulty":   round(original_diff, 3),
            "final_difficulty":      round(final_diff,    3),
            "difficulty_reduction":  round(original_diff - final_diff, 3),
        },
        "sentence_details": sentence_details
    }

def simplify_targeted(text, difficulty_threshold=3.5, sim_threshold=0.65):
    """
    Only simplify sentences that are actually hard.
    Easy sentences pass through untouched.
    """
    sentences = split_sentences(text)
    
    result_sentences = []
    details = []
    api_calls_made = 0

    for sentence in sentences:
        words = sentence.split()
        
        # Too short — keep as is
        if len(words) < 5:
            result_sentences.append(sentence)
            details.append({
                'original':   sentence,
                'simplified': sentence,
                'action':     'kept_unchanged',
                'reason':     'too short'
            })
            continue

        # Score this sentence
        sentence_difficulty = score_difficulty(sentence)

        # Easy sentence — keep as is, don't touch it
        if sentence_difficulty < difficulty_threshold:
            result_sentences.append(sentence)
            details.append({
                'original':   sentence,
                'simplified': sentence,
                'action':     'kept_unchanged',
                'reason':     'already easy',
                'difficulty': round(sentence_difficulty, 3)
            })
            continue

        # Hard sentence — find which specific words are causing it
        hard_word_results = find_difficult_words_in_text(sentence, threshold=6.0)
        hard_words = [w['word'] for w in hard_word_results['difficult_words']]

        # Simplify only this sentence, with hard words injected into prompt
        simplified_result = simplify_text(
            sentence,
            sim_threshold=sim_threshold,
            hard_words=hard_words
        )
        api_calls_made += 5  # track cost

        if simplified_result.get('success'):
            simplified_sentence = simplified_result['simplified']
            final_difficulty    = simplified_result['reranking']['best_difficulty']

            result_sentences.append(simplified_sentence)
            details.append({
                'original':            sentence,
                'simplified':          simplified_sentence,
                'action':              'simplified',
                'original_difficulty': round(sentence_difficulty, 3),
                'final_difficulty':    round(final_difficulty, 3),
                'reduction':           round(sentence_difficulty - final_difficulty, 3),
                'hard_words_targeted': hard_words,
                'winning_temp':        simplified_result['reranking']['best_temperature'],
                'winning_strategy':    simplified_result['reranking']['best_temperature'],
            })
        else:
            # Simplification failed — keep original, don't break the output
            result_sentences.append(sentence)
            details.append({
                'original':   sentence,
                'simplified': sentence,
                'action':     'kept_unchanged',
                'reason':     'simplification failed',
                'difficulty': round(sentence_difficulty, 3)
            })

    # Assemble final text — only the hard sentences were rewritten
    final_text = ' '.join(result_sentences)

    # Compute overall metrics
    original_flesch   = textstat.flesch_reading_ease(text)
    simplified_flesch = textstat.flesch_reading_ease(final_text)
    original_diff     = score_difficulty(text)
    final_diff        = score_difficulty(final_text)

    sentences_simplified = sum(1 for d in details if d['action'] == 'simplified')
    sentences_kept       = len(details) - sentences_simplified

    return {
        "original":          text,
        "simplified":        final_text,
        "original_flesch":   original_flesch,
        "simplified_flesch": simplified_flesch,
        "improvement":       round(simplified_flesch - original_flesch, 2),
        "success":           True,
        "reranking": {
            "mode":                  "targeted",
            "total_sentences":       len(sentences),
            "sentences_simplified":  sentences_simplified,
            "sentences_kept":        sentences_kept,
            "api_calls_made":        api_calls_made,
            "original_difficulty":   round(original_diff, 3),
            "final_difficulty":      round(final_diff, 3),
            "difficulty_reduction":  round(original_diff - final_diff, 3),
        },
        "sentence_details": details
    }

if __name__ == "__main__":
    test_texts = [
        "Myocardial infarction occurs when blood flow decreases or stops to a part of the heart, causing damage to the heart muscle.",
        "The defendant, pursuant to the aforementioned contractual obligations stipulated in section 4.2 of the binding agreement, shall be held liable for any consequential damages.",
        "Quantum entanglement is a physical phenomenon that occurs when a group of particles are generated, interact, or share spatial proximity in such a way that the quantum state of each particle cannot be described independently.",
    ]

    print("🧪 Text Simplifier — MBR Re-ranking with Difficulty Scorer\n")
    print("=" * 70)

    for text in test_texts:
        result = simplify_text(text)
        if result.get("success"):
            r = result["reranking"]
            print(f"\n📝 Original  (Flesch: {result['original_flesch']:.1f} | "
                  f"Difficulty: {r['original_difficulty']}):")
            print(f"   {result['original']}")
            print(f"\n✨ Best output (Flesch: {result['simplified_flesch']:.1f} | "
                  f"Difficulty: {r['best_difficulty']} | "
                  f"Temp: {r['best_temperature']} | "
                  f"Sim: {r['best_similarity']}):")
            print(f"   {result['simplified']}")
            print(f"\n📊 Difficulty reduction: {r['difficulty_reduction']:+.3f} | "
                  f"Flesch improvement: {result['improvement']:+.1f}")
            print(f"   Valid candidates: {r['candidates_valid']}/{r['candidates_generated']}")
            print("\n   All candidates:")
            for c in r['all_candidates']:
                    marker = " ← SELECTED" if c['temperature'] == r['best_temperature'] else ""                                                 
                    print(f"   temp={c['temperature']} | "
                      f"diff={c['difficulty']} | "
                      f"sim={c['similarity']}{marker}")
            print("=" * 70)
        else:
            print(f"❌ Error: {result['error']}")