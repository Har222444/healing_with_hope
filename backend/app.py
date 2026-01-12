from fastapi import FastAPI, HTTPException
import joblib
import os

app = FastAPI()

# Paths
MODEL_PATH = "models/mental_health_model.pkl"
VECTORIZER_PATH = "models/tfidf_vectorizer.pkl"
ENCODER_PATH = "models/label_encoder.pkl"

# Load files
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError("Model file not found")

model = joblib.load(MODEL_PATH)
vectorizer = joblib.load(VECTORIZER_PATH)
label_encoder = joblib.load(ENCODER_PATH)

@app.post("/predict")
def predict(data: dict):
    """
    Example input:
    {
        "text": "I feel very anxious and stressed"
    }
    """

    text = data.get("text")

    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Transform text
    X = vectorizer.transform([text])

    # Predict
    prediction = model.predict(X)
    label = label_encoder.inverse_transform(prediction)[0]

    return {
        "prediction": label
    }
