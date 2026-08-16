from sentence_transformers import CrossEncoder

class DocumentReranker:
    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"):
        print(f"[RERANKER] Loading cross-encoder model: {model_name}...")
        self.model = CrossEncoder(model_name, max_length=512)

    def rerank(self, query: str, search_results: list, top_k: int = 5) -> list:
        if not search_results:
            return []
        
        pairs = [[query, doc["text"]] for doc in search_results]
        scores = self.model.predict(pairs)
        
        for i, score in enumerate(scores):
            search_results[i]["cross_encoder_score"] = float(score)
            search_results[i]["score"] = float(score) 

        reranked_results = sorted(
            search_results, 
            key=lambda x: x["cross_encoder_score"], 
            reverse=True
        )
        return reranked_results[:top_k]