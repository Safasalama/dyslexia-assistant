from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

import joblib
import os
import sys

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
    import string
    words = input.text.split()
    words = [w.strip(string.punctuation) for w in input.text.split()]
    words = [w for w in words if len(w) > 0]
    word_scores  = {word: score_word_bert(word) for word in words}

    hardest = find_difficult_words_in_text(input.text, threshold=5.0)
    scores_only = [v['difficulty_score'] for v in word_scores.values()]
    overall = round(float(sum(scores_only) / len(scores_only)), 2)


    return {
        "words":              word_scores,
        "overall_difficulty": overall,
        "hardest_words":      [w['word'] for w in hardest]
    }

from groq import Groq
from ai.sevices.simplifier_groq import simplify_text

groq_client = Groq(api_key=("GROQ_API_KEY"))

@app.post("/simplify")
def simplify(input: TextInput):
    # call groq here and return simplified text
    result = simplify_text(input.text)
    return result

@app.post("/process")
def process(input: TextInput):
    # step 1: analyze original text
    original_analysis = analyze(input)
    # step 2: simplify the text
    simplified = simplify_text(input.text)
    # step 3: analyze simplified text
    simplified_analysis = analyze(TextInput(text=simplified['simplified']))
    # step 4: return everything
    return{
        "original":           input.text,
        "simplified":         simplified['simplified'],
        "original_analysis":  original_analysis,
        "simplified_analysis": simplified_analysis,
        "flesch_improvement": simplified['improvement']

    }
    
    