import re
import numpy as np

class SemanticChunker:
    """
    LEARNER TIP:
    Semantic Chunker splits text based on sentence embedding similarity.
    It groups adjacent sentences together as long as their embedding vectors are close.
    If the embedding model fails to load, it falls back to recursive character splitting.
    """
    def __init__(self, model_name="all-MiniLM-L6-v2", similarity_threshold_percentile=75, max_chunk_size=600):
        self.model_name = model_name
        self.similarity_threshold_percentile = similarity_threshold_percentile
        self.max_chunk_size = max_chunk_size
        self._model = None

    @property
    def model(self):
        """
        LEARNER TIP:
        Lazy loads the transformer model inside a try-except statement.
        If importing fails (due to blocked C-extensions/DLLs), we set self._model = False
        so the application fails over to the standard character chunker instead of crashing.
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                print(f"Warning: Failed to load sentence-transformers model '{self.model_name}': {e}.")
                print("Falling back to Recursive Character Text Splitting.")
                self._model = False
        return self._model

    def split_sentences(self, text):
        """
        LEARNER TIP:
        Regex-based sentence splitter. It checks for periods, question marks, and exclamation marks.
        Uses negative lookbehinds (e.g. (?<!\w\.\w.)) to avoid splitting on abbreviations like 'e.g.', 'i.e.', or 'Mr.'.
        """
        sentence_end = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!)\s+')
        sentences = sentence_end.split(text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _cosine_similarity(self, v1, v2):
        """
        LEARNER TIP:
        Calculates the Cosine Similarity between two vector arrays v1 and v2.
        Formula: DotProduct(v1, v2) / (Norm(v1) * Norm(v2))
        """
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)

    def split_text_semantically(self, text):
        """
        LEARNER TIP:
        1. Encodes all sentences into vectors.
        2. Computes the distance (1.0 - similarity) between consecutive sentences.
        3. Identifies the 75th percentile of distances as the partition threshold.
        4. Splits the text into chunks at those boundaries.
        """
        model = self.model
        if not model:
            # Fallback to recursive splitter if model isn't available
            return self.split_text_recursive(text)

        sentences = self.split_sentences(text)
        if len(sentences) < 3:
            # Paragraph is too short to find a threshold; keep it as a single chunk
            return [text]

        try:
            # Get numerical vector lists for each sentence
            embeddings = model.encode(sentences, show_progress_bar=False)
            
            # Calculate cosine distance (1.0 - CosineSimilarity) between adjacent sentences
            distances = []
            for i in range(len(embeddings) - 1):
                sim = self._cosine_similarity(embeddings[i], embeddings[i+1])
                distances.append(1.0 - sim)

            # Define the splitting threshold using a statistical percentile
            threshold = np.percentile(distances, self.similarity_threshold_percentile)

            chunks = []
            current_chunk_sentences = [sentences[0]]
            current_len = len(sentences[0])

            for i in range(1, len(sentences)):
                sentence = sentences[i]
                dist = distances[i-1]
                
                # Check if the semantic shift exceeds the threshold, or if adding this sentence 
                # exceeds the maximum character chunk size limit.
                if dist >= threshold or current_len + len(sentence) + 1 > self.max_chunk_size:
                    chunks.append(" ".join(current_chunk_sentences))
                    current_chunk_sentences = [sentence]
                    current_len = len(sentence)
                else:
                    current_chunk_sentences.append(sentence)
                    current_len += len(sentence) + 1

            if current_chunk_sentences:
                chunks.append(" ".join(current_chunk_sentences))

            return chunks

        except Exception as e:
            # Fallback if any unexpected calculation error occurs (e.g. dimensions mismatch)
            print(f"Error during semantic splitting: {e}. Falling back to recursive splitting.")
            return self.split_text_recursive(text)

    def split_text_recursive(self, text, chunk_size=450, chunk_overlap=50):
        """
        LEARNER TIP:
        Deterministic character splitter.
        Groups sentences together until the character count reaches 'chunk_size' (450).
        If a single sentence is longer than 450 characters, it splits it by words to keep chunks small.
        """
        if len(text) <= chunk_size:
            return [text]

        sentences = self.split_sentences(text)
        chunks = []
        current_chunk = []
        current_len = 0

        for sentence in sentences:
            # If adding this sentence would exceed the limit
            if current_len + len(sentence) + (1 if current_chunk else 0) > chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                # Word splitting fallback if a single sentence is larger than the entire chunk size
                if len(sentence) > chunk_size:
                    words = sentence.split(" ")
                    word_chunk = []
                    word_len = 0
                    for w in words:
                        if word_len + len(w) + 1 > chunk_size:
                            if word_chunk:
                                chunks.append(" ".join(word_chunk))
                            word_chunk = [w]
                            word_len = len(w)
                        else:
                            word_chunk.append(w)
                            word_len += len(w) + 1
                    if word_chunk:
                        current_chunk = word_chunk
                        current_len = word_len
                else:
                    current_chunk = [sentence]
                    current_len = len(sentence)
            else:
                current_chunk.append(sentence)
                current_len += len(sentence) + (1 if len(current_chunk) > 1 else 0)

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

def chunk_paragraphs(paragraphs, chunker=None):
    """
    LEARNER TIP:
    Loop function that takes a list of constructed flowchart paragraph dictionaries,
    runs them through the Semantic Chunker, and returns a flat list of text chunks
    formatted with IDs and logical metadata.
    """
    if chunker is None:
        chunker = SemanticChunker()

    all_chunks = []
    
    for p in paragraphs:
        text = p["text"]
        chunks = chunker.split_text_semantically(text)
        
        for idx, chunk_text in enumerate(chunks):
            all_chunks.append({
                "chunk_id": f"{p['paragraph_id']}_c{idx + 1}",
                "paragraph_id": p["paragraph_id"],
                "manual_name": p["manual_name"],
                "flowchart_id": p["flowchart_id"],
                "text": chunk_text,
                "decision_path": p["decision_path"]  # Keep full decision path for RAG context
            })
            
    return all_chunks

