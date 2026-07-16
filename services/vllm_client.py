import os
import re
import openai

def sanitize_mermaid_code(text):
    """
    Finds all ```mermaid ... ``` code blocks in the text and ensures they start with a valid
    Mermaid declaration (like 'flowchart TD' or 'graph TD'). If not, prepends 'flowchart TD'.
    Also sanitizes individual flowchart lines to guarantee valid syntax.
    """
    def sanitize_node_id(node_id):
        cleaned = node_id.strip()
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', cleaned)
        cleaned = re.sub(r'_+', '_', cleaned)
        cleaned = cleaned.strip('_')
        return cleaned

    def sanitize_label(label):
        label = label.strip()
        if not label:
            return '""'
        # Check if already quoted
        if len(label) >= 2 and label[0] == '"' and label[-1] == '"':
            label = label[1:-1]
        label = label.replace('\\"', '"')
        label = label.replace('"', '\\"')
        return f'"{label}"'

    def sanitize_mermaid_line(line):
        indent_match = re.match(r'^(\s*)', line)
        indent = indent_match.group(1) if indent_match else ''
        content = line.strip()
        if not content:
            return line
            
        if content.lower().startswith(('flowchart', 'graph', '%%', 'subgraph', 'end', 'style', 'classdef', 'class', 'click', 'linkstyle')):
            return line
            
        # Pre-process "-- label -->" to "-->|label|"
        content = re.sub(r'\s*--\s*(.*?)\s*-->\s*', r' -->|\1| ', content)
        
        connector_pattern = r'(\s*(?:==>|-->|-.->|--x|-x|--o|-o|---)\s*(?:\|[^\|]*\|)?\s*)'
        parts = re.split(connector_pattern, content)
        
        sanitized_parts = []
        for idx, part in enumerate(parts):
            if idx % 2 == 0:
                part_str = part.strip()
                if not part_str:
                    sanitized_parts.append("")
                    continue
                    
                node_match = re.match(r'^([^\{\[\(\>]+)([\{\[\(\>]+)(.*)([\}\]\)]+)$', part_str)
                if node_match:
                    node_id = node_match.group(1)
                    opening = node_match.group(2)
                    label = node_match.group(3)
                    closing = node_match.group(4)
                    
                    sanitized_id = sanitize_node_id(node_id)
                    sanitized_label = sanitize_label(label)
                    sanitized_parts.append(f"{sanitized_id}{opening}{sanitized_label}{closing}")
                else:
                    sanitized_parts.append(sanitize_node_id(part_str))
            else:
                connector = part
                label_match = re.search(r'\|([^\|]+)\|', connector)
                if label_match:
                    label_text = label_match.group(1)
                    sanitized_lbl = sanitize_label(label_text)
                    arrow_type = re.search(r'(==>|-->|-.->|--x|-x|--o|-o|---)', connector).group(1)
                    connector = f" {arrow_type}|{sanitized_lbl}| "
                sanitized_parts.append(connector)
                
        return indent + "".join(sanitized_parts)

    def replace_block(match):
        code = match.group(1)
        lines = code.split("\n")
        
        # Check if first word is valid mermaid keyword
        trimmed_lines = [line.strip() for line in lines if line.strip()]
        first_line = trimmed_lines[0] if trimmed_lines else ""
        first_word = first_line.split()[0].lower() if first_line.split() else ""
        
        valid_keywords = ("flowchart", "graph", "sequencediagram", "statediagram", "classdiagram", "erdiagram", "gantt", "pie", "gitgraph", "journey")
        starts_with_valid = any(first_word.startswith(kw) for kw in valid_keywords)
        is_flowchart = (not starts_with_valid) or first_word.startswith(('flowchart', 'graph'))
        
        sanitized_lines = []
        for line in lines:
            if is_flowchart:
                sanitized_lines.append(sanitize_mermaid_line(line))
            else:
                sanitized_lines.append(line)
            
        if not starts_with_valid:
            # Insert flowchart TD at the start
            return f"```mermaid\nflowchart TD\n" + "\n".join(sanitized_lines) + "\n```"
            
        return f"```mermaid\n" + "\n".join(sanitized_lines) + "\n```"

    pattern = r"```mermaid\s*\n(.*?)\n\s*```"
    return re.sub(pattern, replace_block, text, flags=re.DOTALL | re.IGNORECASE)

class VllmClient:
    """
    Client for interacting with local vLLM server using OpenAI-compatible API.
    """
    def __init__(self, api_url=None, model=None):
        # Match user's environment configuration
        self.api_url = api_url or os.environ.get("VLLM_SERVER_URL", "http://localhost:8000/v1")
        if self.api_url == "EMPTY" or not self.api_url:
            self.api_url = "http://localhost:8000/v1"
            
        self.model = model or os.environ.get("MODEL_NAME", "Qwen/Qwen3-30B-A3B-GPTQ-Int4")
        self.temperature = float(os.environ.get("MODEL_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.environ.get("MODEL_MAX_TOKENS", "20000"))
        
        self.client = openai.OpenAI(
            api_key="EMPTY",
            base_url=self.api_url
        )

    def get_system_instructions(self):
        return (
            "You are an expert troubleshooting assistant. You are given natural language troubleshooting steps "
            "retrieved from a flowchart decision graph. The user is asking a troubleshooting question or describing an issue.\n\n"
            "Your output must consist of two sections:\n"
            "1. A Mermaid flowchart diagram representing the decision paths matching the user's query/issue. "
            "Start the flowchart with a 'flowchart TD' statement. Format it inside a ```mermaid code block. "
            "Use clean node names and appropriate shapes (e.g., rectangles for action steps, diamonds for decision/question/conditions, "
            "rounded rectangles for start/end terminals). Make sure to label the transition paths/edges with the conditions (like Yes, No, Red, Green).\n"
            "2. A bulleted list (using '-' for bullets) of the step-by-step troubleshooting actions in the correct logical order.\n\n"
            "Strict Guidelines:\n"
            "1. Answer ONLY using the retrieved troubleshooting context. Do not use outside knowledge.\n"
            "2. Follow the exact logical sequence defined in the decision graph context. Do not skip or jump steps.\n"
            "3. Do NOT invent or assume steps that are not explicitly present in the retrieved graph context.\n"
            "4. Match conditions (Yes/No, ON/OFF, Green/Red Light, etc.) precisely based on the user's state.\n"
            "5. Keep your response professional, precise, and structured exactly as described.\n"
            "6. CRITICAL MERMAID SYNTAX RULES:\n"
            "   - Node IDs must be single-word alphanumeric names with no spaces or special characters (e.g., use 'start_node' or 'node_1', NEVER 'start node' or 'node-1').\n"
            "   - ALWAYS wrap ALL node labels and transition/edge labels in double quotes. For example: node_1[\"Start Action\"] or node_2{\"Is Voltage < 220V?\"} or node_1 -->|\"Yes\"| node_2.\n"
            "   - Never leave '<', '>', '(', ')', '[', ']', or other special characters unquoted inside node or edge labels."
        )

    def query(self, prompt, system_instruction=None, temperature=None, max_tokens=None):
        if system_instruction is None:
            system_instruction = self.get_system_instructions()
        if temperature is None:
            temperature = self.temperature
        if max_tokens is None:
            max_tokens = 2048  # Allow enough tokens for Mermaid + bullets output

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            if response and response.choices:
                raw_content = response.choices[0].message.content.strip()
                return sanitize_mermaid_code(raw_content)
            raise RuntimeError("vLLM response choices empty")
        except Exception as e:
            raise RuntimeError(f"vLLM Query Error: {e}")
