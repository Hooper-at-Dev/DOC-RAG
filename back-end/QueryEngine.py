from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

class QueryEngine:
    def __init__(
        self, 
        embedding_model_name="BAAI/bge-small-en-v1.5", 
        qdrant_path="./qdrant_db",
        collection_name="pdf_rag_collection"
    ):
        print(f"[QUERY ENGINE] Loading embedding model: {embedding_model_name}...")
        self.embedding_model = SentenceTransformer(embedding_model_name)
        
        print(f"[QUERY ENGINE] Connecting to local Qdrant database at '{qdrant_path}'...")
        self.qdrant_client = QdrantClient(path=qdrant_path)
        self.collection_name = collection_name

    def search(self, user_query, top_k=10, file_filter=None):
        print(f"\n[SEARCH] Vectorizing query: '{user_query}'...")
        query_vector = self.embedding_model.encode(user_query).tolist()

        search_filter = None
        if file_filter:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="filename",
                        match=MatchValue(value=file_filter)
                    )
                ]
            )

        search_response = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=search_filter,
            with_payload=True 
        )
        
        search_results = search_response.points

        formatted_results = []
        for result in search_results:
            payload = result.payload
            formatted_results.append({
                "score": result.score,
                "text": payload.get("text", ""),
                "filename": payload.get("filename", "Unknown"),
                "pages": payload.get("pages", []),
                "chunk_id": payload.get("original_chunk_id", "Unknown")
            })

        return formatted_results

    def close(self):
        if hasattr(self, 'qdrant_client') and self.qdrant_client is not None:
            self.qdrant_client.close()
            print("[QUERY ENGINE] Database connection closed and lock released.")
