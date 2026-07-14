import json
import os
import urllib.request
import urllib.error

def load_graph():
    """
    LEARNER TIP:
    Reads and loads the simplified decision graph nodes and edges from the JSON file.
    If the file is missing, it alerts the user to run the parsing pipeline first.
    """
    graph_path = "simplified_decision_graph.json"
    if not os.path.exists(graph_path):
        print(f"Error: {graph_path} not found. Run parser.py first.")
        return None
    with open(graph_path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    """
    LEARNER TIP:
    Standalone command line interface (CLI) to query the flowchart troubleshooting assistant.
    Steps:
      1. Loads the flowchart logical graph.
      2. Validates your Groq API Key.
      3. Prompts you to pick which flowchart/page you want to search.
      4. Captures your problem description/query.
      5. Runs the retrieval pipeline to extract relevant flowchart branches.
      6. Queries the Groq LLM model and prints the final guided solution.
    """
    graph = load_graph()
    if not graph:
        return

    # --- API KEY AUTHENTICATION ---
    # Retrieve the API key from system environment variables
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        # Prompt the user to input the key manually if not found in environmental variables
        api_key = input("Enter your Groq API Key: ").strip()
        if not api_key:
            print("Groq API Key is required. Exiting.")
            return

    # --- FLOWCHART SELECTION ---
    print("\nAvailable Flowcharts:")
    # Sort the page IDs numerically
    pages_list = sorted(list(graph.keys()), key=int)
    for idx, page in enumerate(pages_list):
        nodes = graph[page]["nodes"]
        title = f"Page {page} Flowchart"
        if nodes:
            # Append the text of the first step (the start node) to give the user context
            title = f"Page {page} Flowchart (Starts with: {nodes[0]['text'][:45]}...)"
        print(f"  {idx + 1}. {title}")
        
    choice = input("\nSelect a flowchart number to query: ").strip()
    try:
        page_idx = int(choice) - 1
        page_num = pages_list[page_idx]
    except:
        print("Invalid selection. Exiting.")
        return

    # --- USER QUERY ENTRY ---
    user_query = input("\nEnter your query/issue: ").strip()
    if not user_query:
        print("Empty query. Exiting.")
        return

    # --- RETRIEVAL-AUGMENTED GENERATION (RAG) RUNNER ---
    try:
        from services.vector_store import VectorStoreManager
        from services.query_processor import process_query_pipeline
        from services.groq_client import GroqClient
        
        # Initialize vector store manager
        vector_store = VectorStoreManager()
        
        # Execute hybrid search process
        processed = process_query_pipeline(
            query_text=user_query,
            graph_path="simplified_decision_graph.json",
            paragraphs_path="paragraphs.json",
            vector_store=vector_store,
            flowchart_id=page_num,
            n_results=3
        )
        
        retrieved_chunks = processed["context_chunks"]
        prompt = processed["prompt"]
        citations = processed["citations"]
        
        # Log if structural prioritization activated
        if processed.get("graph_prioritized"):
            print(f"\n[Graph Prioritization Active]: Matched nodes: {processed.get('referenced_nodes')}")
    except Exception as e:
        print(f"Error executing flowchart retrieval pipeline: {e}")
        return

    if not retrieved_chunks:
        print("No matching troubleshooting path chunks found.")
        return

    # Print matching path paragraphs for debugging and learning
    print("\n[Retrieved Context Chunks]:")
    for idx, chunk in enumerate(retrieved_chunks):
        print(f"  {idx + 1}. {chunk}")

    # --- LLM SYNTHESIS & INFERENCE CALL ---
    print("\nQuerying Groq API... Please wait...")
    try:
        groq_client = GroqClient(api_key=api_key)
        response_text = groq_client.query(prompt)
        if response_text:
            print("\n=======================================================")
            print("   GROQ AI TROUBLESHOOTING RESPONSE")
            print("=======================================================\n")
            print(response_text + citations)
            print("\n=======================================================\n")
    except Exception as e:
        print(f"Error querying Groq LLM: {e}")

if __name__ == "__main__":
    main()

