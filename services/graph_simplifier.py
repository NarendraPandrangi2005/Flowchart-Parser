import json
import os

def simplify_node_type(raw_type):
    """
    LEARNER TIP:
    Maps raw visual shape classifications from the PDF (e.g., 'decision_box')
    to user-friendly, logical Flowchart Node Types (e.g., 'Decision').
    """
    # Define a lookup dictionary (key-value mapping) for the shapes
    mapping = {
        "decision_box": "Decision",         # Diamonds in the flowchart
        "process_box": "Process",           # Rectangles in the flowchart
        "start_end_terminal": "Start/End"   # Ovals/Circles in the flowchart
    }
    # Look up the type in mapping. If it is not found, return the raw_type as a default.
    return mapping.get(raw_type, raw_type)

def simplify_graph_data(raw_graph):
    """
    LEARNER TIP:
    Takes the raw, highly complex decision graph dictionary extracted from the PDF
    and discards coordinates, bounding boxes, and other visual metadata.
    It returns a clean logical structure containing only text and connections.
    """
    # Create an empty dictionary to hold the simplified graph data
    simplified = {}
    
    # Loop through each page in the raw graph (e.g., page_id "1", "2", etc.)
    for page_id, page_data in raw_graph.items():
        simplified_nodes = []
        simplified_edges = []
        
        # --- PART 1: SIMPLIFYING FLOWCHART BOXES (NODES) ---
        # Get the 'nodes' list from page_data. If not present, default to an empty list [].
        for node in page_data.get("nodes", []):
            # Construct a clean node dictionary with only the essential details
            simplified_node = {
                # Get 'id' or fallback to 'node_id' if key name differs
                "id": node.get("id") or node.get("node_id"),
                # Convert the shape type to a logical name (e.g. 'process_box' -> 'Process')
                "type": simplify_node_type(node.get("type")),
                # Clean up the text by stripping leading/trailing whitespace
                "text": node.get("text", "").strip()
            }
            # Append the cleaned node to our temporary list for this page
            simplified_nodes.append(simplified_node)
            
        # --- PART 2: SIMPLIFYING FLOWCHART ARROWS (EDGES) ---
        # Get the 'edges' list from page_data. If not present, default to an empty list [].
        for edge in page_data.get("edges", []):
            # Construct a clean edge dictionary representing logical transitions
            simplified_edge = {
                # 'from' is where the arrow starts (source node ID)
                "source": edge.get("from"),
                # 'to' is where the arrow points (destination node ID)
                "destination": edge.get("to"),
                # 'label' represents choice text like 'YES', 'NO', 'ON', 'OFF'
                "condition": edge.get("label") or ""
            }
            # Append the cleaned connection to our temporary list for this page
            simplified_edges.append(simplified_edge)
            
        # --- PART 3: SAVING TO THE PAGE DICTIONARY ---
        # Store the simplified nodes and connections under this page ID
        simplified[page_id] = {
            "nodes": simplified_nodes,
            "edges": simplified_edges
        }
        
    return simplified

def simplify_graph_file(input_filepath, output_filepath):
    """
    LEARNER TIP:
    Loads a raw JSON file from disk, runs the simplification logic,
    and writes the cleaned output back to a new JSON file on disk.
    """
    # Defensive programming: Check if the file actually exists before trying to open it
    if not os.path.exists(input_filepath):
        raise FileNotFoundError(f"Original graph file not found at: {input_filepath}")
        
    # Open and load the raw JSON data
    with open(input_filepath, "r", encoding="utf-8") as f:
        raw_graph = json.load(f)
        
    # Simplify the raw graph data in memory
    simplified = simplify_graph_data(raw_graph)
    
    # Write the simplified graph to a new JSON file with indent=2 (easy to read)
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(simplified, f, indent=2)
        
    return simplified

