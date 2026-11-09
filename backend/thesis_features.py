"""
thesis_features.py - feature extraction exactly as described in the thesis (Chapter 3).

  text   : EmbeddingGemma, Matryoshka (MRL) truncated to 256 dimensions, L2-normalized
  image  : MobileNetV2 (ImageNet weights), headless, global-average-pooled -> 1280 dimensions
  context: the student's subject text embedded like any other text -> cosine similarity S

Training (training/extract_features.py) and serving (classify_service.py) both import this file,
so the two can never drift apart. Heavy libraries are imported lazily.

Needs: torch, torchvision, sentence-transformers>=5.1, pillow, numpy
       and a Hugging Face login because google/embeddinggemma-300m is gated:  hf auth login
"""
import io
import numpy as np

TEXT_MODEL_ID = "google/embeddinggemma-300m"
TEXT_PROMPT = "task: classification | query: "
TEXT_DIM = 256            # MRL truncation (thesis: 256-dimensional semantic vectors)
MAX_SEQ_LENGTH = 128
IMAGE_DIM = 1280          # MobileNetV2 feature size
IMAGE_SIZE = 224
# Used when nothing is selected in the popup, and by the training data when a row has no context.
DEFAULT_CONTEXT = "computer science and information technology: programming, algorithms, databases, networks, software engineering, computer systems"


def l2_normalize(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    return v / (np.linalg.norm(v) + 1e-12)


class FeatureExtractor:
    def __init__(self):
        import torch
        from PIL import Image
        from sentence_transformers import SentenceTransformer
        from torchvision import models, transforms

        self._torch, self._Image = torch, Image
        self.text_model = SentenceTransformer(TEXT_MODEL_ID, truncate_dim=TEXT_DIM)
        self.text_model.max_seq_length = MAX_SEQ_LENGTH
        net = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT).eval()
        self.cnn = net.features
        # torchvision's pretrained weights expect ImageNet mean/std. (The thesis text says pixel values
        # are scaled to [-1, 1], which is the Keras convention. Use whichever matches the weights you load.)
        self.prep = transforms.Compose([
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE), interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    def embed_text(self, text):
        v = self.text_model.encode(text, prompt=TEXT_PROMPT, normalize_embeddings=False)
        return l2_normalize(v[:TEXT_DIM])            # re-normalize after the MRL cut

    def embed_texts(self, texts, batch_size=64):
        """Batched version for training-set extraction (much faster than one call per item). Returns (n, 256)."""
        v = self.text_model.encode(list(texts), prompt=TEXT_PROMPT, normalize_embeddings=False, batch_size=batch_size, show_progress_bar=True)
        v = np.asarray(v, dtype=np.float64)[:, :TEXT_DIM]
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)

    def embed_image(self, data: bytes):
        img = self._Image.open(io.BytesIO(data)).convert("RGB")
        with self._torch.no_grad():
            fmap = self.cnn(self.prep(img).unsqueeze(0))          # (1, 1280, 7, 7)
            v = fmap.mean(dim=(2, 3))[0].cpu().numpy()            # global average pool -> (1280,)
        return np.asarray(v, dtype=np.float64)
