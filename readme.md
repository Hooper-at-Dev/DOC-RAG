# Compliance Copilot

Compliance Copilot is a lightweight, full-stack AI tool designed to answer questions about organizational policy and regulatory documents. It uses a Retrieval-Augmented Generation (RAG) architecture to ensure that every answer is grounded in actual source material, providing transparent inline citations, a confidence score, and strict refusal capabilities when the answer is not found in the documents.

## 🚀 Features

*   **Intelligent RAG Pipeline**: Ingests PDFs, chunks them with intelligent overlap, and extracts text using PyMuPDF. It falls back to GPU-accelerated OCR (EasyOCR) for scanned images.
*   **Vector Search & Query Expansion**: Uses the `BAAI/bge-small-en-v1.5` embedding model and Qdrant vector database. Complex queries are broken down into sub-queries using a Query Expander to ensure high retrieval accuracy.
*   **Grounded Generation & Refusals**: Powered by Gemini 2.5 Flash, the LLM is strictly prompted to only use provided context and output structured JSON. If the answer isn't in the context, it refuses to answer, dropping the confidence score to zero.
*   **Evidence Panel & Citations**: The React frontend features an intuitive "Evidence" sidebar showing confidence scores, citation accuracy metrics, and exact source chunks so users can verify the model's claims.
*   **Admin Dashboard**: A built-in dashboard to drag-and-drop new PDF policies, view the document registry, and trigger asynchronous indexing pipelines.

## 🛠️ Tech Stack

*   **Frontend**: React / Next.js, Tailwind CSS, Lucide Icons.
*   **Backend**: Python, FastAPI.
*   **AI/ML**: Google Gemini API (Generation & Query Expansion), SentenceTransformers (Embeddings), Cross-Encoder (Reranking).
*   **Database/Storage**: Local Qdrant (Vector Store), Local JSON files (History & Registry).

---

## ⚖️ Trade-offs & What Was Left Out

To respect the 5-6 hour time constraint while delivering a robust AI product, a few intentional scoping decisions were made:

1.  **Postgres / pgvector was swapped for Local JSON + Qdrant**
    *   *What was omitted*: A Postgres database for storing documents, chunks, and history.
    *   *Reason*: Setting up a Postgres container with the `pgvector` extension adds friction to the "one-command setup" requirement. Instead, I used `chat_history.json`, `document_registry.json`, and a local file-based Qdrant vector database. This achieves the exact same architectural goals but allows the app to run instantly on any machine without Docker dependencies.
2.  **Separate Offline Evaluation Script**
    *   *What was omitted*: A standalone python script to run a batch of 10 test questions and output a report.
    *   *Reason*: Instead of an offline script, I built **real-time evaluation metrics** directly into the API and UI. Every single query calculates its own "Retrieval Confidence Score" (based on top chunk distance thresholds) and "Citation Accuracy Score" (verifying if the LLM's citations actually match the retrieved chunks). This provides continuous, visible evaluation on every prompt. 
3.  **Authentication & User Roles**
    *   *What was omitted*: Real auth (OAuth/JWT). 
    *   *Reason*: The UI mocks a user workspace ("Trust & Safety workspace") to demonstrate what a production UI would look like, but implementing actual auth was cut to focus purely on the core AI retrieval mechanics.

---

## ⚙️ How to Run the Code (Step-by-Step)

### Prerequisites
*   Python 3.9+
*   Node.js 18+
*   A Google Gemini API Key

### 1. Setup the Backend (FastAPI)

1. Open your terminal and navigate to the backend directory (or the root if combined).
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
