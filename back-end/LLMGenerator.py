import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

class LLMGenerator:
    def __init__(self, model_name="gemini-2.5-flash", env_path=".env"):

        load_dotenv(dotenv_path=env_path)
        
        self.model_name = model_name
        
        if not os.getenv("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY not found. Ensure it is defined in your .env file.")
            
        self.client = genai.Client()

    def build_context_string(self, retrieved_chunks):
        if not retrieved_chunks:
            return "No context found."
            
        context_text = ""
        for i, chunk in enumerate(retrieved_chunks, 1):
            context_text += f"\n--- Context Block {i} ---\n"
            context_text += f"Source: {chunk['filename']} | Pages: {chunk['pages']} | Score: {chunk.get('score', 'N/A')}\n"
            context_text += f"Text:\n{chunk['text']}\n"
        
        return context_text

    def generate_answer(self, user_query, retrieved_chunks):
        context_text = self.build_context_string(retrieved_chunks)
        
        system_instruction = (
            "You are an expert, truthful AI assistant. Your task is to answer the user's question "
            "ONLY using the provided Context Blocks. Do not use outside knowledge. "
            "If the answer cannot be found in the context, say exactly: 'I cannot find the answer in the provided documents.'\n\n"
            "CITATION RULES:\n"
            "1. You must include inline citations in your text (e.g., [filename.pdf, p. 4, Score: 0.85]).\n"
            "2. At the very end of your response, you MUST provide a 'Sources' list containing the exact filenames, page numbers, and Retrieval Scores used."
        )
        
        prompt = f"Question: {user_query}\n\nProvided Context:\n{context_text}"
        
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3, 
        )
                
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            
            return json.dumps({
                "answer": response.text,
                "metadata": {
                    "api_logprobs": getattr(response, "logprobs", None),
                    "retrieval_metrics": [
                        {
                            "chunk_file": chunk["filename"],
                            "retrieval_score": chunk.get("score")
                        } for chunk in retrieved_chunks
                    ]
                }
            })
        except Exception as e:
            return json.dumps({"error": f"[ERROR] Failed to generate response from Gemini: {e}"})
