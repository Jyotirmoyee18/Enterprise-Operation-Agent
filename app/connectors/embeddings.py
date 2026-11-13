from functools import lru_cache
from sentence_transformers import SentenceTransformer
from app.core.config import settings

@lru_cache(maxsize=1)
def model():
    return SentenceTransformer(settings.embedding_model)

def embed(text: str) -> list[float]:
    return model().encode(text, normalize_embeddings=True).tolist()
