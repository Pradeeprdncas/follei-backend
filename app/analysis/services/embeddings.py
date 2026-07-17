import logging
import torch
from transformers import AutoModel, AutoTokenizer
from app.config.settings import get_settings

_settings = get_settings()

logger = logging.getLogger(__name__)


class EmbeddingsService:
    def __init__(self):
        self.tokenizer = None
        self.model = None

    def initialize(self):
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(_settings.EMBEDDING_MODEL)
            self.model = AutoModel.from_pretrained(_settings.EMBEDDING_MODEL)
            self.model.eval()
            if torch.cuda.is_available():
                self.model = self.model.to("cuda")
            logger.info("Embedding model loaded: %s", _settings.EMBEDDING_MODEL)
            return True
        except Exception as e:
            logger.warning("Failed to initialize embedding model: %s. RAG will not work.", str(e))
            self.tokenizer = None
            self.model = None
            return False

    @torch.inference_mode()
    def embed(self, texts):
        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Embedding model is not initialized")

        if isinstance(texts, str):
            texts = [texts]
        inputs = self.tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        outputs = self.model(**inputs)
        vector = outputs.last_hidden_state[:, 0, :]
        return vector.detach().cpu().numpy().tolist()


embeddings_service = EmbeddingsService()
