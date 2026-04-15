import numpy as np
import pandas as pd 
import os

import os
import numpy as np
import pandas as pd

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # ai/models
AI_DIR   = os.path.dirname(BASE_DIR)                           # ai
DATA_DIR = os.path.join(AI_DIR, 'data')                        # ai/data

# Files
embeddings_path = os.path.join(BASE_DIR, 'word_embeddings_small.npy')
subtlex_path    = os.path.join(DATA_DIR, 'SUBTLEX-US frequency list with PoS and Zipf information.csv')
aoa_path        = os.path.join(DATA_DIR, 'AoA_51715_words.xlsx')

# Load
embeddings = np.load(embeddings_path)
subtlex    = pd.read_csv(subtlex_path)
aoa        = pd.read_excel(aoa_path)

df = subtlex.merge(aoa[['Word', 'AoA_Kup', 'Nphon', 'Freq_pm']], on='Word', how='inner')
df['Nphon'] = df['Nphon'].fillna(df['Nphon'].mean())
df['Freq_pm'] = df['Freq_pm'].fillna(df['Freq_pm'].mean())
df      = df.dropna(subset=['AoA_Kup'])

import re
import pyphen

dic = pyphen.Pyphen(lang='en')


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

df['word_length']         = df['Word'].str.len()
df['confusable_letters']  = (df['Word'].str.count('b') + df['Word'].str.count('p') +
                            df['Word'].str.count('d') + df['Word'].str.count('q'))
df['syllable_count']      = df['Word'].apply(count_syllables)
df['vowel_ratio']         = (df['Word'].str.count('[aeiou]')) / df['word_length']
df['has_silent_letter']   = df['Word'].str.contains('kn|wr|gh|mb|bt|mn').astype(int)
df['has_irregular_grapheme'] = df['Word'].str.contains('ough|aigh|eigh|tion|sion').astype(int)
df['consonant_clusters']  = df['Word'].apply(count_consonant_clusters)

from sklearn.preprocessing import LabelEncoder
le = LabelEncoder()
df['Dom_PoS_SUBTLEX'] = df['Dom_PoS_SUBTLEX'].fillna('Unknown')
df['Dom_PoS_SUBTLEX'] = le.fit_transform(df['Dom_PoS_SUBTLEX'])

linguistic_features = df[['word_length', 'syllable_count', 'confusable_letters',
                           'vowel_ratio', 'has_silent_letter', 'has_irregular_grapheme',
                           'consonant_clusters', 'Dom_PoS_SUBTLEX',
                           'Nphon', 'Freq_pm']].values

X = np.hstack([embeddings, linguistic_features])
y = df['AoA_Kup'].values

from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error

x_train, x_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = XGBRegressor(n_estimators=500, learning_rate=0.05, random_state=42, n_jobs=-1)
model.fit(x_train, y_train)

y_pred = model.predict(x_test)
print(f"MSE: {mean_squared_error(y_test, y_pred):.4f}")
print(f"R2:  {r2_score(y_test, y_pred):.4f}")

import joblib
joblib.dump({
    'model': model,
    'feature_count': X.shape[1]
}, 'bert_difficulty_model.pkl')
print("Model saved")

