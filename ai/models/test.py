from difficulty_scorer import score_word_bert

test_words = [
    # Should be easy (score < 3)
    'cat', 'dog', 'run', 'house', 'eat',
    # Should be medium (score 3-6)
    'system', 'machine', 'process', 'language',
    # Should be hard (score > 6)
    'deoxyribonucleic', 'straightforwardness', 'indemnification',
    # Dyslexia-specific traps — irregular spelling, visually confusable
    'yacht', 'colonel', 'pneumonia', 'Wednesday',
    # Common but abstract
    'justice', 'democracy', 'philosophy',
]

for word in test_words:
    r = score_word_bert(word)
    print(f"{word:25s} {r['difficulty_score']:5.2f}  {r['difficulty_level']:6s}  {r['reasons']}")