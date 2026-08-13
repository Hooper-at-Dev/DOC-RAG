import json
import os
import hashlib
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

class PDFInitiator:
    def __init__(self, registry_path="document_registry.json"):

        self.registry_path = registry_path
        self._lock = threading.Lock() 
        self.registry = self._load_registry()

    def _load_registry(self):
        with self._lock:
            if os.path.exists(self.registry_path):
                with open(self.registry_path, 'r') as file:
                    try:
                        return json.load(file)
                    except json.JSONDecodeError:
                        return {}
            return {}

    def _save_registry(self):
        with open(self.registry_path, 'w') as file:
            json.dump(self.registry, file, indent=4)

    def _generate_file_hash(self, file_path):
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def process_pdf(self, file_path):
        if not os.path.exists(file_path):
            print(f"[ERROR] File '{file_path}' does not exist.")
            return False

        filename = os.path.basename(file_path)
        file_hash = self._generate_file_hash(file_path)

        with self._lock:
            if file_hash in self.registry:
                status = self.registry[file_hash].get("status", "unknown")
                print(f"[SKIP] '{filename}' is already in the DB (Status: {status}).")
                return True

            file_size_bytes = os.path.getsize(file_path)
            
            self.registry[file_hash] = {
                "filename": filename,
                "file_size_bytes": file_size_bytes,
                "status": "pending_embedding",
                "added_at": datetime.now().isoformat(),
                "total_pages": None,  
                "chunk_count": 0      
            }
            
            self._save_registry()
            print(f"[REGISTERED] '{filename}' successfully queued for pipeline.")
            
        return True

    def process_folder(self, folder_path, max_workers=None):
        if not os.path.isdir(folder_path):
            print(f"[ERROR] Folder '{folder_path}' does not exist.")
            return

        pdf_files = [
            os.path.join(folder_path, f) for f in os.listdir(folder_path)
            if f.lower().endswith('.pdf')
        ]

        if not pdf_files:
            print(f"No PDF files found in '{folder_path}'.")
            return

        print(f"\n--- Batch Processing Started: Found {len(pdf_files)} PDFs ---")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pdf = {executor.submit(self.process_pdf, pdf): pdf for pdf in pdf_files}
            
            success_count = 0
            for future in as_completed(future_to_pdf):
                pdf = future_to_pdf[future]
                try:
                    if future.result():
                        success_count += 1
                except Exception as e:
                    print(f"[ERROR] Processing {os.path.basename(pdf)} generated an exception: {e}")

        elapsed = round(time.time() - start_time, 2)
        print(f"--- Batch Processing Complete: {success_count}/{len(pdf_files)} successful in {elapsed} seconds ---")
