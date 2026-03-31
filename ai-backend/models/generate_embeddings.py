import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# Load model
embedder = SentenceTransformer('paraphrase-MiniLM-L3-v2')

# Load merged dataset
subtlex = pd.read_csv('SUBTLEX-US frequency list with PoS and Zipf information.csv')
aoa     = pd.read_excel('AoA_51715_words.xlsx')
df      = subtlex.merge(aoa[['Word', 'AoA_Kup', 'Nphon', 'Freq_pm']], on='Word', how='inner')
df      = df.dropna(subset=['AoA_Kup'])

words = [str(w) for w in df['Word'].tolist()]

# Generate in batches
embeddings = []
batch_size = 256  # larger batch = faster

for i in tqdm(range(0, len(words), batch_size)):
    batch = words[i:i+batch_size]
    batch_embeddings = embedder.encode(batch, show_progress_bar=False)
    embeddings.append(batch_embeddings)

embeddings = np.vstack(embeddings)
np.save('word_embeddings_small.npy', embeddings)
print(f"Saved: {embeddings.shape}")