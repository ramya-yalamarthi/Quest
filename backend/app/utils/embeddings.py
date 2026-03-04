from typing import List
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from app.config import EMBEDDING_PROVIDER, LOCAL_EMBEDDING_MODEL, EMBEDDING_DIM

load_dotenv()

_local_model = None


def _get_provider() -> str:
    return EMBEDDING_PROVIDER.strip().lower()


def _get_local_model():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        model_name = LOCAL_EMBEDDING_MODEL
        _local_model = SentenceTransformer(model_name, device="cpu")
    return _local_model


def _match_dim(vector: List[float], dim: int) -> List[float]:
    if len(vector) == dim:
        return vector
    if len(vector) > dim:
        return vector[:dim]
    return vector + [0.0] * (dim - len(vector))


def _get_cloud_client() -> AzureOpenAI:
    endpoint = os.getenv("OPENAI_ENDPOINT")
    api_key = os.getenv("OPENAI_API_KEY")
    api_version = os.getenv("LLM_API_VERSION", "2024-12-01-preview")
    embedding_model = os.getenv("EMBEDDING_MODEL")

    if not all([endpoint, api_key, embedding_model]):
        raise RuntimeError("Missing Azure OpenAI embedding configuration")

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )


def get_embedding(text: str) -> List[float]:
    """Return a fixed‑size vector for the given text.

    Provider is controlled by EMBEDDING_PROVIDER=local|cloud.
    """
    provider = _get_provider()
    if provider == "cloud":
        client = _get_cloud_client()
        model = os.getenv("EMBEDDING_MODEL")
        resp = client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding

    model = _get_local_model()
    vector = model.encode([text], normalize_embeddings=True)[0].tolist()
    return _match_dim(vector, EMBEDDING_DIM)