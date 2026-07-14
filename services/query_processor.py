import json
import os
import re

def find_referenced_nodes(query_text, nodes):
    """
    LEARNER TIP:
    This function analyzes the user's natural language question to see if they
    specifically mentioned any physical elements of the flowchart (like a circuit breaker [CB1]).
    It returns a list of matching nodes.
    """
    referenced = []
    q_lower = query_text.lower()
    
    for node in nodes:
        node_text = node.get("text", "").lower()
        node_id = node.get("id", "").lower()
        
        # --- METHOD 1: EXACT MATCH ON ID ---
        # If the user explicitly typed the ID (e.g. "rect_3" or "decision_1")
        if node_id in q_lower:
            referenced.append(node)
            continue
            
        # --- METHOD 2: BRACKETED TERM MATCH (e.g. "[CB1]") ---
        # Flowcharts often tag instruments inside square brackets.
        # This regex looks for text between brackets: \[ matches '[', (.*?) is the capture group, \] matches ']'
        brackets = re.findall(r'\[(.*?)\]', node.get("text", ""))
        matched_abbr = False
        for abbr in brackets:
            abbr_clean = abbr.lower().strip()
            # If the user mentioned this bracketed term in their query, mark it as referenced.
            # We use word boundary \b to prevent matching partial strings (e.g. 'cb1' matching 'cb10')
            if abbr_clean:
                pattern = r'\b' + re.escape(abbr_clean) + r'\b'
                if re.search(pattern, q_lower):
                    referenced.append(node)
                    matched_abbr = True
                    break
        if matched_abbr:
            continue
            
        # --- METHOD 3: PHRASE MATCH ---
        # Remove the bracketed terms from the node text to do a clean string comparison
        clean_node_text = re.sub(r'\[.*?\]', '', node.get("text", "")).strip().lower()
        clean_node_text = clean_node_text.replace("?", "").strip()
        # Ensure we only match meaningful, longer phrases (length > 4) using word boundaries
        if len(clean_node_text) > 4:
            pattern = r'\b' + re.escape(clean_node_text) + r'\b'
            if re.search(pattern, q_lower):
                referenced.append(node)
            
    return referenced

def process_query_pipeline(query_text, graph_path, paragraphs_path, vector_store, manual_name="sample.pdf", flowchart_id=None, n_results=3):
    """
    LEARNER TIP:
    This is the core RAG orchestration pipeline. It coordinates:
      1. Loading flowchart data files.
      2. Priority Graph Matching (checks if specific components are in the query).
      3. Semantic/Keyword Vector Store Search.
      4. Merging contexts & generating a clean prompt for the LLM.
    """
    # Defensive checks: make sure our JSON files are compiled and ready on disk
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Simplified graph file not found at: {graph_path}")
    if not os.path.exists(paragraphs_path):
        raise FileNotFoundError(f"Paragraphs file not found at: {paragraphs_path}")
        
    # Read the simplified graph data
    with open(graph_path, "r", encoding="utf-8") as f:
        graph_data = json.load(f)
        
    # Read the generated path paragraphs
    with open(paragraphs_path, "r", encoding="utf-8") as f:
        paragraphs_data = json.load(f)
        
    # --- STAGE 1: GET ACTIVE NODES ---
    # Retrieve nodes relevant to the active flowchart page
    active_nodes = []
    if flowchart_id:
        for node in graph_data.get(str(flowchart_id), {}).get("nodes", []):
            node_copy = dict(node)
            node_copy["flowchart_id"] = str(flowchart_id)
            active_nodes.append(node_copy)
    else:
        # If no page filter is active, merge nodes from all pages in the document
        for page_num, page_data in graph_data.items():
            for node in page_data.get("nodes", []):
                node_copy = dict(node)
                node_copy["flowchart_id"] = str(page_num)
                active_nodes.append(node_copy)
            
    # --- STAGE 2: PRIORITY GRAPH PATH RETRIEVAL ---
    # Detect if the query references specific flowchart components (like CB1)
    referenced_nodes = find_referenced_nodes(query_text, active_nodes)
    
    graph_context_chunks = []
    graph_paths = []
    
    # If the user mentioned a node, we grab all troubleshooting paragraphs that pass through it!
    if referenced_nodes:
        # Create scoped page/node matching keys to prevent crossing page boundaries
        referenced_keys = {(str(n["flowchart_id"]), str(n["id"])) for n in referenced_nodes}
        print(f"Detected direct flowchart node references in query: {[(n.get('flowchart_id'), n.get('text')) for n in referenced_nodes]}")
        for p in paragraphs_data:
            # Apply file filter
            if manual_name and p["manual_name"] != manual_name:
                continue
            # Apply page filter
            p_flowchart_id = str(p["flowchart_id"])
            if flowchart_id and p_flowchart_id != str(flowchart_id):
                continue
                
            # Check if this paragraph's decision path contains any of the referenced node IDs on the same page
            path_keys = {(p_flowchart_id, str(step["node_id"])) for step in p["decision_path"]}
            if referenced_keys.intersection(path_keys):
                graph_context_chunks.append(p["text"])
                graph_paths.append(p["decision_path"])
                
        print(f"Retrieved {len(graph_context_chunks)} matching flowchart path paragraphs via graph prioritization.")
        
    # --- STAGE 3: RETRIEVE FROM CHROMADB OR FALLBACK ---
    semantic_chunks = []
    semantic_metadatas = []
    
    try:
        # Query the local database for semantically matching snippets
        semantic_results = vector_store.query(
            query_text=query_text,
            manual_name=manual_name,
            flowchart_id=flowchart_id,
            n_results=n_results
        )
        if semantic_results and "documents" in semantic_results and semantic_results["documents"]:
            semantic_chunks = semantic_results["documents"][0]
            semantic_metadatas = semantic_results["metadatas"][0]
    except Exception as e:
        # LEARNER TIP:
        # If your machine blocks SciPy/SentenceTransformers, we catch the error here
        # and redirect execution to a standard string/keyword match over the paragraphs.
        print(f"Warning: Semantic retrieval failed (e.g. DLL loading blocked/scipy issue): {e}")
        print("Falling back to standard keyword/phrase substring matching.")
        semantic_chunks = fallback_keyword_search(
            query_text=query_text,
            paragraphs_data=paragraphs_data,
            manual_name=manual_name,
            flowchart_id=flowchart_id,
            n_results=n_results
        )
        
    # --- STAGE 4: COMBINE AND DEDUPLICATE CONTEXTS ---
    # Start our context list with the highly-accurate graph-prioritized chunks
    final_chunks = list(graph_context_chunks)
    
    # Append the search chunks, making sure not to add duplicates
    for c in semantic_chunks:
        if c not in final_chunks:
            final_chunks.append(c)
            
    # Slice to top n_results BEFORE calculating citations and prompt context
    final_sliced_chunks = final_chunks[:n_results]
            
    # --- STAGE 5: CITATION BUILDER ---
    # Find all flowchart pages referenced in this retrieval to cite them
    pages_referenced = set()
    if flowchart_id:
        pages_referenced.add(str(flowchart_id))
    for p in paragraphs_data:
        if p["text"] in final_sliced_chunks:
            pages_referenced.add(str(p["flowchart_id"]))
            
    # Clean and sort page citations numerically
    pages_referenced = sorted(list(filter(None, pages_referenced)), key=int)
    citations = f"\n\n**Sources:** Page {', '.join(pages_referenced)} Flowchart"
    
    # Prepare the formatted context string
    context_str = "\n".join([f"- {c}" for c in final_sliced_chunks])
    
    # Build final system instructions and prompt
    prompt = (
        f"Context (Retrieved Troubleshooting Flowchart Steps):\n{context_str}\n\n"
        f"User Troubleshooting Issue/Question: \"{query_text}\"\n\n"
        "Trace the step-by-step instructions from the context above matching the user's issue and provide corrective actions."
    )
    
    return {
        "prompt": prompt,
        "context_chunks": final_sliced_chunks,
        "citations": citations,
        "graph_prioritized": len(graph_context_chunks) > 0,
        "referenced_nodes": [n["text"] for n in referenced_nodes]
    }

def fallback_keyword_search(query_text, paragraphs_data, manual_name=None, flowchart_id=None, n_results=3):
    """
    LEARNER TIP:
    Pure Python search fallback. It calculates a simple match score for each paragraph
    by checking how many query words are present. No neural network dependencies are needed.
    """
    # Set of common words to filter out (stop words) since they carry no semantic value
    stop_words = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "to", "of", "in", "on", "off", "yes", "no", "if", "for", "with", "at", "by", "from"}
    query_words = [w.strip(",.?!()").lower() for w in query_text.split() if w.strip(",.?!()").lower() not in stop_words]
    
    if not query_words:
        # Fallback split if the query only contained stop words
        query_words = [w.strip(",.?!()").lower() for w in query_text.split() if w.strip(",.?!()").strip()]
        
    scored_paragraphs = []
    
    for p in paragraphs_data:
        # Check filters
        if manual_name and p.get("manual_name") != manual_name:
            continue
        if flowchart_id and str(p.get("flowchart_id")) != str(flowchart_id):
            continue
            
        p_text = p.get("text", "").lower()
        score = 0
        
        # Give a massive score reward if the entire query matches a substring
        if query_text.lower() in p_text:
            score += 10
            
        # Count frequency of each query keyword
        for word in query_words:
            if len(word) > 1:
                # Add score points for each occurrence
                score += p_text.count(word) * 2
                # Tiny score reward if the word is a partial substring of any word in the text
                if word not in p_text and any(word in p_word for p_word in p_text.split()):
                    score += 1
                    
        # If the paragraph matched any keyword, add it to our candidate list
        if score > 0:
            scored_paragraphs.append((score, p.get("text")))
            
    # Sort paragraphs by score descending (highest score first)
    scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
    
    # Return the clean text of the top N results
    return [text for _, text in scored_paragraphs[:n_results]]


