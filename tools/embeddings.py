import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoProcessor, AutoModel, AutoTokenizer
from PIL import Image
from sklearn.preprocessing import normalize
from config import BaseConfig
from config import get_global_config
from langchain_core.tools import tool
from typing import Optional

base_cfg = get_global_config()
device = "cuda" if torch.cuda.is_available() else "cpu"

# Initialize models only once
text_model = None
image_model = None
image_processor = None
image_tokenizer = None

def get_text_model():
    global text_model
    if text_model is None:
        text_model = SentenceTransformer(base_cfg.embed_text_model_name)
        text_model.to(device)
    return text_model

def get_image_model():
    global image_model, image_processor, image_tokenizer
    if image_model is None:
        image_processor = AutoProcessor.from_pretrained(base_cfg.embed_image_model_name)
        image_tokenizer = AutoTokenizer.from_pretrained(base_cfg.embed_image_model_name)
        image_model = AutoModel.from_pretrained(base_cfg.embed_image_model_name).to(device).eval()
    return image_model, image_processor, image_tokenizer


def text2vector(text: str) -> np.ndarray:
    """
    Convert text content to a vector using the sentence transformer model.
    500 characters of text is embedded which should be enough for the agent to decide relevance.
    """
    model = get_text_model()
    snippet = text[:500]
    vec = model.encode(
        snippet,
        normalize_embeddings=True,
        max_length=512,  # safely below common model limits
        show_progress_bar=False,
    )
    return vec.astype(np.float32)

EDGE_MAX      = 150      # px ─ covers 16·24·32·48·128 icon tiers  :contentReference[oaicite:0]{index=0}
ASPECT_TOLER  = 4        # px  ─ allow slight padding
COLORS_MAX    = 256      # typical indexed-PNG palette limit       :contentReference[oaicite:1]{index=1}

def is_icon(img: Image.Image, file_bytes: Optional[int] = None) -> bool:
    """
    Heuristically decide whether `img` is a UI icon.
    Optionally pass `file_bytes` (len(open(path,'rb').read())) to add a 10 kB test.
    """
    w, h = img.size
    # 1) too big  →  definitely NOT an icon
    if max(w, h) > EDGE_MAX:
        return False
    # 2) flat-palette test
    try:
        # returns None if > maxcolors unique colours
        colours = img.convert("RGBA").getcolors(maxcolors=256*256)
        if colours is None or len(colours) > COLORS_MAX:
            return False
    except Exception:
        # corrupted or huge palette → treat as photo
        return False
    # 4) optional file-size guard (icons ≤10 kB on average)     
    if file_bytes is not None and file_bytes > 10_000:
        return False
    return True

def image2vector(image_path: str, filter_icons: bool = True) -> np.ndarray:
    """
    Convert an image to a vector using the image model.
    """
    model, processor, _ = get_image_model()
    try:
        img = Image.open(image_path).convert("RGB")
        if filter_icons and is_icon(img):
            return None
        with torch.no_grad():
            inputs = processor(images=img, return_tensors="pt").to(device)
            vec = model.get_image_features(**inputs)
        return normalize(vec.cpu().numpy().astype(np.float32))[0]
    except Exception as e:
        return None
   

def get_embedding_dimensions():
    """
    Return the dimensions of the text and image embeddings.
    """
    text_model = get_text_model()
    text_dim = text_model.get_sentence_embedding_dimension()
    
    model, processor, _ = get_image_model()
    with torch.no_grad():
        dummy_image = Image.new("RGB", (512, 512))
        inputs = processor(images=dummy_image, return_tensors="pt").to(device)
        image_features = model.get_image_features(**inputs)
        image_dim = image_features.shape[-1]
    
    return text_dim, image_dim 

def query2vector(query: str) -> np.ndarray:
    """
    Convert a query to a vector using the CLIP model's text processing capabilities.
    This ensures the vector dimensions match those expected by the Milvus image collection.
    """
    model, _, tokenizer = get_image_model()
    with torch.no_grad():
        # Process the text input using the CLIP text encoder
        inputs = tokenizer([query], padding=True, return_tensors="pt").to(device)
        vec = model.get_text_features(**inputs)
    return normalize(vec.cpu().numpy().astype(np.float32))[0]

