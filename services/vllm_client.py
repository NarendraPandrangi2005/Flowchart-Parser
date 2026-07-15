import os
import re
import openai

def sanitize_mermaid_code(text):
    """
    Finds all ```mermaid ... ``` code blocks in the text and ensures they start with a valid
    Mermaid declaration (like 'flowchart TD' or 'graph TD'). If not, prepends 'flowchart TD'.
    """
    def replace_block(match):
        code = match.group(1)
        trimmed = code.strip()
        valid_keywords = ("flowchart", "graph", "sequencediagram", "statediagram", "classdiagram", "erdiagram", "gantt", "pie", "gitgraph", "journey")
        first_word = trimmed.split()[0].lower() if trimmed.split() else ""
        # Check if first word starts with any of the valid keywords
        starts_with_valid = any(first_word.startswith(kw) for kw in valid_keywords)
        if not starts_with_valid:
            return f"```mermaid\nflowchart TD\n    {trimmed}\n```"
        return match.group(0)

    # Match blocks starting with ```mermaid and ending with ```
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
            "6. CRITICAL MERMAID SYNTAX RULE: If any node label or transition/edge label contains special characters "
            "(especially '<', '>', parentheses '()', brackets '[]', or quotes), you MUST wrap the label text in double quotes. "
            "For example, write: A[\"Check Speed (10.66.225.88:8080)\"] or B{\"Is Speed < 30%?\"} or B -->|\"< 30%\"| C. "
            "Never leave '<' or '>' unquoted inside node/edge labels as it breaks the parser."
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
