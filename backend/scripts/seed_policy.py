from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from sentence_transformers import SentenceTransformer

encoder = SentenceTransformer('all-MiniLM-L6-v2')
client = QdrantClient("localhost", port=6333)
COLLECTION_NAME = "corporate_policies"

policies = [
    "Strict Policy: All GPL v2 or v3 licenses are FORBIDDEN in our SaaS products.",
    "Strict Policy: AGPL licenses are strictly PROHIBITED.",
    "Policy: MIT, Apache 2.0, and BSD licenses are SAFE.",
    "Policy: Any package with more than 3 vulnerabilities must be flagged as FORBIDDEN."
]

def seed():
    # Drop existing collection if present
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    
    # Recreate collection
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )
    print(f"--- COLLECTION '{COLLECTION_NAME}' CREATED ---")
    
    # Prepare points
    points = []
    for i, text in enumerate(policies):
        vector = encoder.encode(text).tolist()
        points.append(PointStruct(id=i, vector=vector, payload={"text": text}))
    
    # Upsert into database
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print("--- POLICY SEEDED SUCCESSFULLY ---")

if __name__ == "__main__":
    seed()
