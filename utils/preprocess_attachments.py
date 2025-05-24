import os
# Silence the HuggingFace "process just got forked" warning
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from pymilvus import connections, DataType
from pymilvus import MilvusClient
import numpy as np
from pathlib import Path
from tqdm import tqdm
from config import BaseConfig
from config import get_global_config

from utils.get_attachments_metadata import get_all_metadata
from tools.embeddings import image2vector, text2vector, get_embedding_dimensions

base_cfg = get_global_config()

def create_collection(client, name: str, dim: int, logger=None):
    """Create a Milvus collection if it doesn't exist"""
    if logger:
        logger.info("Creating collection %s", name)
    client.create_collection(
        collection_name=name,
        dimension=dim,
        vector_field_name="vector",
        metric_type="COSINE",
        auto_id=True,
        enable_dynamic_field=True,
    )

def preprocess_data_to_milvus(logger=None):
    CONNECTION_URI = base_cfg.milvus_uri
    client = MilvusClient(uri=CONNECTION_URI)
    IMAGE_COLL = f"{base_cfg.case_name}__attachments_image"
    TEXT_COLL  = f"{base_cfg.case_name}__attachments_text"

    # Check if both collections already exist
    if client.has_collection(IMAGE_COLL) and client.has_collection(TEXT_COLL):
        logger.info("Both collections already exist, skipping data processing")
        return
    
    # Get embedding dimensions
    DIM_TEXT, DIM_IMAGE = get_embedding_dimensions()

    # Create collections if they don't exist
    create_collection(client, IMAGE_COLL, DIM_IMAGE, logger)
    create_collection(client, TEXT_COLL, DIM_TEXT, logger)

    # ---------------- Bulk ingest ----------------
    DATA_ROOT = Path(base_cfg.get_path("attached_artifact_dir"))
    BATCH_SIZE = 100

    img_batch = {"vector": [], "path": []}
    txt_batch = {"vector": [], "path": [], "content": []}

    def flush_img():
        if not img_batch["vector"]:
            return

        rows = [
            {"vector": v, "path": p, "modality": "image", "content": "", "metadata": get_all_metadata(p)}
            for v, p in zip(img_batch["vector"], img_batch["path"])
        ]
        client.insert(IMAGE_COLL, rows)
        for k in img_batch:
            img_batch[k].clear()

    def flush_txt():
        if not txt_batch["vector"]:
            return

        rows = [
            {"vector": v, "path": p, "modality": "text", "content": c, "metadata": get_all_metadata(p)}
            for v, p, c in zip(txt_batch["vector"], txt_batch["path"], txt_batch["content"])
        ]
        client.insert(TEXT_COLL, rows)
        for k in txt_batch:
            txt_batch[k].clear()

    def process_file(p: Path):
        try:
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                vec = image2vector(str(p), filter_icons=True)
                if vec is not None:
                    img_batch["vector"].append(vec.astype(np.float32).tolist())
                    img_batch["path"].append(str(p))
            elif p.suffix.lower() in {".txt", ".md"}:
                full_text = p.read_text(encoding="utf-8", errors="ignore")
                snippet = full_text[:500]
                vec = text2vector(snippet)
                txt_batch["vector"].append(vec.astype(np.float32).tolist())
                txt_batch["path"].append(str(p))
                txt_batch["content"].append(snippet)
        except Exception as e:
            logger.error(f"Failed to ingest {p}: {e}")

    files = [f for f in DATA_ROOT.rglob("*") if f.is_file()]
    for f in tqdm(files, desc="Embedding & uploading"):
        process_file(f)
        if len(img_batch["vector"]) >= BATCH_SIZE:
            flush_img()
        if len(txt_batch["vector"]) >= BATCH_SIZE:
            flush_txt()

    flush_img()
    flush_txt()

    client.flush(IMAGE_COLL)
    client.flush(TEXT_COLL)

    img_count = int(client.get_collection_stats(IMAGE_COLL)["row_count"])
    txt_count = int(client.get_collection_stats(TEXT_COLL)["row_count"])
    logger.info("Done. Image entities: %d, Text entities: %d", img_count, txt_count)

