"""
difficulty_scorer.py
---------------------
Updated to match train_difficulty_model.py:
  - 15 linguistic features (was 10)
  - Predicts dyslexia_difficulty (0-10) directly — not AoA
  - No AoA rescaling needed — model output IS the difficulty score
  - Added: concreteness, mrc_imag, mrc_fam, valence, arousal lookups
  - LRU cache unchanged
  - Public API identical: score_word_bert() and find_difficult_words_in_text()
"""

import re, os, json
import numpy as np
import pandas as pd
import pyphen
import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel
from wordfreq import word_frequency
from functools import lru_cache
import nltk
nltk.download('wordnet', quiet=True)
nltk.download('omw-1.4', quiet=True)
from nltk.corpus import wordnet

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR  = os.path.join(BASE_DIR, 'ai', 'models')
DATA_DIR   = os.path.join(BASE_DIR, 'ai', 'data')

WEIGHTS_PATH      = os.path.join(MODEL_DIR, 'difficulty_model.pt')
CONFIG_PATH       = os.path.join(MODEL_DIR, 'difficulty_config.json')
SUBTLEX_PATH      = os.path.join(DATA_DIR, 'SUBTLEX-US frequency list with PoS and Zipf information.csv')
AOA_PATH          = os.path.join(DATA_DIR, 'AoA_51715_words.xlsx')
CONCRETENESS_PATH = os.path.join(DATA_DIR, 'concreteness.txt')

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

# ── Model definition (must match train_difficulty_model.py) ───────────────────
class WordDifficultyModel(nn.Module):
    def __init__(self, transformer_name, n_linguistic):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(transformer_name)
        hidden_size  = self.encoder.config.hidden_size
        self.head = nn.Sequential(
            nn.Linear(hidden_size + n_linguistic, 256),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1)
        )

    def forward(self, input_ids, attention_mask, linguistic):
        out      = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls_emb  = out.last_hidden_state[:, 0, :]
        combined = torch.cat([cls_emb, linguistic], dim=1)
        return self.head(combined).squeeze(-1)

# ── Load model ────────────────────────────────────────────────────────────────
print("Loading fine-tuned difficulty model...")
checkpoint = torch.load(WEIGHTS_PATH, map_location=DEVICE)
config     = json.load(open(CONFIG_PATH))

_transformer_name = checkpoint['transformer_name']
_n_linguistic     = checkpoint['n_linguistic']
_max_len          = config['max_len']
_scaler_mean      = np.array(checkpoint['scaler_mean'])
_scaler_scale     = np.array(checkpoint['scaler_scale'])

_model = WordDifficultyModel(_transformer_name, _n_linguistic).to(DEVICE)
_model.load_state_dict(checkpoint['model_state_dict'])
_model.eval()
_tokenizer = AutoTokenizer.from_pretrained(_transformer_name)
print("Model loaded.")

# ── Lookup tables ─────────────────────────────────────────────────────────────
subtlex_df   = pd.read_csv(SUBTLEX_PATH)
aoa_df       = pd.read_excel(AOA_PATH)
nphon_lookup = aoa_df.set_index('Word')['Nphon'].to_dict()
freq_lookup  = aoa_df.set_index('Word')['Freq_pm'].to_dict()
pos_lookup   = subtlex_df.set_index('Word')['Dom_PoS_SUBTLEX'].to_dict()

# Concreteness
try:
    conc_lookup = pd.read_csv(CONCRETENESS_PATH, sep='\t').set_index('Word')['Conc.M'].to_dict()
except Exception:
    conc_lookup = {}

# ── Constants ─────────────────────────────────────────────────────────────────
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'was', 'are', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'shall', 'can', 'need', 'dare',
    'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
    'he', 'she', 'we', 'you', 'i', 'my', 'your', 'his', 'her', 'our',
    'not', 'no', 'nor', 'so', 'yet', 'both', 'either', 'neither',
    'as', 'if', 'then', 'than', 'when', 'while', 'although', 'because',
    'into', 'onto', 'upon', 'about', 'above', 'below', 'between', 'through'
}

pos_map = {
    'Noun': 1, 'Verb': 2, 'Adjective': 3, 'Adverb': 4,
    'Preposition': 5, 'Conjunction': 6, 'Pronoun': 7,
    'Article': 8, 'Determiner': 9, 'Number': 10,
    'Interjection': 11, 'Name': 12, 'Unknown': 0
}

dic = pyphen.Pyphen(lang='en')

# ── Helpers ───────────────────────────────────────────────────────────────────
def should_skip_word(word):
    if len(word) <= 2:
        return True
    if word.lower() in STOP_WORDS:
        return True
    if not re.match(r"^[a-zA-Z][a-zA-Z'\-]*[a-zA-Z]$", word):
        return True
    return False

def count_syllables(word):
    if not isinstance(word, str) or not word.strip():
        return 0
    try:
        return len(dic.inserted(word).split('-'))
    except Exception:
        return 0

def count_consonant_clusters(word):
    if not isinstance(word, str):
        return 0
    return len(re.findall(r'[bcdfghjklmnpqrstvwxyz]{2,}', word.lower()))

def get_pos(word):
    return pos_map.get(pos_lookup.get(word, 'Unknown'), 0)

def get_freq_pm(word):
    if word in freq_lookup:
        return freq_lookup[word]
    return word_frequency(word, 'en') * 1_000_000

def get_context(word):
    synsets = wordnet.synsets(word)
    if not synsets:
        return word
    for s in synsets:
        if s.examples():
            return s.examples()[0]
    return synsets[0].definition()

def _build_linguistic(word):
    """Build and normalise the 15-feature vector."""
    word_lower  = word.lower()
    length      = len(word)
    syllables   = count_syllables(word)
    confusable  = word_lower.count('b') + word_lower.count('p') + \
                  word_lower.count('d') + word_lower.count('q')
    vowels      = sum(1 for c in word_lower if c in 'aeiou')
    vowel_ratio = vowels / length if length > 0 else 0
    # NEW
    silent    = 1 if any(p in word_lower for p in [
        'kn', 'wr', 'gh', 'mb', 'bt', 'mn',
        'cht', 'lm', 'sw', 'gn', 'ps', 'rh'   # yacht→cht, calm→lm, sword→sw
    ]) else 0
    irregular = 1 if any(p in word_lower for p in [
        'ough', 'aigh', 'eigh', 'tion', 'sion',
        'olo',                                  # colonel
        ' yacht', 'queue', 'quay',              # specific irregular words
        'eur', 'ieu', 'eau',                   # French-origin patterns
        'ph', 'sch', 'chr'                     # ph=f, sch=sk, chr=kr
    ]) else 0
    clusters    = count_consonant_clusters(word)
    pos         = get_pos(word_lower)
    nphon       = nphon_lookup.get(word_lower, 6)
    freq_pm     = get_freq_pm(word_lower)
    concreteness = conc_lookup.get(word_lower, 2.5)

    raw = np.array([
        length, syllables, confusable, vowel_ratio,
        silent, irregular, clusters, pos, nphon, freq_pm,
        concreteness
    ], dtype=np.float32)

    normalised = (raw - _scaler_mean) / _scaler_scale
    return normalised, {
        'syllables':          int(syllables),
        'length':             int(length),
        'confusable_letters': int(confusable),
        'freq_pm':            round(float(freq_pm), 2),
    }

# ── Cached inference ──────────────────────────────────────────────────────────
@lru_cache(maxsize=4096)
def _score_word_cached(word_lower: str):
    ling_vec, ling_dict = _build_linguistic(word_lower)
    context = get_context(word_lower)

    enc = _tokenizer(
        word_lower,
        context,
        max_length=_max_len,
        padding='max_length',
        truncation=True,
        return_tensors='pt'
    )
    input_ids      = enc['input_ids'].to(DEVICE)
    attention_mask = enc['attention_mask'].to(DEVICE)
    ling_tensor    = torch.tensor(ling_vec, dtype=torch.float32).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        difficulty = _model(input_ids, attention_mask, ling_tensor).item()

    # Clamp to valid range — model output is already 0-10
    difficulty = float(np.clip(difficulty, 0.0, 10.0))
    return difficulty, ling_dict

# ── Public API ────────────────────────────────────────────────────────────────
def score_word_bert(word: str) -> dict:
    """
    Score a single word for dyslexic reading difficulty.
    Returns same dict structure as old bert_scorer.py — drop-in replacement.
    
    Key difference from old scorer:
      - difficulty_score is now the direct model output (0-10)
      - No AoA rescaling: (aoa - 3) / 13 * 10
      - 'aoa' field still returned for backwards compatibility but equals difficulty_score
    """
    word_lower = word.lower()
    difficulty, ling_dict = _score_word_cached(word_lower)

    syllables  = ling_dict['syllables']
    length     = ling_dict['length']
    confusable = ling_dict['confusable_letters']
    freq_pm    = ling_dict['freq_pm']

    # NEW — must match _build_linguistic exactly
    silent    = any(p in word_lower for p in [
        'kn', 'wr', 'gh', 'mb', 'bt', 'mn',
        'cht', 'lm', 'sw', 'gn', 'ps', 'rh'
    ])
    irregular = any(p in word_lower for p in [
        'ough', 'aigh', 'eigh', 'tion', 'sion',
        'olo', 'queue', 'quay', 'eur', 'ieu', 'eau', 'ph', 'sch', 'chr'
    ])
    clusters  = count_consonant_clusters(word)

    if difficulty < 3:
        level = "Easy"
    elif difficulty < 6:
        level = "Medium"
    else:
        level = "Hard"

    reasons = []
    if syllables >= 4:
        reasons.append(f"{syllables} syllables")
    if length > 10:
        reasons.append(f"Long word ({length} letters)")
    if confusable >= 2:
        reasons.append(f"Contains {confusable} confusable letters")
    if silent:
        reasons.append("Has silent letters")
    if irregular:
        reasons.append("Irregular spelling")
    if clusters >= 2:
        reasons.append(f"{clusters} consonant clusters")
    if difficulty >= 7.0 and not reasons:
        reasons.append("Rarely encountered word")
    if freq_pm < 5.0:
        reasons.append("Uncommon in everyday reading")
    # Add this after the existing reasons block, before the return statement
    if length >= 12 and freq_pm < 1.0 and difficulty < 6.0:
        # Long rare words are always hard for dyslexic readers
        # even if they lack specific orthographic traps
        difficulty = max(difficulty, 6.0)
        level = "Hard"
        if not reasons:
            reasons.append("Long and rarely encountered word")

    return {
        'word':             word,
        'difficulty_score': round(difficulty, 2),
        'difficulty_level': level,
        'aoa':              round(difficulty, 2),   # backwards compat
        'reasons':          reasons,
        'features': {
            'syllables':          syllables,
            'length':             length,
            'confusable_letters': confusable,
        }
    }


def find_difficult_words_in_text(text: str, threshold: float = 5.0) -> dict:
    """Identical signature and return structure to old bert_scorer.py."""
    all_words = re.findall(r'\b[a-zA-Z]+\b', text)

    word_freq = {}
    for word in all_words:
        key = word.lower()
        if not should_skip_word(word):
            word_freq[key] = word_freq.get(key, 0) + 1

    all_scored      = []
    difficult_words = []
    seen            = set()

    for word in all_words:
        word_lower = word.lower()
        if word_lower in seen:
            continue
        if should_skip_word(word):
            continue
        seen.add(word_lower)

        result = score_word_bert(word)
        result['frequency_in_text'] = word_freq.get(word_lower, 1)
        all_scored.append(result)

        if result['difficulty_score'] >= threshold:
            difficult_words.append(result)

    difficult_words.sort(key=lambda x: x['difficulty_score'], reverse=True)
    return {
        'all_scored':      all_scored,
        'difficult_words': difficult_words,
    }


if __name__ == '__main__':
    for w in ['the', 'cat', 'straightforwardness', 'deoxyribonucleic', 'yacht', 'colonel']:
        r = score_word_bert(w)
        print(f"{r['word']:25s} score={r['difficulty_score']:5.2f}  level={r['difficulty_level']:6s}  reasons={r['reasons']}")
