import os
import pickle
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "model", "model.pkl")


def build_feature_text(item):
    return " ".join([
        str(item.get("category", "")).lower(),
        str(item.get("category", "")).lower(),
        str(item.get("type", "")).lower(),
        str(item.get("type", "")).lower(),
        str(item.get("type", "")).lower(),
        str(item.get("size", "")).lower(),
        str(item.get("size", "")).lower(),
        str(item.get("condition", "")).lower(),
        str(item.get("tags", "")).lower(),
        str(item.get("tags", "")).lower(),
        str(item.get("title", "")).lower()
    ])


def load_model():
    if not os.path.exists(MODEL_PATH):
        raise Exception("Model not found. Run train_model.py")

    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def recommend_similar_items(current_item, top_n=4):
    model = load_model()

    items_data = model["items_data"]
    vectorizer = model["vectorizer"]
    tfidf_matrix = model["tfidf_matrix"]

    current_vector = vectorizer.transform([build_feature_text(current_item)])
    similarity_scores = cosine_similarity(current_vector, tfidf_matrix).flatten()

    results = []

    for i, item in enumerate(items_data):

        if item["id"] == current_item["id"]:
            continue

        score = float(similarity_scores[i])

        # STRONG FILTERING (IMPORTANT)
        if item["category"] != current_item["category"]:
            continue

        # Boost scoring
        if item["type"] == current_item["type"]:
            score += 0.6

        if item["size"] == current_item["size"]:
            score += 0.2

        if item["condition"] == current_item["condition"]:
            score += 0.1

        results.append({
            **item,
            "similarity_score": round(score, 3)
        })

    results.sort(key=lambda x: x["similarity_score"], reverse=True)

    return results[:top_n]