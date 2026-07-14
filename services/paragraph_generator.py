import json
import os
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

def path_to_paragraph(path, G, flowchart_id):
    """
    LEARNER TIP:
    Converts a sequence of graph nodes and edges (a path) into a natural language paragraph.
    This uses custom NLP string transformations to translate choices (YES/NO/ON/OFF)
    into flowing conditional sentences (e.g. 'If it does not check CB14...').
    """
    sentences = []
    skip_next = False
    
    for i in range(len(path)):
        if skip_next:
            skip_next = False
            continue
            
        node_id = path[i]
        node_data = G.nodes[node_id]
        current_text = node_data.get("text", "").strip()
        current_type = node_data.get("type", "")
        
        # Clean current text (normalize whitespace)
        current_text = " ".join(current_text.split())
        if current_text.endswith("."):
            current_text = current_text[:-1]
            
        # First node in path (Start terminal)
        if i == 0:
            sentences.append(f"To start troubleshooting the flowchart for page {flowchart_id}, begin at the step '{current_text}'.")
            continue
            
        # Transition clause from previous node to current node
        prev_id = path[i - 1]
        prev_data = G.nodes[prev_id]
        edge_data = G.edges[prev_id, node_id]
        cond = edge_data.get("condition", "").strip()
        
        prev_text = prev_data.get("text", "").strip()
        prev_text = " ".join(prev_text.split())
        if prev_text.endswith("?"):
            prev_q = prev_text[:-1]
        else:
            prev_q = prev_text
            
        # Remove brackets if they enclose instrument references (e.g., [CB14] -> CB14)
        prev_q = prev_q.replace("[", "").replace("]", "")
        
        # --- NLP TRANSFORMATION RULES ---
        # Translate raw edge conditions into gramatically readable English
        if cond:
            cond_lower = cond.lower()
            if cond_lower == "no":
                if prev_q.lower().startswith("does "):
                    rest = prev_q[5:].strip()
                    words = rest.split()
                    if len(words) > 1:
                        subject = words[0]
                        verb_phrase = " ".join(words[1:])
                        transition_clause = f"If {subject} does not {verb_phrase}"
                    else:
                        transition_clause = f"If it does not {rest}"
                elif prev_q.lower().startswith("is "):
                    rest = prev_q[3:].strip()
                    transition_clause = f"If {rest} is not the case"
                else:
                    transition_clause = f"If the answer to '{prev_q}' is no"
            elif cond_lower == "yes":
                if prev_q.lower().startswith("does "):
                    rest = prev_q[5:].strip()
                    words = rest.split()
                    if len(words) > 1:
                        # Simple rule to pluralize verb inside 'YES' transitions
                        subject = words[0]
                        verb = words[1]
                        if verb.endswith("y"):
                            if len(verb) > 1 and verb[-2] not in "aeiou":
                                verb_plural = verb[:-1] + "ies"
                            else:
                                verb_plural = verb + "s"
                        elif verb.endswith("s") or verb.endswith("sh") or verb.endswith("ch"):
                            verb_plural = verb + "es"
                        else:
                            verb_plural = verb + "s"
                        verb_phrase = verb_plural + " " + " ".join(words[2:]) if len(words) > 2 else verb_plural
                        transition_clause = f"If {subject} {verb_phrase}"
                    else:
                        transition_clause = f"If it does {rest}"
                elif prev_q.lower().startswith("is "):
                    rest = prev_q[3:].strip()
                    transition_clause = f"If {rest}"
                else:
                    transition_clause = f"If the answer to '{prev_q}' is yes"
            elif cond_lower in ["on", "off"]:
                transition_clause = f"If the setting for '{prev_q}' is {cond.upper()}"
            else:
                transition_clause = f"If the condition is '{cond}' for '{prev_q}'"
        else:
            transition_clause = f"From '{prev_q}'"
            
        # --- COMBINING CONSECUTIVE STEPS ---
        # Look ahead one step. If the current step is 'Check X' and the next step is 'Replace/Repair X',
        # combine them into one fluent sentence: 'Check X. If faulty, replace/repair it.'
        combined = False
        if i < len(path) - 1:
            next_id = path[i + 1]
            next_data = G.nodes[next_id]
            next_text = next_data.get("text", "").strip()
            next_text = " ".join(next_text.split())
            if next_text.endswith("."):
                next_text = next_text[:-1]
                
            if current_text.lower().startswith("check ") and (next_text.lower().startswith("replace") or next_text.lower().startswith("repair") or next_text.lower().startswith("troubleshoot")):
                target_obj = current_text[6:].strip()
                verb_phrase = next_text.lower()
                
                # Make pronouns clean
                if "fuse" in verb_phrase and "replace" in verb_phrase:
                    verb_phrase = "replace it"
                elif "wire" in verb_phrase and "repair" in verb_phrase:
                    verb_phrase = "repair it"
                    
                sentence = f"{transition_clause}, check {target_obj}. If {target_obj} is faulty, {verb_phrase} before continuing with the troubleshooting process."
                sentences.append(sentence)
                combined = True
                skip_next = True # Skip the next node because we merged it into this sentence
                
        if not combined:
            sentences.append(f"{transition_clause}, proceed to '{current_text}'.")
            
    # Combine sentences and add a final period if not present
    paragraph = " ".join(sentences)
    if not paragraph.endswith("."):
        paragraph += "."
    return paragraph

def generate_paragraphs_from_graph(simplified_graph, manual_name="sample.pdf"):
    """
    LEARNER TIP:
    Traverses the simplified graph to extract paths and generate paragraphs.
    1. Identifies start nodes (nodes with an in-degree of 0, meaning no arrows point to them).
    2. Identifies sink/end nodes (nodes with an out-degree of 0, meaning no arrows point away from them).
    3. Finds all simple paths from each start to each end node using NetworkX.
    4. Converts each path to a prose paragraph.
    """
    generated_paragraphs = []
    paragraph_id_counter = 1
    
    for page_num, data in simplified_graph.items():
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        
        if not nodes:
            continue
            
        G = build_nx_graph(data)
        
        # --- IDENTIFY START TERMINALS ---
        # Nodes with an in-degree of 0 have no incoming arrows.
        starts = [n for n, d in G.in_degree() if d == 0]
        if not starts:
            # Fallback check if there's a loop structure: search for nodes containing 'start' in text
            for node_id in G.nodes:
                node_data = G.nodes[node_id]
                text = str(node_data.get("text", "")).lower()
                type_ = str(node_data.get("type", "")).lower()
                if "start" in text or "start" in type_:
                    starts.append(node_id)
        if not starts and G.nodes:
            # Fallback to the first node in the list
            starts = [list(G.nodes.keys())[0]]
            
        # --- IDENTIFY SINK TERMINALS (END NODES) ---
        # Nodes with an out-degree of 0 have no outgoing arrows.
        sinks = [n for n, d in G.out_degree() if d == 0]
        if not sinks:
            sinks = list(G.nodes.keys())
            
        # --- PATH FINDING AND PARAGRAPH GENERATION ---
        for start in starts:
            for sink in sinks:
                if start == sink:
                    continue
                try:
                    # Find all unique non-looping routes from start to sink in Directed Graph
                    paths = list(nx.all_simple_paths(G, source=start, target=sink))
                    for path in paths:
                        paragraph_text = path_to_paragraph(path, G, page_num)
                        
                        # Construct a list representing each individual step in the decision path
                        decision_path_steps = []
                        for idx, node_id in enumerate(path):
                            node_data = G.nodes[node_id]
                            step = {
                                "node_id": node_id,
                                "text": node_data.get("text", "").strip(),
                                "type": node_data.get("type", "")
                            }
                            if idx < len(path) - 1:
                                next_id = path[idx + 1]
                                # Add the condition text (e.g. 'YES') on the arrow to the next step
                                step["transition"] = G.edges[node_id, next_id].get("condition", "")
                            decision_path_steps.append(step)
                            
                        # Save the generated paragraph and path metadata
                        generated_paragraphs.append({
                            "paragraph_id": f"p_{flowchart_id_to_str(page_num)}_{paragraph_id_counter}",
                            "manual_name": manual_name,
                            "flowchart_id": page_num,
                            "start_node": start,
                            "end_node": sink,
                            "decision_path": decision_path_steps,
                            "text": paragraph_text
                        })
                        paragraph_id_counter += 1
                except nx.NetworkXNoPath:
                    continue # Skip if there is no connected path between these two nodes
                except Exception as e:
                    print(f"Error traversing path from {start} to {sink} on page {page_num}: {e}")
                    
    return generated_paragraphs

def flowchart_id_to_str(page):
    # Formats page IDs safely for JSON key names
    return str(page).replace(" ", "_")

def generate_paragraphs_file(input_graph_path, output_filepath, manual_name="sample.pdf"):
    """
    LEARNER TIP:
    Reads the simplified graph from disk, generates paths, and writes the
    troubleshooting path paragraphs out to disk as a JSON file ('paragraphs.json').
    """
    if not os.path.exists(input_graph_path):
        raise FileNotFoundError(f"Simplified graph file not found at: {input_graph_path}")
        
    with open(input_graph_path, "r", encoding="utf-8") as f:
        simplified_graph = json.load(f)
        
    paragraphs = generate_paragraphs_from_graph(simplified_graph, manual_name)
    
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(paragraphs, f, indent=2)
        
    return paragraphs

