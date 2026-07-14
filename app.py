import os
import json
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from parser import parse_pdf

app = Flask(__name__)
CORS(app)  # Enable CORS for convenience

# Beautiful HTML dashboard template served at root endpoint
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flowchart Troubleshooting Assistant</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', sans-serif;
        }
        body {
            background: radial-gradient(circle at center, #1c183a 0%, #0d0a21 100%);
            color: #f3f4f6;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
        }
        .app-container {
            width: 92%;
            max-width: 1200px;
            height: 88vh;
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            display: flex;
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.55);
            overflow: hidden;
        }
        /* Sidebar Styles */
        .sidebar {
            width: 320px;
            background: rgba(10, 8, 22, 0.55);
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            padding: 30px 24px;
            display: flex;
            flex-direction: column;
            gap: 26px;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .brand-icon {
            width: 34px;
            height: 34px;
            background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            color: #0c091f;
            font-family: 'Outfit', sans-serif;
        }
        .brand-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.3rem;
            font-weight: 700;
            background: linear-gradient(135deg, #ffffff 0%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .sidebar-section {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .sidebar-section label {
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #9ca3af;
        }
        .styled-select, .styled-input {
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 12px;
            padding: 12px 16px;
            color: #f3f4f6;
            font-size: 0.9rem;
            outline: none;
            transition: all 0.3s ease;
        }
        .styled-select:focus, .styled-input:focus {
            border-color: #4facfe;
            box-shadow: 0 0 10px rgba(79, 172, 254, 0.2);
            background: rgba(255, 255, 255, 0.08);
        }
        .styled-select option {
            background: #0f0c1b;
            color: #f3f4f6;
        }
        .save-btn {
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            border: none;
            border-radius: 12px;
            color: white;
            padding: 12px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .save-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 18px rgba(99, 102, 241, 0.45);
        }
        /* Chat Area Styles */
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: rgba(10, 8, 22, 0.25);
        }
        .chat-header {
            padding: 24px 30px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .chat-title-container {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .chat-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.2rem;
            font-weight: 600;
            background: linear-gradient(135deg, #ffffff 0%, #e2e8f0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .chat-subtitle {
            font-size: 0.8rem;
            color: #9ca3af;
        }
        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.8rem;
            background: rgba(16, 185, 129, 0.1);
            color: #10b981;
            padding: 6px 12px;
            border-radius: 20px;
            border: 1px solid rgba(16, 185, 129, 0.2);
        }
        .status-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.6; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.6; }
        }
        .messages-container {
            flex: 1;
            padding: 30px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        /* Message Bubbles */
        .message {
            display: flex;
            max-width: 80%;
            animation: slideIn 0.3s ease forwards;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message.user {
            align-self: flex-end;
        }
        .message.assistant {
            align-self: flex-start;
        }
        .message-content {
            padding: 16px 20px;
            border-radius: 16px;
            font-size: 0.95rem;
            line-height: 1.5;
        }
        .user .message-content {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            color: white;
            border-bottom-right-radius: 4px;
            box-shadow: 0 4px 15px rgba(37, 99, 235, 0.25);
        }
        .assistant .message-content {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #e5e7eb;
            border-bottom-left-radius: 4px;
        }
        /* Suggestion Chips */
        .suggestions-container {
            padding: 0 30px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .suggestion-chip {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.8rem;
            color: #cbd5e1;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .suggestion-chip:hover {
            background: rgba(79, 172, 254, 0.1);
            border-color: #4facfe;
            color: #4facfe;
            transform: scale(1.02);
        }
        /* Input Area */
        .input-container {
            padding: 20px 30px 30px;
            display: flex;
            gap: 12px;
        }
        .input-bar {
            flex: 1;
            position: relative;
        }
        .chat-input {
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 16px 20px;
            color: white;
            font-size: 0.95rem;
            outline: none;
            transition: all 0.3s ease;
        }
        .chat-input:focus {
            border-color: #4facfe;
            box-shadow: 0 0 15px rgba(79, 172, 254, 0.15);
            background: rgba(255, 255, 255, 0.08);
        }
        .send-btn {
            background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
            border: none;
            border-radius: 16px;
            color: #0c091f;
            width: 54px;
            height: 54px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .send-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 18px rgba(0, 242, 254, 0.45);
        }
        .send-btn svg {
            width: 20px;
            height: 20px;
            fill: #0c091f;
        }
        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 6px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        /* Typing indicator dots */
        .typing-bubble {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 12px 16px;
        }
        .dot {
            width: 6px;
            height: 6px;
            background: #9ca3af;
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out both;
        }
        .dot:nth-child(1) { animation-delay: -0.32s; }
        .dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1.0); }
        }
        
        /* Markdown rendering styles */
        .assistant .message-content ul, .assistant .message-content ol {
            margin-left: 20px;
            margin-top: 8px;
            margin-bottom: 8px;
        }
        .assistant .message-content li {
            margin-bottom: 4px;
        }
        .assistant .message-content strong {
            color: #60a5fa;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="brand">
                <div class="brand-icon">F</div>
                <div class="brand-title">Flowchart Chat</div>
            </div>
            
            <div class="sidebar-section" style="margin-top: 15px;">
                <label>Active Mode</label>
                <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px; padding: 12px 16px; font-size: 0.9rem; color: #cbd5e1; display: flex; align-items: center; gap: 8px;">
                    <div style="width: 8px; height: 8px; background: #00f2fe; border-radius: 50%;"></div>
                    Global Search (All Pages)
                </div>
            </div>
            
            <div class="sidebar-section">
                <label for="api-key-input">Groq API Key</label>
                <input type="password" id="api-key-input" class="styled-input" placeholder="gsk_...">
                <button id="save-key-btn" class="save-btn">Save API Key</button>
            </div>
            
            <div style="margin-top: auto; font-size: 0.75rem; color: #6b7280; text-align: center;">
                Powered by PyMuPDF & Groq Llama 3.1
            </div>
        </div>
        
        <!-- Chat Area -->
        <div class="chat-area">
            <!-- Header -->
            <div class="chat-header">
                <div class="chat-title-container">
                    <div class="chat-title" id="active-flowchart-title">Global Troubleshooting Assistant</div>
                    <div class="chat-subtitle" id="active-flowchart-desc">Search and trace troubleshooting steps across all flowchart pages.</div>
                </div>
                <div class="status-badge">
                    <div class="status-dot"></div>
                    <span>Online</span>
                </div>
            </div>
            
            <!-- Messages -->
            <div class="messages-container" id="messages-list">
                <div class="message assistant">
                    <div class="message-content">
                        Hello! I am your AI Flowchart troubleshooting assistant.
                        <br><br>
                        Verify your Groq API Key, and enter your query or select one of the suggested prompts below. I will search across all flowchart pages to trace the corrective actions!
                    </div>
                </div>
            </div>
            
            <!-- Suggestions -->
            <div class="suggestions-container" id="suggestions-list">
                <!-- suggestions populated by JS -->
            </div>
            
            <!-- Input -->
            <div class="input-container">
                <div class="input-bar">
                    <input type="text" class="chat-input" id="user-chat-input" placeholder="Enter your query/issue...">
                </div>
                <button class="send-btn" id="send-chat-btn">
                    <svg viewBox="0 0 24 24">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"></path>
                    </svg>
                </button>
            </div>
        </div>
    </div>

    <script>
        const apiKeyInput = document.getElementById("api-key-input");
        const saveKeyBtn = document.getElementById("save-key-btn");
        const messagesList = document.getElementById("messages-list");
        const userChatInput = document.getElementById("user-chat-input");
        const sendChatBtn = document.getElementById("send-chat-btn");
        const activeFlowchartTitle = document.getElementById("active-flowchart-title");
        const activeFlowchartDesc = document.getElementById("active-flowchart-desc");
        const suggestionsList = document.getElementById("suggestions-list");

        // Load saved API key from localStorage
        const savedKey = localStorage.getItem("groq_api_key");
        if (savedKey) {
            apiKeyInput.value = savedKey;
        }

        saveKeyBtn.addEventListener("click", () => {
            const key = apiKeyInput.value.trim();
            if (key) {
                localStorage.setItem("groq_api_key", key);
                alert("API Key saved securely in your browser storage!");
            } else {
                localStorage.removeItem("groq_api_key");
                alert("API Key cleared.");
            }
        });

        // Quick Suggestion Prompts configuration for Global Search
        const SUGGESTIONS = [
            "Switch Circuit Breaker to ON [CB14]",
            "What if CB14 stays ON?",
            "Is the Service Light flashing?",
            "Device Ready LED is flashing red",
            "Is the encoder cable damaged?",
            "Trigger photoeye green light is off"
        ];

        function updateSuggestions() {
            suggestionsList.innerHTML = "";
            SUGGESTIONS.forEach(p => {
                const chip = document.createElement("div");
                chip.className = "suggestion-chip";
                chip.textContent = p;
                chip.addEventListener("click", () => {
                    userChatInput.value = p;
                    userChatInput.focus();
                });
                suggestionsList.appendChild(chip);
            });
        }

        // Initialize suggestions
        updateSuggestions();

        // Format Markdown Simple Parser
        function formatMarkdown(text) {
            // Escape HTML characters
            let formatted = text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
                
            // Replace bold **text**
            formatted = formatted.replace(/\\*\\*(.*?)\\*\\*/g, "<strong>$1</strong>");
            
            // Replace bullet list items (handle both - and *)
            formatted = formatted.replace(/^-\\s+(.*?)$/gm, "<li>$1</li>");
            formatted = formatted.replace(/^\\*\\s+(.*?)$/gm, "<li>$1</li>");
            
            // Wrap bullet lists
            formatted = formatted.replace(/(<li>.*?<\\/li>)/s, "<ul>$1</ul>");
            
            // Replace newlines
            formatted = formatted.replace(/\\n/g, "<br>");
            return formatted;
        }

        function appendMessage(sender, content, isHtml = false) {
            const msgDiv = document.createElement("div");
            msgDiv.className = `message ${sender}`;
            
            const contentDiv = document.createElement("div");
            contentDiv.className = "message-content";
            
            if (isHtml) {
                contentDiv.innerHTML = content;
            } else {
                contentDiv.textContent = content;
            }
            
            msgDiv.appendChild(contentDiv);
            messagesList.appendChild(msgDiv);
            messagesList.scrollTop = messagesList.scrollHeight;
            return msgDiv;
        }

        function showTypingIndicator() {
            const typingDiv = document.createElement("div");
            typingDiv.className = "message assistant typing-placeholder";
            
            const contentDiv = document.createElement("div");
            contentDiv.className = "message-content typing-bubble";
            contentDiv.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
            
            typingDiv.appendChild(contentDiv);
            messagesList.appendChild(typingDiv);
            messagesList.scrollTop = messagesList.scrollHeight;
            return typingDiv;
        }

        async function sendChat() {
            const message = userChatInput.value.trim();
            const apiKey = apiKeyInput.value.trim();
            
            if (!message) return;
            
            if (!apiKey) {
                alert("Please enter and save your Groq API Key in the sidebar first!");
                return;
            }
            
            // Append User message
            appendMessage("user", message);
            userChatInput.value = "";
            
            // Show Typing indicator
            const typingIndicator = showTypingIndicator();
            
            try {
                const response = await fetch("/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        message: message,
                        page: null, // Always search globally
                        api_key: apiKey
                    })
                });
                
                // Remove Typing indicator
                typingIndicator.remove();
                
                const data = await response.json();
                if (data.success) {
                    const reply = formatMarkdown(data.response);
                    appendMessage("assistant", reply, true);
                } else {
                    appendMessage("assistant", `Error: ${data.error || "Failed to query the AI assistant."}`);
                }
            } catch (error) {
                typingIndicator.remove();
                appendMessage("assistant", `Connection error: Failed to communicate with the server.`);
            }
        }

        sendChatBtn.addEventListener("click", sendChat);
        userChatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                sendChat();
            }
        });
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index_endpoint():
    """Serves the Chatbot HTML dashboard interface."""
    return render_template_string(HTML_TEMPLATE)

@app.route("/chat", methods=["POST"])
def chat_endpoint():
    """
    Handles chatbot natural language troubleshooting requests using a modular flowchart RAG pipeline.
    Expects JSON body: { "message": "...", "page": "1", "api_key": "..." }
    """
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    page_num = str(data.get("page", "1")).strip()
    api_key = data.get("api_key", "").strip()
    
    if not message:
        return jsonify({"success": False, "error": "Message content is required."}), 400
    if not api_key:
        return jsonify({"success": False, "error": "Groq API Key is required."}), 400
        
    # Check if vector database exists, if not generate it
    graph_path = "decision_graph.json"
    simplified_graph_path = "simplified_decision_graph.json"
    paragraphs_path = "paragraphs.json"
    
    if not os.path.exists(graph_path) or not os.path.exists(simplified_graph_path) or not os.path.exists(paragraphs_path):
        try:
            print("Decision graph or paragraphs file missing, running parse_pdf...")
            parse_pdf("data/sample.pdf")
        except Exception as e:
            return jsonify({"success": False, "error": f"Failed to auto-generate decision graph & vector store: {e}"}), 500
            
    # Process query through flowchart-aware retrieval service
    try:
        from services.vector_store import VectorStoreManager
        from services.query_processor import process_query_pipeline
        from services.groq_client import GroqClient
        
        vector_store = VectorStoreManager()
        
        # Run query processor pipeline (combines semantic search + graph node priority matching)
        processed = process_query_pipeline(
            query_text=message,
            graph_path=simplified_graph_path,
            paragraphs_path=paragraphs_path,
            vector_store=vector_store,
            flowchart_id=None,  # Always search globally across all pages
            n_results=3
        )
        
        prompt = processed["prompt"]
        citations = processed["citations"]
        
        # Log matching info to server terminal
        if processed.get("graph_prioritized"):
            print(f"Graph prioritisation activated for query. Matched nodes: {processed.get('referenced_nodes')}")
        else:
            print("Semantic similarity fallback activated for query.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to retrieve context/process query: {e}"}), 500
        
    # Request completion from Groq API service
    try:
        groq_client = GroqClient(api_key=api_key)
        content = groq_client.query(prompt)
        full_response = content + citations
        return jsonify({"success": True, "response": full_response})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/process", methods=["GET", "POST"])
def process_endpoint():
    """
    Flask route to process a PDF.
    Supports both GET and POST requests.
    Expects 'pdf_path' query parameter or JSON body with 'pdf_path'.
    Defaults to 'sample.pdf' if not specified.
    """
    pdf_path = None
    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
            pdf_path = data.get("pdf_path")
        else:
            pdf_path = request.form.get("pdf_path")
            
    if not pdf_path:
        pdf_path = request.args.get("pdf_path", "data/sample.pdf")
        
    print(f"\n--- API Request received to process: {pdf_path} ---")
    
    if not os.path.exists(pdf_path):
        error_msg = f"PDF file not found at: {os.path.abspath(pdf_path)}"
        print(f"Error: {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 404
        
    try:
        text_data, shapes_data = parse_pdf(pdf_path)
        
        if text_data is None or shapes_data is None:
            return jsonify({"success": False, "error": "Parsing failed. Inspect terminal logs."}), 500
            
        total_pages = len(text_data)
        summary = {}
        for page, page_text in text_data.items():
            text_blocks_count = len(page_text.get("blocks", []))
            page_shapes = shapes_data.get(page, {})
            if isinstance(page_shapes, dict):
                shapes_count = len(page_shapes.get("all_drawings", []))
            else:
                shapes_count = len(page_shapes)
            summary[page] = {
                "text_blocks": text_blocks_count,
                "shapes_paths": shapes_count
            }
            
        print("API processing complete. Returning JSON response.")
        
        return jsonify({
            "success": True,
            "pdf_path": os.path.abspath(pdf_path),
            "total_pages": total_pages,
            "page_summary": summary,
            "data": {
                "text": text_data,
                "shapes": shapes_data
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/status", methods=["GET"])
def status_endpoint():
    """Simple status check route."""
    return jsonify({
        "status": "online",
        "message": "Flask PyMuPDF Parser Service running."
    })

if __name__ == "__main__":
    # Start the server on port 5000
    print("Starting Flask PyMuPDF Parser app on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
