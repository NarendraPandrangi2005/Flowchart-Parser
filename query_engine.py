import json
import os

def load_graph():
    """
    LEARNER TIP:
    Reads and loads the simplified decision graph nodes and edges from the JSON file.
    Alerts the user to run the parsing pipeline first if it is missing.
    """
    graph_path = "simplified_decision_graph.json"
    if not os.path.exists(graph_path):
        print(f"Error: {graph_path} not found. Run parser.py first to generate it.")
        return None
    with open(graph_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_query_engine():
    """
    LEARNER TIP:
    Interactive CLI troubleshooter.
    Unlike groq_query.py which uses an AI LLM, this engine uses standard graph traversal:
      1. Starts at the 'Start' terminal node of the selected page.
      2. If a node has exactly one outgoing arrow, it automatically proceeds to the next step.
      3. If a node has multiple outgoing arrows (a Decision Box), it displays the conditions
         (e.g., [YES] or [NO]) and lets you choose which branch to follow.
      4. Repeats until it hits a leaf node (with no outgoing connections), then summarizes your path.
    """
    graph = load_graph()
    if not graph:
        return

    print("\n=======================================================")
    print("   WELCOME TO THE FLOWCHART TROUBLESHOOTING QUERY ENGINE")
    print("   (LOGICAL SIMPLIFIED GRAPH PATH TRACER)")
    print("=======================================================\n")

    # --- 1. DISPLAY AVAILABLE FLOWCHARTS ---
    print("Available Flowcharts in Document:")
    # Retrieve and sort pages numerically
    pages_list = sorted(list(graph.keys()), key=int)
    for idx, page in enumerate(pages_list):
        nodes = graph[page]["nodes"]
        title_tag = f"Page {page} Flowchart"
        if nodes:
            # Display page title alongside its starting text node
            title_tag = f"Page {page} Flowchart (Starts with: {nodes[0]['text'][:40]}...)"
        print(f"  {idx + 1}. {title_tag}")

    choice = input("\nSelect a flowchart number to query: ").strip()
    try:
        page_idx = int(choice) - 1
        page_num = pages_list[page_idx]
    except:
        print("Invalid selection. Exiting.")
        return

    page_data = graph[page_num]
    nodes = page_data["nodes"]
    edges = page_data["edges"]

    if not nodes:
        print("No nodes found for this flowchart. Exiting.")
        return

    # --- 2. LOCATE STARTING TERMINAL ---
    start_node = None
    for n in nodes:
        # Search for node of type 'Start/End' whose text is exactly 'Start'
        if n["type"] == "Start/End" and n["text"].lower() == "start":
            start_node = n
            break
    if not start_node:
        # Fallback: if no node has 'Start' text, begin at the first node in the list
        start_node = nodes[0]

    current_node = start_node

    print("\n-------------------------------------------------------")
    print(f"Starting Troubleshooting Path: {current_node['text']}")
    print("-------------------------------------------------------")

    # List to log the path history as the user navigates
    path_history = [current_node["text"]]

    # --- 3. TRAVERSAL LOOP ---
    while True:
        # Filter all outgoing connections where the current node is the source
        outgoing = [e for e in edges if e["source"] == current_node["id"]]

        if not outgoing:
            # If no outgoing arrows, we reached the end of the troubleshooting path
            print(f"\n[END OF PATH - ACTION REQUIRED]: {current_node['text']}")
            break

        if len(outgoing) == 1:
            # Automatic routing: if there is only one outgoing connection, proceed instantly
            edge = outgoing[0]
            next_node_id = edge["destination"]
            # Locate the next node object from our node list
            next_node = next(n for n in nodes if n["id"] == next_node_id)
            print(f"\n---> {next_node['text']}")
            current_node = next_node
            path_history.append(current_node["text"])
        else:
            # Manual branching routing (Decision Box)
            print(f"\nDecision Required at: '{current_node['text']}'")
            print("Options:")
            for o_idx, edge in enumerate(outgoing):
                # Fetch target node for each alternative choice
                target_node = next(n for n in nodes if n["id"] == edge["destination"])
                cond = edge["condition"] if edge["condition"] else "Proceed"
                print(f"  {o_idx + 1}. Choice: [{cond}] -> points to: '{target_node['text'][:65]}...'")

            opt_choice = input("Enter choice number: ").strip()
            try:
                opt_idx = int(opt_choice) - 1
                selected_edge = outgoing[opt_idx]
                next_node_id = selected_edge["destination"]
                # Move state to the selected destination node
                next_node = next(n for n in nodes if n["id"] == next_node_id)
                print(f"\nSelected branch: [{selected_edge['condition']}]")
                print(f"---> {next_node['text']}")
                current_node = next_node
                path_history.append(current_node["text"])
            except:
                print("Invalid input. Please choose a valid option number.")

    # --- 4. DISPLAY PATH SUMMARY ---
    print("\n-------------------------------------------------------")
    print("Summary of Traced Troubleshooting Path:")
    for idx, step in enumerate(path_history):
        print(f"  Step {idx + 1}: {step}")
    print("-------------------------------------------------------\n")

if __name__ == "__main__":
    run_query_engine()

