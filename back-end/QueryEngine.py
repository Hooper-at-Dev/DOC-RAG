from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from QueryExpander import QueryExpander

class QueryEngine:
    def __init__(
        self, 
        embedding_model_name="BAAI/bge-small-en-v1.5", 
        qdrant_path="./qdrant_db",
        collection_name="pdf_rag_collection",
        use_query_expansion=True
    ):
        print(f"[QUERY ENGINE] Loading embedding model: {embedding_model_name}...")
        self.embedding_model = SentenceTransformer(embedding_model_name)
        
        print(f"[QUERY ENGINE] Connecting to local Qdrant database at '{qdrant_path}'...")
        self.qdrant_client = QdrantClient(path=qdrant_path)
        self.collection_name = collection_name
        
        self.use_query_expansion = use_query_expansion
        if self.use_query_expansion:
            print("[QUERY ENGINE] Initializing Query Expander...")
            self.expander = QueryExpander()

    def search(self, user_query, top_k=10, initial_k=20, file_filter=None):
        search_queries = [user_query]
        
        if self.use_query_expansion:
            print(f"\n[QUERY EXPANSION] Generating sub-queries for: '{user_query}'...")
            search_queries = self.expander.expand_query(user_query)
            print(f"[QUERY EXPANSION] Sub-queries generated: {search_queries}")

        search_filter = None
        if file_filter:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            search_filter = Filter(
                must=[FieldCondition(key="filename", match=MatchValue(value=file_filter))]
            )

        # We will store the results of each sub-query in a list of lists
        all_query_results = []

        for q in search_queries:
            query_vector = self.embedding_model.encode(q).tolist()
            search_response = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=initial_k,
                query_filter=search_filter,
                with_payload=True 
            )
            
            # Format the points for this specific sub-query
            current_query_chunks = []
            for result in search_response.points:
                current_query_chunks.append({
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "filename": result.payload.get("filename", "Unknown"),
                    "pages": result.payload.get("pages", []),
                    "chunk_id": result.payload.get("original_chunk_id", "Unknown")
                })
            
            all_query_results.append(current_query_chunks)

        # Round-Robin Selection to guarantee diversity
        final_results = []
        seen_chunk_ids = set()
        
        # We loop up to initial_k times (the max depth of any single query's results)
        for i in range(initial_k):
            for query_chunks in all_query_results:
                # If this query still has chunks at index i
                if i < len(query_chunks):
                    chunk = query_chunks[i]
                    if chunk["chunk_id"] not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk["chunk_id"])
                        final_results.append(chunk)
                        
                        # Stop exactly when we hit our top_k limit
                        if len(final_results) == top_k:
                            return final_results

        return final_results

    def close(self):
        if hasattr(self, 'qdrant_client') and self.qdrant_client is not None:
            self.qdrant_client.close()
            print("[QUERY ENGINE] Database connection closed and lock released.")

if __name__ == "__main__":
    engine = QueryEngine()
    result = engine.search("The KYC policy states that financial transaction records must be retained for a minimum of 5 years. Is this the exact timeframe I should follow, or does another policy override this?")
    import json
    print(json.dumps(result, indent=2))
    print("-"*20)
