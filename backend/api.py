from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

import joblib
import os
import sys
import re
import numpy as np 

app = FastAPI(title="Dyslexia Assistant API")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # points to dyslexia assistant/
sys.path.append(BASE_DIR)
model_path = os.path.join(BASE_DIR, "ai", "models", "bert_difficulty_model.pkl")

data = joblib.load(model_path)
model = data["model"]
feature_columns = data["feature_count"]

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Dyslexia Assistant API is running"}

class TextInput(BaseModel):
    text: str

from ai.models.bert_scorer import score_word_bert, find_difficult_words_in_text
@app.post("/analyze")
def analyze(input: TextInput):

    results     = find_difficult_words_in_text(input.text, threshold=5.0)
    all_scored = results['all_scored']  
    hard_words  = results['difficult_words']  

    all_scores   = [w['difficulty_score'] for w in all_scored]
    total_words  = len(all_scores)
    hard_count   = len(hard_words)
    hard_density = round(hard_count / total_words * 100, 1)
    p90_score    = round(float(np.percentile(all_scores, 90)), 2)
    max_word     = hard_words[0] if hard_words else None

    total_frequency     = sum(w['frequency_in_text'] for w in hard_words)
    weighted_difficulty = round(
        sum(w['difficulty_score'] * w['frequency_in_text'] for w in hard_words) / total_frequency, 2
    ) if total_frequency > 0 else 0.0

    if hard_density < 5:
        reading_level = "Easy"
    elif hard_density < 15:
        reading_level = "Moderate"
    elif hard_density < 30:
        reading_level = "Challenging"
    else:
        reading_level = "Very Difficult"

    return {
        "summary": {
            "total_content_words": total_words,
            "hard_word_count":     hard_count,
            "hard_word_density":   f"{hard_density}%",
            "weighted_difficulty": weighted_difficulty,
            "p90_score":           p90_score,
            "hardest_word":        max_word['word'] if max_word else None,
            "hardest_word_score":  max_word['difficulty_score'] if max_word else None,
            "reading_level":       reading_level
        },
        "hard_words": hard_words
    }
    

from groq import Groq
from ai.sevices.simplifier_groq import simplify_text, simplify_sentence_level

groq_client = Groq(api_key=("GROQ_API_KEY"))

@app.post("/simplify")
def simplify(input: TextInput, mode: str = "sentence"):
    if mode == "sentence":
        result = simplify_sentence_level(input.text)
    else:
        result = simplify_text(input.text)
    return result

@app.post("/process")
def process(input: TextInput, user_view: bool = False):
    # step 1 — analyze original
    original_analysis = analyze(input)

    # step 2 — simplify using ranked candidate pipeline
    simplified = simplify_text(input.text)
    if not simplified.get('success'):
        return {"error": simplified.get('error'), "success": False}

    simplified_text = simplified['simplified']

    # step 3 — analyze simplified
    simplified_analysis = analyze(TextInput(text=simplified_text))

    # step 4 — compute the diff
    original_hard   = {w['word']: w for w in original_analysis['hard_words']}
    simplified_hard = {w['word']: w for w in simplified_analysis['hard_words']}

    eliminated = [
        word for word in original_hard
        if word not in simplified_hard
    ]

    survived = [
        {
            'word':             word,
            'original_score':   original_hard[word]['difficulty_score'],
            'simplified_score': simplified_hard[word]['difficulty_score'],
            'improved':         simplified_hard[word]['difficulty_score'] < original_hard[word]['difficulty_score']
        }
        for word in original_hard
        if word in simplified_hard
    ]

    introduced = [
        word for word in simplified_hard
        if word not in original_hard
    ]

    # step 5 — verdict
    original_density   = float(original_analysis['summary']['hard_word_density'].replace('%', ''))
    simplified_density = float(simplified_analysis['summary']['hard_word_density'].replace('%', ''))
    density_reduction  = round(original_density - simplified_density, 1)

    original_diff  = simplified['reranking']['original_difficulty']
    final_diff     = simplified['reranking']['best_difficulty']
    diff_reduction = round(original_diff - final_diff, 3)

    if diff_reduction >= 1.5 and density_reduction >= 20:
        verdict = "Highly effective — significant vocabulary and density improvement"
    elif diff_reduction >= 0.8 or density_reduction >= 15:
        verdict = "Effective — meaningful improvement in readability"
    elif diff_reduction >= 0.3 or density_reduction >= 5:
        verdict = "Moderate — some improvement but hard words remain"
    elif len(introduced) > len(eliminated):
        verdict = "Ineffective — simplification introduced new hard words"
    else:
        verdict = "Minimal — text was already near its simplest form"

    # step 6 — user view
    if user_view:
        before_level = original_analysis['summary']['reading_level']
        after_level  = simplified_analysis['summary']['reading_level']

        summary = (
            f"We replaced {len(eliminated)} difficult words. "
            f"This text went from {before_level} to {after_level} reading level."
        )

        if len(survived) > 0:
            survived_names = ', '.join([w['word'] for w in survived])
            summary += f" Some hard words could not be replaced: {survived_names}."

        if len(introduced) > 0:
            summary += f" Watch out for {len(introduced)} new word(s) that may be tricky."

        words_to_watch = []
        for w in simplified_analysis['hard_words'][:5]:
            words_to_watch.append({
                'word': w['word'],
                'why':  w['reasons'][0] if w['reasons'] else 'Rarely encountered word',
                'difficulty': w['difficulty_level']
            })

        return {
            "original":            input.text,
            "simplified":          simplified_text,
            "reading_level":       {"before": before_level, "after": after_level},
            "improvement_summary": summary,
            "words_to_watch":      words_to_watch
        }

    # step 7 — full technical response for developers
    return {
        "original":   input.text,
        "simplified": simplified_text,

        "verdict": {
            "label":                 verdict,
            "hard_words_eliminated": len(eliminated),
            "hard_words_survived":   len(survived),
            "hard_words_introduced": len(introduced),
            "density_reduction":     f"{density_reduction}%",
            "difficulty_reduction":  diff_reduction,
            "flesch_improvement":    round(simplified['improvement'], 1),
            "semantic_similarity":   simplified['reranking']['best_similarity'],
            "winning_strategy":      simplified['reranking']['best_temperature'],
        },

        "diff": {
            "eliminated": eliminated,
            "survived":   survived,
            "introduced": introduced,
        },

        "original_analysis":   original_analysis,
        "simplified_analysis": simplified_analysis,
        "simplification_meta": simplified['reranking']
    }