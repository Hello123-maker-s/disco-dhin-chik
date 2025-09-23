import os
import joblib
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sentence_transformers import SentenceTransformer

# ------------------ Paths ------------------ #
BASE_DIR = os.path.dirname(__file__)
CSV_PATH = os.path.join(BASE_DIR, "synthetic_expense_dataset_v2.csv")
MODEL_PATH = os.path.join(BASE_DIR, "expense_classifier_model.pkl")

# ------------------ Main Categories ------------------ #
MAIN_CATEGORIES = [
    "Food & Dining", "Transportation", "Housing & Utilities", "Personal & Shopping",
    "Health & Fitness", "Entertainment & Leisure", "Education", "Financial",
    "Travel & Vacation"
]
MISC_CATEGORY = "Miscellaneous"

# ------------------ Preprocessing (minimal) ------------------ #
def clean_text(text: str) -> str:
    # Just lowercase + strip whitespace
    return str(text).lower().strip()

def preprocess_texts(texts):
    return [clean_text(t) for t in texts]

# ------------------ Embedding ------------------ #
def encode_texts(embedder, texts, batch_size=64):
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        batch_emb = embedder.encode(batch, show_progress_bar=False)
        embeddings.append(batch_emb)
    return np.concatenate(embeddings, axis=0)

# ------------------ Model caching ------------------ #
_model_bundle = None

def load_classifier():
    """Load the model once and cache it in memory."""
    global _model_bundle
    if _model_bundle is None:
        if os.path.exists(MODEL_PATH):
            _model_bundle = joblib.load(MODEL_PATH)
        else:
            _model_bundle = train_classifier(CSV_PATH)
    return _model_bundle

# ------------------ Training ------------------ #
def train_classifier(csv_path=CSV_PATH, save_model=True):
    """Train a classifier from CSV."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if "Merchant_Text" not in df.columns or "Category" not in df.columns:
        raise ValueError("CSV must contain 'Merchant_Text' and 'Category' columns.")

    # Minimal preprocessing
    df["Merchant_Text"] = preprocess_texts(df["Merchant_Text"])

    # Split
    X_train_text, X_test_text, y_train, y_test = train_test_split(
        df["Merchant_Text"], df["Category"], test_size=0.2, stratify=df["Category"], random_state=42
    )

    # Load embedder
    embedder = SentenceTransformer('all-MiniLM-L6-v2')

    # Encode embeddings
    X_train_emb = encode_texts(embedder, X_train_text.tolist())
    X_test_emb = encode_texts(embedder, X_test_text.tolist())

    # Train classifier
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", n_jobs=-1)
    clf.fit(X_train_emb, y_train)

    # Evaluation
    y_pred = clf.predict(X_test_emb)
    print("Accuracy:", accuracy_score(y_test, y_pred))
    print("Macro F1-score:", f1_score(y_test, y_pred, average="macro"))
    print(classification_report(y_test, y_pred, zero_division=0))

    # Cross-validation
    X_emb_all = np.concatenate([X_train_emb, X_test_emb], axis=0)
    y_all = np.concatenate([y_train.values, y_test.values], axis=0)
    cv_scores = cross_val_score(clf, X_emb_all, y_all, cv=5, scoring="f1_macro", n_jobs=-1)
    print("Average CV Macro F1-score:", cv_scores.mean())

    if save_model:
        joblib.dump({"embedder": embedder, "classifier": clf}, MODEL_PATH)
        print(f"Model saved at {MODEL_PATH}")

    global _model_bundle
    _model_bundle = {"embedder": embedder, "classifier": clf}
    return _model_bundle

# ------------------ Prediction ------------------ #
def predict_category(texts):
    """Predict category for a list of merchant texts.
    If the model predicts something outside MAIN_CATEGORIES, map it to 'Miscellaneous'."""
    model_bundle = load_classifier()
    embedder = model_bundle["embedder"]
    clf = model_bundle["classifier"]

    clean_texts_list = preprocess_texts(texts)
    embeddings = encode_texts(embedder, clean_texts_list)
    preds = clf.predict(embeddings)

    # Fallback to Miscellaneous if prediction is unknown
    preds_mapped = [p if p in MAIN_CATEGORIES else MISC_CATEGORY for p in preds]
    return preds_mapped
