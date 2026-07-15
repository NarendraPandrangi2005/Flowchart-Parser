import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
import networkx as nx

def build_nx_graph(page_data):
    """
    LEARNER TIP:
    Builds a NetworkX Directed Graph (DiGraph) from simplified page data.
    NetworkX makes it easy to model nodes and edges, and run graph algorithms
    like path-finding.
    """
    G = nx.DiGraph()
    for node in page_data.get("nodes", []):
        # Add node with all its attributes unpacked (**node)
        G.add_node(node["id"], **node)
    for edge in page_data.get("edges", []):
        G.add_edge(edge["source"], edge["destination"], condition=edge.get("condition", ""))
    return G

def path_to_paragraph(path, G, flowchart_id, vllm_client):
    """
    Translates a sequence of graph nodes and edges (a path) into a natural language paragraph
    using a locally hosted vLLM model (e.g. Qwen).
    """
    steps_desc = []
    for idx, node_id in enumerate(path):
        node_data = G.nodes[node_id]
        text = node_data.get("text", "").strip()
        text = " ".join(text.split())
        
        if idx == 0:
            steps_desc.append(f"- Start at the step: '{text}'")
        else:
            prev_id = path[idx - 1]
            edge_data = G.edges[prev_id, node_id]
            cond = edge_data.get("condition", "").strip()
            if cond:
                steps_desc.append(f"- If the choice/condition is '{cond}', proceed to: '{text}'")
            else:
                steps_desc.append(f"- Proceed to: '{text}'")
                
    steps_text = "\n".join(steps_desc)
    
    prompt = (
        f"You are an expert technical writer. Convert the following sequence of troubleshooting steps from a flowchart path into a single, cohesive, grammatically correct paragraph.\n\n"
        f"Troubleshooting steps:\n"
        f"{steps_text}\n\n"
        f"Guidelines:\n"
        f"1. Write a single, continuous, fluent paragraph. Do not use bullet points, numbered lists, or line breaks.\n"
        f"2. Be precise and clear. Translate conditions (like YES/NO/ON/OFF) into smooth natural English transitions.\n"
        f"3. Maintain the exact logical flow. Do not add or assume any steps not explicitly listed.\n"
        f"4. Keep the paragraph professional and concise.\n"
        f"5. Start directly with the text. Do NOT include any introductory or concluding comments (e.g. do not say 'Here is the paragraph' or 'This describes').\n"
        f"6. IMPORTANT: Do NOT output any <think> tags or reasoning steps. Output ONLY the final paragraph."
    )
    
    paragraph = vllm_client.query(
        prompt=prompt,
        system_instruction="You are a precise technical writer that converts flowchart paths into descriptive troubleshooting paragraphs. Output only the final paragraph without thinking/reasoning.",
        temperature=0.1,
        max_tokens=1024
    )
    if paragraph:
        # Strip any <think>...</think> tags if returned by the model
        paragraph = re.sub(r'<think>.*?</think>', '', paragraph, flags=re.DOTALL).strip()
        return paragraph
    raise ValueError("Empty response from local vLLM server")

def generate_paragraphs_from_graph(simplified_graph, manual_name="sample.pdf", vllm_client=None):
    """
    LEARNER TIP:
    Traverses the simplified graph to extract paths and generate paragraphs.
    1. Identifies start nodes (nodes with an in-degree of 0, meaning no arrows point to them).
    2. Identifies sink/end nodes (nodes with an out-degree of 0, meaning no arrows point away from them).
    3. Finds all simple paths from each start to each end node using NetworkX.
    4. Converts each path to a prose paragraph.
    """
    if vllm_client is None:
        from services.vllm_client import VllmClient
        vllm_client = VllmClient()
        print(f"Initialized local vLLM client using model: {vllm_client.model} at URL: {vllm_client.api_url}")

    all_paths_to_process = []
    
    for page_num, data in simplified_graph.items():
        nodes = data.get("nodes", [])
        if not nodes:
            continue
            
        G = build_nx_graph(data)
        
        # --- IDENTIFY START TERMINALS ---
        starts = [n for n, d in G.in_degree() if d == 0]
        if not starts:
            for node_id in G.nodes:
                node_data = G.nodes[node_id]
                text = str(node_data.get("text", "")).lower()
                type_ = str(node_data.get("type", "")).lower()
                if "start" in text or "start" in type_:
                    starts.append(node_id)
        if not starts and G.nodes:
            starts = [list(G.nodes.keys())[0]]
            
        # --- IDENTIFY SINK TERMINALS (END NODES) ---
        sinks = [n for n, d in G.out_degree() if d == 0]
        if not sinks:
            sinks = list(G.nodes.keys())
            
        # --- PATH FINDING ---
        for start in starts:
            for sink in sinks:
                if start == sink:
                    continue
                try:
                    paths = list(nx.all_simple_paths(G, source=start, target=sink))
                    for path in paths:
                        all_paths_to_process.append((path, G, page_num))
                except nx.NetworkXNoPath:
                    continue
                except Exception as e:
                    print(f"Error finding paths from {start} to {sink} on page {page_num}: {e}")

    # Process all paths concurrently using ThreadPoolExecutor to take advantage of vLLM batching
    def process_single_path(item):
        path, G, page_num = item
        try:
            text = path_to_paragraph(path, G, page_num, vllm_client)
            return {"path": path, "G": G, "page_num": page_num, "text": text, "error": None}
        except Exception as e:
            return {"path": path, "G": G, "page_num": page_num, "text": None, "error": e}

    print(f"Sending {len(all_paths_to_process)} paths to local vLLM for paragraph generation concurrently...")
    
    # 15 concurrent workers leverages vLLM's internal continuous batching on local GPU
    with ThreadPoolExecutor(max_workers=15) as executor:
        results = list(executor.map(process_single_path, all_paths_to_process))

    results_by_page = {}
    for res in results:
        path = res["path"]
        G = res["G"]
        page_num = res["page_num"]
        paragraph_text = res["text"]
        error = res["error"]
        
        if error:
            print(f"Failed to generate paragraph for a path on page {page_num}: {error}")
            continue
            
        if page_num not in results_by_page:
            results_by_page[page_num] = {
                "paths": [],
                "texts": [],
                "G": G
            }
        results_by_page[page_num]["paths"].append(path)
        results_by_page[page_num]["texts"].append(paragraph_text)

    generated_paragraphs = []
    
    print("\nMerging path paragraphs page by page using local vLLM...")
    for page_num, page_data in results_by_page.items():
        texts = page_data["texts"]
        paths = page_data["paths"]
        G = page_data["G"]
        
        if len(texts) == 1:
            merged_text = texts[0]
        else:
            combined_paths_text = "\n\n".join(texts)
            merge_prompt = (
                f"You are an expert technical writer. You are given multiple individual decision path paragraphs "
                f"for the same troubleshooting flowchart page. Merge them into a single, cohesive, grammatically correct "
                f"troubleshooting paragraph that covers all options, decisions, and outcomes in a logical sequence.\n\n"
                f"Individual path paragraphs:\n"
                f"{combined_paths_text}\n\n"
                f"Guidelines:\n"
                f"1. Write a single, continuous, fluent paragraph. Do not use bullet points, numbered lists, or line breaks.\n"
                f"2. Be precise and clear. Combine different decision branches using smooth logical transitions (e.g., 'If..., then... Otherwise, if...').\n"
                f"3. Maintain the exact logical flow. Do not add or assume any steps not explicitly listed.\n"
                f"4. Keep the paragraph professional and concise.\n"
                f"5. Start directly with the text. Do NOT include any introductory or concluding comments.\n"
                f"6. IMPORTANT: Do NOT output any <think> tags or reasoning steps. Output ONLY the final merged paragraph."
            )
            try:
                merged_text = vllm_client.query(
                    prompt=merge_prompt,
                    system_instruction="You are a precise technical writer that merges multiple flowchart path paragraphs into a single cohesive troubleshooting paragraph. Output only the final paragraph without thinking/reasoning.",
                    temperature=0.1,
                    max_tokens=2048
                )
                if merged_text:
                    merged_text = re.sub(r'<think>.*?</think>', '', merged_text, flags=re.DOTALL).strip()
                else:
                    merged_text = " ".join(texts)
            except Exception as e:
                print(f"Error merging paragraphs for page {page_num}: {e}. Falling back to concatenation.")
                merged_text = " ".join(texts)
                
        # Collect unique steps from all paths on this page
        seen_nodes = set()
        decision_path_steps = []
        for path in paths:
            for idx, node_id in enumerate(path):
                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    node_data = G.nodes[node_id]
                    step = {
                        "node_id": node_id,
                        "text": node_data.get("text", "").strip(),
                        "type": node_data.get("type", "")
                    }
                    if idx < len(path) - 1:
                        next_id = path[idx + 1]
                        if G.has_edge(node_id, next_id):
                            step["transition"] = G.edges[node_id, next_id].get("condition", "")
                    decision_path_steps.append(step)

        # Save single page paragraph
        generated_paragraphs.append({
            "paragraph_id": f"p_{flowchart_id_to_str(page_num)}",
            "manual_name": manual_name,
            "flowchart_id": page_num,
            "decision_path": decision_path_steps,
            "text": merged_text
        })
        
    return generated_paragraphs

def flowchart_id_to_str(page):
    # Formats page IDs safely for JSON key names
    return str(page).replace(" ", "_")

def generate_paragraphs_file(input_graph_path, output_filepath, manual_name="sample.pdf", vllm_client=None):
    """
    LEARNER TIP:
    Reads the simplified graph from disk, generates paths, and writes the
    troubleshooting path paragraphs out to disk as a JSON file ('paragraphs.json').
    """
    if not os.path.exists(input_graph_path):
        raise FileNotFoundError(f"Simplified graph file not found at: {input_graph_path}")
        
    with open(input_graph_path, "r", encoding="utf-8") as f:
        simplified_graph = json.load(f)
        
    paragraphs = generate_paragraphs_from_graph(simplified_graph, manual_name, vllm_client)
    
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(paragraphs, f, indent=2)
        
    return paragraphs
