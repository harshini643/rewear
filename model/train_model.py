import os
import sqlite3
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, "database", "rewear.db")
MODEL_PATH = os.path.join(BASE_DIR, "model", "model.pkl")


def build_feature_text(item):
    category = str(item.get("category", "")).lower()
    item_type = str(item.get("type", "")).lower()
    size = str(item.get("size", "")).lower()
    condition = str(item.get("condition", "")).lower()
    tags = str(item.get("tags", "")).lower()
    title = str(item.get("title", "")).lower()

    return " ".join([
        category, category, category,
        item_type, item_type, item_type, item_type,
        size, size, size,
        condition, condition,
        tags, tags,
        title
    ])


def fetch_items_from_database():
    if not os.path.exists(DATABASE_PATH):
        return []

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, title, category, type, size, condition, tags, points, image
        FROM items
        WHERE approved = 1 AND status = 'available'
    """).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def fallback_synthetic_items():
    return [
        {"id": 1, "title": "Floral Kurti", "category": "Women", "type": "Top", "size": "M", "condition": "Like New", "tags": "kurti floral ethnic", "points": 60, "image": "floral_kurti.png"},
        {"id": 2, "title": "Blue Denim Jacket", "category": "Women", "type": "Jacket", "size": "S", "condition": "Good", "tags": "denim jacket casual blue", "points": 80, "image": "blue_denim_jacket.jpg"},
        {"id": 3, "title": "Ethnic Saree", "category": "Women", "type": "Saree", "size": "Free", "condition": "Excellent", "tags": "saree silk ethnic festival", "points": 120, "image": "ethnic_saree.png"},
        {"id": 4, "title": "Winter Coat", "category": "Women", "type": "Coat", "size": "M", "condition": "Excellent", "tags": "coat winter woollen warm", "points": 150, "image": "winter_coat.jpg"},
        {"id": 5, "title": "Lehanga", "category": "Women", "type": "Dress", "size": "M", "condition": "Good", "tags": "lehanga festive ethnic pink wedding", "points": 80, "image": "lehanga.jpg"},
        {"id": 6, "title": "Kids Summer Dress", "category": "Kids", "type": "Dress", "size": "5-6Y", "condition": "Good", "tags": "dress kids summer", "points": 40, "image": "kids_summer_dress.jpg"},
        {"id": 7, "title": "Men's Formal Shirt", "category": "Men", "type": "Shirt", "size": "L", "condition": "Like New", "tags": "formal shirt white office", "points": 55, "image": "mens_formal_shirt.jpg"},
        {"id": 8, "title": "Sports T-Shirt", "category": "Men", "type": "T-Shirt", "size": "M", "condition": "Good", "tags": "sports tshirt nike casual", "points": 45, "image": "sports_tshirt.png"}
    ]


def train_and_save_model():
    items_data = fetch_items_from_database()

    if len(items_data) < 4:
        items_data = fallback_synthetic_items()

    documents = [build_feature_text(item) for item in items_data]

    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(documents)

    model_data = {
        "items_data": items_data,
        "vectorizer": vectorizer,
        "tfidf_matrix": tfidf_matrix
    }

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    print("model.pkl created successfully from database items.")


if __name__ == "__main__":
    train_and_save_model()