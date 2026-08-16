import os
import json
import time
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import uuid
import re
from QueryEngine import QueryEngine
from LLMGenerator import LLMGenerator
from PDFInitiator import PDFInitiator
from PDFChunker import PDFChunker

UPLOAD_DIR = "./uploads"
HISTORY_FILE = "chat_history.json"

engine = None
llm = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, llm
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            json.dump([], f)
            
    print("[SYSTEM] Loading Models into memory. This happens only once...")
    engine = QueryEngine()
    llm = LLMGenerator()
    print("[SYSTEM] Models loaded successfully. API is ready.")
    
    yield
    
    if engine:
        engine.close()
    print("[SYSTEM] Shutting down.")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str

def save_to_history(user_query: str, response_data: dict):
    """Saves the isolated query and its full response payload."""
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    except Exception:
        history = []
        
    history.insert(0, {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "query": user_query,
        "response": response_data
    })
    
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

@app.post("/api/chat")
def handle_chat(request: ChatRequest):
    user_query = request.query
    
    top_chunks = engine.search(user_query, top_k=5)
    
    raw_llm_json_str = llm.generate_answer(user_query, top_chunks)
    
    try:
        llm_response = json.loads(raw_llm_json_str)
        generated_text = llm_response.get("answer", "No answer found.")
    except json.JSONDecodeError:
        generated_text = raw_llm_json_str

    formatted_sources = []
    for i, chunk in enumerate(top_chunks):
        formatted_sources.append({
            "id": f"{(i+1):02d}",
            "title": chunk.get("filename", "Unknown Document"),
            "type": "Chunk",
            "updated": f"Score: {chunk.get('score', 0):.2f}",
            "excerpt": chunk.get("text", "")[:300] + "...", 
            "score": chunk.get("score", 0)
        })

    if top_chunks:
        top_1_score = top_chunks[0].get("score", 0)
        avg_top_3 = sum(c.get("score", 0) for c in top_chunks[:3]) / min(len(top_chunks), 3)
        
        raw_score = (top_1_score * 0.7) + (avg_top_3 * 0.3)
        
        min_thresh, max_thresh = 0.40, 0.55
        if raw_score <= min_thresh:
            confidence_percentage = 0
        else:
            scaled_score = (raw_score - min_thresh) / (max_thresh - min_thresh)
            confidence_percentage = min(max(scaled_score * 100, 0), 100)
    else:
        confidence_percentage = 0

    if confidence_percentage >= 75:
        confidence_class = "High confidence"
        confidence_msg = "Answer is directly supported by your organization's source material."
    elif confidence_percentage >= 40:
        confidence_class = "Moderate confidence"
        confidence_msg = "Answer is partially supported by context. Verify details."
    else:
        confidence_class = "Under confident"
        confidence_msg = "Answer lacks strong support from the knowledge base and may be unreliable."

    not_found_phrase = "I cannot find the answer in the provided documents"
    if not_found_phrase.lower() in generated_text.lower():
        confidence_percentage = 0
        confidence_class = "Zero confidence"
        confidence_msg = "The knowledge base does not contain information to answer this query."
        formatted_sources = []

    citations = re.findall(r'\[([^\[\]]+?),\s*p\.\s*(\d+),\s*Score:\s*([\d.]+)\]', generated_text)
    
    if citations:
        valid_citations = 0
        for filename, page_str, score_str in citations:
            filename = filename.strip()
            try:
                page = int(page_str.strip())
            except ValueError:
                continue
            
            is_valid = False
            for chunk in top_chunks:
                if chunk.get("filename") == filename and page in chunk.get("pages", []):
                    is_valid = True
                    break
            
            if is_valid:
                valid_citations += 1
                
        citation_accuracy = int((valid_citations / len(citations)) * 100)
    else:
        citation_accuracy = 0

    response_payload = {
        "question": user_query,
        "summary": generated_text,
        "detail": "", 
        "confidence": {
            "score": int(confidence_percentage),
            "classification": confidence_class,
            "message": confidence_msg
        },
        "citation_accuracy": citation_accuracy,
        "sources": formatted_sources
    }

    save_to_history(user_query, response_payload)

    return response_payload

@app.get("/api/dashboard")
def get_dashboard_data():
    registry_data = {}
    if os.path.exists("document_registry.json"):
        with open("document_registry.json", "r") as f:
            try:
                registry_data = json.load(f)
            except json.JSONDecodeError:
                pass
                
    documents = []
    latest_time = None
    
    for file_hash, data in registry_data.items():
        doc_date_str = data.get("added_at")
        doc_size_kb = data.get("file_size_bytes", 0) // 1024
        
        if doc_date_str:
            doc_date = datetime.fromisoformat(doc_date_str)
            if not latest_time or doc_date > latest_time:
                latest_time = doc_date
                
        documents.append({
            "name": data.get("filename", "Unknown"),
            "size": f"{doc_size_kb} KB",
            "status": data.get("status", "Unknown"),
            "date": doc_date_str.split("T")[0] if doc_date_str else "Unknown"
        })
        
    last_indexed_str = "N/A"
    if latest_time:
        diff_minutes = int((datetime.now() - latest_time).total_seconds() / 60)
        last_indexed_str = f"{diff_minutes}m ago" if diff_minutes < 60 else f"{diff_minutes // 60}h ago"

    return {
        "stats": {
            "documents_indexed": len(documents),
            "last_indexed": last_indexed_str
        },
        "documents": documents
    }

@app.post("/api/upload")
async def upload_documents(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)):
    for file in files:
        file_location = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_location, "wb+") as file_object:
            file_object.write(await file.read())
            
    background_tasks.add_task(process_upload_folder)
    return {"message": f"{len(files)} file(s) queued for indexing."}

@app.get("/api/history")
def get_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def process_upload_folder():
    global engine
    print(f"[BACKGROUND TASK] Starting pipeline for {UPLOAD_DIR}")
    
    if engine:
        engine.close()

    try:
        initiator = PDFInitiator()
        initiator.process_folder(UPLOAD_DIR)
        
        chunker = PDFChunker()
        chunker.process_pending_pdfs(pdf_folder=UPLOAD_DIR)
        chunker.close() 
    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] Pipeline failed: {e}")
    finally:
        print("[BACKGROUND TASK] Reconnecting Chat Engine...")
        engine = QueryEngine()
        print("[BACKGROUND TASK] Pipeline complete.")

if __name__ == "__main__":
    import uvicorn
    os.environ["TOKENIZERS_PARALLELISM"] = "false" 
    uvicorn.run(app, host="0.0.0.0", port=8000)