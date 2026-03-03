from typing import List
import os
from openai import AzureOpenAI, OpenAI

# configure Azure OpenAI for embeddings, sharing the same endpoint/key as the
# LLM helpers.  Make sure the environment variables are set in .env.

_client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    api_version=os.environ.get("LLM_API_VERSION", "2024-12-01-preview"),
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT"),
)

# _client = OpenAI(
#     api_key=os.environ.get("OPENAI_API_KEY1")
# )
EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")


def get_embedding(text: str) -> List[float]:
    """Return a fixed‑size vector for the given text using Azure OpenAI.

    The embedding dimension must match the vector size of the
    `embedding` columns (1536).
    """
    resp = _client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding
