import joblib
from xgboost import XGBRegressor

# Load old model
data  = joblib.load('ai/models/bert_difficulty_model.pkl')
model = data['model']

# Resave the booster in current XGBoost format
model.get_booster().save_model('ai/models/xgb_booster.json')

# Save updated pkl with json path reference
joblib.dump({
    'model':         model,
    'feature_count': data['feature_count']
}, 'ai/models/bert_difficulty_model.pkl')

print("Resaved successfully")