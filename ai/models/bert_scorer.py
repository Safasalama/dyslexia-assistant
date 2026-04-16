import re
import numpy as np
import pandas as pd
import pyphen
import joblib
import os
from sentence_transformers import SentenceTransformer

# Get the root directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Build the absolute path to the model
model_path = os.path.join(BASE_DIR, "ai", "models", "bert_difficulty_model.pkl")

# Load the model
data = joblib.load(model_path)
# Load model and embedder once at startup
model    = data['model']
embedder = SentenceTransformer('paraphrase-MiniLM-L3-v2')
dic      = pyphen.Pyphen(lang='en')

csv_path = os.path.join(BASE_DIR, "ai", "data", "SUBTLEX-US frequency list with PoS and Zipf information.csv")
subtlex_df = pd.read_csv(csv_path)
excel_path = os.path.join(BASE_DIR, "ai", "data", "AoA_51715_words.xlsx")
aoa_df = pd.read_excel(excel_path)
nphon_lookup  = aoa_df.set_index('Word')['Nphon'].to_dict()
freq_lookup   = aoa_df.set_index('Word')['Freq_pm'].to_dict()
pos_lookup = subtlex_df.set_index('Word')['Dom_PoS_SUBTLEX'].to_dict()

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

def should_skip_word(word):
    """Return True if word should be excluded from scoring"""
    if len(word) <= 2:
        return True
    if word.lower() in STOP_WORDS:
        return True
    # Skip words that are purely numbers or symbols, but allow apostrophes and hyphens
    if not re.match(r"^[a-zA-Z][a-zA-Z'\-]*[a-zA-Z]$", word):
        return True
    return False

pos_map = {
    'Noun': 1, 'Verb': 2, 'Adjective': 3, 'Adverb': 4,
    'Preposition': 5, 'Conjunction': 6, 'Pronoun': 7,
    'Article': 8, 'Determiner': 9, 'Number': 10,
    'Interjection': 11, 'Name': 12, 'Unknown': 0
}

def get_pos(word):
    pos_str = pos_lookup.get(word, 'Unknown')
    return pos_map.get(pos_str, 0)

def count_syllables(word):
    if not isinstance(word, str) or len(word.strip()) == 0:
        return 0
    try:
        return len(dic.inserted(word).split('-'))
    except:
        return 0

def count_consonant_clusters(word):
    if not isinstance(word, str):
        return 0
    return len(re.findall(r'[bcdfghjklmnpqrstvwxyz]{2,}', word.lower()))

from wordfreq import word_frequency

def get_freq_pm(word):
    """
    Try AoA dataset first. Fall back to wordfreq for unknown words.
    wordfreq returns a proportion (0-1), convert to per-million.
    """
    if word.lower() in freq_lookup:
        return freq_lookup[word.lower()]
    # wordfreq fallback — convert proportion to per-million scale
    freq = word_frequency(word.lower(), 'en')
    return freq * 1_000_000  # e.g. 0.000045 → 45 per million

def score_word_bert(word):
    word_lower = word.lower()
    length      = len(word)
    syllables   = count_syllables(word)
    confusable  = word.count('b') + word.count('p') + word.count('d') + word.count('q')
    silent      = 1 if any(p in word for p in ['kn', 'wr', 'gh', 'mb', 'bt', 'mn']) else 0
    irregular   = 1 if any(p in word for p in ['ough', 'aigh', 'eigh', 'tion', 'sion']) else 0
    clusters    = count_consonant_clusters(word)
    vowels      = sum(1 for c in word if c in 'aeiou')
    vowel_ratio = vowels / length if length > 0 else 0
    pos = get_pos(word_lower)
    nphon   = nphon_lookup.get(word_lower, 6)    # use real value if available
    freq_pm = get_freq_pm(word_lower)

    # get BERT embedding
    embedding = embedder.encode(word)

    # combine all features
    linguistic = np.array([length, syllables, confusable, vowel_ratio,
                           silent, irregular, clusters, pos, nphon, freq_pm])
    features = np.hstack([embedding, linguistic]).reshape(1, -1)

    aoa_predicted = model.predict(features)[0]
    difficulty = (aoa_predicted - 3.0) / (16.0 - 3.0) * 10

    # Classify difficulty level
    if difficulty < 3:
        level = "Easy"
    elif difficulty < 6:
        level = "Medium"
    else:
        level = "Hard"

    # Build reasons list
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
    if aoa_predicted >= 10.0 and not reasons:
        reasons.append("Rarely encountered word")
    if freq_pm < 5.0:
        reasons.append("Uncommon in everyday reading")

    
    return {
    'word': word,
    'difficulty_score': round(float(difficulty), 2),
    'difficulty_level': level,
    'aoa': round(float(aoa_predicted), 2),
    'reasons': reasons,
    'features': {
        'syllables': int(syllables),
        'length': int(length),
        'confusable_letters': int(confusable)
    }
}

def find_difficult_words_in_text(text, threshold=5.0):
    """
    Find all difficult words in text above threshold
    Also returns document frequency (how many times each word appears).
    """
    all_words = re.findall(r'\b[a-zA-Z]+\b', text)

    word_freq = {}
    for word in all_words:
        key = word.lower()
        if not should_skip_word(word):
            word_freq[key] = word_freq.get(key, 0)+1

    all_scored = []
    difficult_words = []
    seen = set()

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
        'all_scored': all_scored,
        'difficult_words': difficult_words
    }        

print(score_word_bert("the"))
print(score_word_bert("cat"))
print(score_word_bert("straightforwardness"))
print(score_word_bert("deoxyribonucleic"))