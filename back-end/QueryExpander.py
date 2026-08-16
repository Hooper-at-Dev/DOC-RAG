import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

class QueryExpander:
    def __init__(self, model_name="gemini-2.5-flash", env_path=".env"):
        load_dotenv(dotenv_path=env_path)
        self.model_name = model_name
        
        if not os.getenv("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY not found. Ensure it is defined in your .env file.")
            
        self.client = genai.Client()

    def expand_query(self, user_query: str) -> list[str]:
        """
        Decomposes complex user questions into multiple targeted search queries 
        to ensure all relevant policy documents (e.g., overrides, schedules) are retrieved.
        """
        system_instruction = (
            "You are an expert search query optimizer for a corporate policy retrieval system. "
            "Your task is to take a user's question and generate 2 to 3 distinct, highly targeted "
            "search queries that will help find all necessary information across multiple policy documents.\n\n"
            "GUIDELINES:\n"
            "1. Decompose multi-hop or comparative questions into individual targeted queries.\n"
            "2. If specific policies, schedule numbers (e.g., NFS-POL-011, NFS-POL-003, NFS-SUB-001), or entities "
            "(e.g., Northwind Capital Markets, Records Retention Schedule) are mentioned or implied, generate search terms targeting those specific documents/schedules.\n"
            "3. Output MUST be a raw JSON array of strings containing only the search queries.\n"
            "Example Output: [\"search query 1\", \"search query 2\", \"search query 3\"]"
        )
        
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            response_mime_type="application/json"
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"User Question: {user_query}",
                config=config
            )
            
            queries = json.loads(response.text)
            if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                # Ensure the original user query is included as the primary search
                if user_query not in queries:
                    queries.insert(0, user_query)
                return queries
        except Exception as e:
            print(f"[QUERY EXPANDER ERROR] Failed to expand query: {e}")
            
        # Fallback to the original query if expansion fails or returns invalid JSON
        return [user_query]