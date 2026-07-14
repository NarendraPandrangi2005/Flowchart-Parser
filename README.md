# 📊 Flowchart PDF Parser & AI-Assisted RAG Troubleshooter

A lightweight, high-performance Python application designed to extract flowchart diagrams from PDF manuals using **PyMuPDF**, reconstruct their logical connections (nodes and edges), and power an interactive AI troubleshooting chatbot using **Retrieval-Augmented Generation (RAG)**.

---

## 🏗️ Project Architecture

The application is structured in three logical pipeline layers:
1. **Extraction Layer**: PyMuPDF parses the PDF, groups drawing shapes (rectangles, diamonds, ovals), extracts text, and links arrowheads to shapes to build the raw topology graph (`parser.py`).
2. **Graph & Embedding Layer**: Simplifies the topology graph, extracts sequential troubleshooting paths as paragraphs, chunks them, generates embeddings, and indexes them in ChromaDB.
3. **RAG & Query Layer**: Receives user questions, runs a hybrid search (direct component match + vector search), builds a strict LLM system prompt, and retrieves answers via the Groq API.


---

## 📂 Core Folder Structure

Here is what each file in the workspace does:

### 📄 Main Entry Point & Dashboards
* **[parser.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/parser.py)**: The main parsing script. It reads the raw PDF document, extracts visual paths and text, reconstructs the graph, and triggers the database indexing.
* **[app.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/app.py)**: Launches a Flask server and serves the Web Dashboard chat interface at `http://127.0.0.1:5000/`.
* **[query_engine.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/query_engine.py)**: Interactive command-line (CLI) wizard to step through the flowchart paths manually (Yes/No choices) in your terminal.
* **[groq_query.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/groq_query.py)**: Standard CLI command line tool to ask troubleshooting questions using the Groq AI service.

### 📁 Modular Services (`services/`)
* **[services/graph_simplifier.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/services/graph_simplifier.py)**: Removes noisy coordinate details from the raw extraction, keeping only logical node items.
* **[services/paragraph_generator.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/services/paragraph_generator.py)**: Traverses flowchart branches (`NetworkX`) to generate descriptive troubleshooting text paragraphs.
* **[services/semantic_chunker.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/services/semantic_chunker.py)**: Splits path paragraphs into context blocks using sentence similarity, with a recursive size fallback.
* **[services/vector_store.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/services/vector_store.py)**: Manages storing and retrieving text embeddings inside the local database.
* **[services/query_processor.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/services/query_processor.py)**: Directs the RAG pipeline, checking for exact components (e.g. `[CB1]`) and executing fallback search logic if Windows blocks your local SciPy DLL files.
* **[services/groq_client.py](file:///c:/Users/ARN%20SOFT/Desktop/Flowchart1/services/groq_client.py)**: Standard HTTP client to query the Groq LLM inference service.

---

## ⚡ Setup & Installation

### 1. Install Dependencies
Run this command in your command prompt to install all required packages:
```bash
pip install -r requirements.txt
```

### 2. Set Up Your API Key
For the AI chat dashboard, set your Groq API Key as an environment variable or type it directly into the web sidebar:
* **Windows CMD**: `set GROQ_API_KEY=your_api_key_here`
* **Windows PowerShell**: `$env:GROQ_API_KEY="your_api_key_here"`

---

## 🚀 How to Run the Project

### A. Run the Interactive Web Chat Interface (Recommended)
Launch the Flask backend server:
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000/`.

### B. Run the Manual Step-by-Step Path CLI
Walk through the flowchart paths using interactive terminal menus:
```bash
python query_engine.py
```

### C. Run the AI RAG CLI Troubleshooter
Ask natural language questions directly in the console:
```bash
python groq_query.py
```

### D. Re-Parse a Custom PDF
If you update `data/sample.pdf` or want to process a new flowchart manual:
```bash
python parser.py
```
This automatically updates `decision_graph.json` and updates the ChromaDB vector database index.