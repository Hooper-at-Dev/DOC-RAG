import json
import os
import hashlib
import threading
import fitz
import io
import re
import numpy as np
from PIL import Image
from datetime import datetime

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance
    VECTOR_LIBS_AVAILABLE = True
except ImportError:
    VECTOR_LIBS_AVAILABLE = False

class PDFChunker:
    def __init__(
        self, 
        registry_path="document_registry.json", 
        chunk_size=1000, 
        overlap_pct=0.30,
        use_gpu_ocr=True,
        ocr_languages=['en'],
        embedding_model_name="BAAI/bge-small-en-v1.5",  
        qdrant_path="./qdrant_db"
    ):
        self.registry_path = registry_path
        self.chunk_size = chunk_size
        self.overlap_pct = overlap_pct
        self.overlap_size = int(chunk_size * overlap_pct)
        self.step_size = self.chunk_size - self.overlap_size
        
        self._lock = threading.RLock()

        if self.step_size <= 0:
            raise ValueError("Overlap percentage cannot be 100% or greater (step size must be > 0).")

        self.use_gpu_ocr = use_gpu_ocr
        self.ocr_reader = None
        if self.use_gpu_ocr:
            if not EASYOCR_AVAILABLE:
                print("[WARNING] EasyOCR package not found. Falling back to native text only.")
                self.use_gpu_ocr = False
            else:
                print(f"[OCR ENGINE] Initializing EasyOCR on GPU (Languages: {ocr_languages})...")
                self.ocr_reader = easyocr.Reader(ocr_languages, gpu=True)

        self.embedding_model_name = embedding_model_name
        self.qdrant_path = qdrant_path
        self.collection_name = "pdf_rag_collection"
        
        if VECTOR_LIBS_AVAILABLE:
            print(f"[EMBEDDING] Loading PyTorch embedding model: {self.embedding_model_name}...")
            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            self.qdrant_client = QdrantClient(path=self.qdrant_path)
            self._ensure_qdrant_collection()
        else:
            print("[WARNING] sentence-transformers or qdrant-client not found. Embedding disabled.")
            self.embedding_model = None
            self.qdrant_client = None

    def _ensure_qdrant_collection(self):
        if not self.qdrant_client:
            return
            
        vector_size = self.embedding_model.get_sentence_embedding_dimension()
        
        if not self.qdrant_client.collection_exists(self.collection_name):
            print(f"[VECTOR DB] Creating new Qdrant collection '{self.collection_name}' with dimension {vector_size}...")
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )

    def _load_registry(self):
        with self._lock:
            if os.path.exists(self.registry_path):
                with open(self.registry_path, 'r') as f:
                    try:
                        return json.load(f)
                    except json.JSONDecodeError:
                        return {}
            return {}

    def _update_registry_entry(self, file_hash, total_pages=None, chunk_count=None, ocr_pages=None, status=None):
        with self._lock:
            registry = self._load_registry()
            if file_hash in registry:
                if total_pages is not None:
                    registry[file_hash]["total_pages"] = total_pages
                if chunk_count is not None:
                    registry[file_hash]["chunk_count"] = chunk_count
                if ocr_pages is not None:
                    registry[file_hash]["ocr_pages"] = ocr_pages
                if status is not None:
                    registry[file_hash]["status"] = status
                    
                registry[file_hash]["updated_at"] = datetime.now().isoformat()
                
                with open(self.registry_path, 'w') as f:
                    json.dump(registry, f, indent=4)

    def _ocr_image_bytes(self, image_bytes):
        if not self.use_gpu_ocr or not self.ocr_reader:
            return ""
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            img_np = np.array(image)
            text_results = self.ocr_reader.readtext(img_np, detail=0)
            return " ".join(text_results).strip()
        except Exception as e:
            print(f"[OCR ERROR] Failed to process image block: {e}")
            return ""

    def _ocr_scanned_page(self, page):
        if not self.use_gpu_ocr or not self.ocr_reader:
            return ""
        try:
            pix = page.get_pixmap(dpi=200)
            image_bytes = pix.tobytes("png")
            return self._ocr_image_bytes(image_bytes)
        except Exception as e:
            print(f"[OCR ERROR] Failed to OCR scanned page {page.number + 1}: {e}")
            return ""

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'[_]{3,}', ' ', text)
        text = re.sub(r'[-]{3,}', ' ', text)
        text = text.replace('\\"', '"').replace('\"', '"')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def extract_text_with_page_map(self, pdf_path):
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        full_text = ""
        page_offsets = []
        ocr_pages = set() 

        for page_num in range(1, total_pages + 1):
            page = doc.load_page(page_num - 1)
            page_text_blocks = []
            
            page_dict = page.get_text("dict")
            blocks = page_dict.get("blocks", [])

            for block in blocks:
                block_type = block.get("type")

                if block_type == 0:
                    lines_text = []
                    for line in block.get("lines", []):
                        span_text = "".join([span.get("text", "") for span in line.get("spans", [])])
                        if span_text.strip():
                            lines_text.append(span_text)
                    if lines_text:
                        page_text_blocks.append(" ".join(lines_text))

                elif block_type == 1 and self.use_gpu_ocr:
                    image_bytes = block.get("image")
                    if image_bytes:
                        ocr_text = self._ocr_image_bytes(image_bytes)
                        if ocr_text:
                            ocr_pages.add(page_num) 
                            page_text_blocks.append(f"[Image Content: {ocr_text}]")

            page_text = " ".join(page_text_blocks).strip()

            if not page_text and self.use_gpu_ocr:
                print(f"[OCR] Page {page_num} appears to be a scanned page. Running full-page OCR...")
                ocr_page_text = self._ocr_scanned_page(page)
                if ocr_page_text:
                    ocr_pages.add(page_num) 
                    page_text = f"[Scanned Page Content: {ocr_page_text}]"

            page_text = self._clean_text(page_text) + " "
            
            start_offset = len(full_text)
            full_text += page_text
            end_offset = len(full_text)

            page_offsets.append({
                "page": page_num,
                "start_idx": start_offset,
                "end_idx": end_offset
            })

        doc.close()
        return full_text, page_offsets, total_pages, sorted(list(ocr_pages))

    def _map_chunk_to_pages(self, chunk_start, chunk_end, page_offsets):
        matching_pages = []
        for p in page_offsets:
            if not (p["end_idx"] <= chunk_start or p["start_idx"] >= chunk_end):
                matching_pages.append(p["page"])
        return matching_pages

    def chunk_pdf(self, pdf_path, file_hash=None):
        filename = os.path.basename(pdf_path)
        print(f"\n[CHUNKING] Starting processing for '{filename}'...")
        
        full_text, page_offsets, total_pages, ocr_pages = self.extract_text_with_page_map(pdf_path)

        if not full_text.strip():
            print(f"[WARNING] No text extracted from '{filename}'. Document may be empty or unreadable.")
            return []

        chunks = []
        text_length = len(full_text)
        start_idx = 0
        chunk_counter = 0

        while start_idx < text_length:
            end_idx = min(start_idx + self.chunk_size, text_length)
            chunk_text = full_text[start_idx:end_idx].strip()

            if chunk_text:
                pages = self._map_chunk_to_pages(start_idx, end_idx, page_offsets)
                
                chunk_data = {
                    "chunk_id": f"{file_hash[:8] if file_hash else 'doc'}_chunk_{chunk_counter}",
                    "file_hash": file_hash,
                    "filename": filename,
                    "text": chunk_text,
                    "metadata": {
                        "filename": filename,
                        "pages": pages,
                        "start_char": start_idx,
                        "end_char": end_idx
                    }
                }
                chunks.append(chunk_data)
                chunk_counter += 1

            if end_idx == text_length:
                break

            start_idx += self.step_size

        print(f"[CHUNKING] Complete: Created {len(chunks)} chunks across {total_pages} pages (OCR on pages: {ocr_pages}).")

        if file_hash:
            self._update_registry_entry(
                file_hash=file_hash,
                total_pages=total_pages,
                chunk_count=len(chunks),
                ocr_pages=ocr_pages
            )

        return chunks

    def embed_and_store(self, chunks):
        if not chunks:
            print("[INFO] No chunks provided for embedding.")
            return
            
        if not self.embedding_model or not self.qdrant_client:
            print("[ERROR] Embedding environment not set up. Check dependencies.")
            return

        file_hash = chunks[0]["file_hash"]
        filename = chunks[0]["filename"]
        
        print(f"[EMBEDDING] Generating PyTorch embeddings for {len(chunks)} chunks from '{filename}'...")
        
        texts = [chunk["text"] for chunk in chunks]
        
        embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
        
        print(f"[VECTOR DB] Pushing {len(chunks)} vectors to Qdrant...")
        
        points = []
        for i, chunk in enumerate(chunks):
            qdrant_id = int(hashlib.md5(chunk["chunk_id"].encode()).hexdigest(), 16) % (10 ** 15)
            
            points.append(PointStruct(
                id=qdrant_id,
                vector=embeddings[i].tolist(),
                payload={
                    "text": chunk["text"],
                    "filename": chunk["filename"],
                    "pages": chunk["metadata"]["pages"],
                    "file_hash": chunk["file_hash"],
                    "original_chunk_id": chunk["chunk_id"]
                }
            ))
            
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        
        print(f"[SUCCESS] '{filename}' chunks fully embedded and stored.")
        
        if file_hash:
            self._update_registry_entry(file_hash, status="completed")


    def process_pending_pdfs(self, pdf_folder="./"):
        registry = self._load_registry()
        pending_files = {
            hash_val: data for hash_val, data in registry.items()
            if data.get("status") == "pending_embedding"
        }

        if not pending_files:
            print("[INFO] No pending PDFs found in registry waiting to be chunked.")
            return

        print(f"Found {len(pending_files)} pending PDF(s) to process.")

        for file_hash, data in pending_files.items():
            filename = data["filename"]
            pdf_path = os.path.join(pdf_folder, filename)

            if not os.path.exists(pdf_path):
                print(f"[ERROR] PDF file '{filename}' not found at '{pdf_path}'. Skipping.")
                continue
            
            chunks = self.chunk_pdf(pdf_path, file_hash=file_hash)
            
            if chunks:
                self.embed_and_store(chunks)

    def close(self):
        if hasattr(self, 'qdrant_client') and self.qdrant_client is not None:
            self.qdrant_client.close()
            print("[CHUNKER] Database connection closed and lock released.")