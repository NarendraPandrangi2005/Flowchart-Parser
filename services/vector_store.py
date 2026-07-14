import os
import json
import chromadb
import numpy as np

class VectorStoreManager:
    """
    LEARNER TIP:
    This class manages a local, persistent vector database using ChromaDB.
    Vector databases are optimized to index text chunks alongside their 
    mathematical vector representations (embeddings) to enable semantic search queries.
    """
    
    def __init__(self, db_path=None, model_name="all-MiniLM-L6-v2"):
        if db_path is None:
            # Set the database folder path to 'chroma_db' inside the workspace root folder
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")
        self.db_path = db_path
        
        # Initialize a persistent client, saving the SQLite database on local disk
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection_name = "flowchart_troubleshooting"
        self.model_name = model_name
        self._model = None # Private variable for lazy loading

    @property
    def model(self):
        """
        LEARNER TIP:
        Lazy loading pattern. Importing 'sentence_transformers' takes 1-2 seconds
        and consumes large amounts of memory. By loading it inside a property, we only
        incur the import penalty the exact moment we attempt to generate embeddings.
        """
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def get_collection(self):
        """
        LEARNER TIP:
        Gets the existing ChromaDB collection, or creates a new one if it doesn't exist.
        Think of collections as 'tables' in a vector database.
        """
        return self.client.get_or_create_collection(self.collection_name)

    def reset_collection(self):
        """
        LEARNER TIP:
        Deletes the collection (if it exists) and recreates it.
        This is useful to prevent duplicate items when rebuilding the index.
        """
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass # Fail silently if the collection doesn't exist yet
        return self.client.get_or_create_collection(self.collection_name)

    def index_chunks(self, chunks):
        """
        LEARNER TIP:
        1. Encodes list of text chunks into mathematical vectors (embeddings).
        2. Packages them with metadata (document name, page number, decision route).
        3. Saves them into the ChromaDB collection.
        """
        # Recreate the table from scratch
        collection = self.reset_collection()
        if not chunks:
            print("No chunks provided to index.")
            return 0

        print(f"Generating embeddings for {len(chunks)} chunks using {self.model_name}...")
        texts = [c["text"] for c in chunks]
        
        # Calculate embeddings (a list of 384 floats for each text chunk)
        embeddings = self.model.encode(texts, show_progress_bar=True)
        
        ids = []
        documents = []
        metadatas = []
        pre_computed_embeddings = []

        for idx, chunk in enumerate(chunks):
            chunk_id = chunk["chunk_id"]
            
            # ChromaDB metadata can only hold simple strings/numbers.
            # We serialize the decision path list of dicts to a JSON string.
            path_str = json.dumps(chunk["decision_path"])
            
            # Construct metadata fields to enable precise query filtering later
            metadata = {
                "manual_name": chunk.get("manual_name", "sample.pdf"),
                "flowchart_id": str(chunk.get("flowchart_id", "")),
                "paragraph_id": chunk.get("paragraph_id", ""),
                "decision_path": path_str
            }
            
            ids.append(chunk_id)
            documents.append(chunk["text"])
            # Convert NumPy arrays to lists (Chroma requires lists for vectors)
            pre_computed_embeddings.append(embeddings[idx].tolist())
            metadatas.append(metadata)

        # Batch insertion helper: insert records in batches of 500 to stay under memory constraints
        batch_size = 500
        for i in range(0, len(ids), batch_size):
            end_idx = min(i + batch_size, len(ids))
            collection.add(
                ids=ids[i:end_idx],
                documents=documents[i:end_idx],
                embeddings=pre_computed_embeddings[i:end_idx],
                metadatas=metadatas[i:end_idx]
            )

        print(f"Successfully indexed {len(ids)} chunks in ChromaDB.")
        return len(ids)

    def query(self, query_text, manual_name=None, flowchart_id=None, n_results=3):
        """
        LEARNER TIP:
        1. Encodes the search query string into a vector.
        2. Applies metadata filters (e.g. searching only page '2').
        3. Returns the nearest matching documents based on Cosine Distance.
        """
        collection = self.get_collection()
        # Convert user's query text into a 384-dimensional vector list
        query_embedding = self.model.encode(query_text).tolist()
        
        # Build filter dict using ChromaDB's where conditions
        where_filter = {}
        filters = []
        
        if manual_name:
            filters.append({"manual_name": manual_name})
        if flowchart_id:
            filters.append({"flowchart_id": str(flowchart_id)})
            
        if len(filters) == 1:
            where_filter = filters[0]
        elif len(filters) > 1:
            # Apply an '$and' operator to ensure both filters must match
            where_filter = {"$and": filters}
        else:
            where_filter = None
            
        # Execute search query in vector space
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter
        )
        return results
