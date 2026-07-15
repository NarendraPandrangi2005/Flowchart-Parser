import os
import openai

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
            "Strict Guidelines:\n"
            "1. Answer ONLY using the retrieved troubleshooting context. Do not use outside knowledge.\n"
            "2. Follow the exact logical sequence defined in the decision graph context. Do not skip or jump steps.\n"
            "3. Do NOT invent or assume steps that are not explicitly present in the retrieved graph context.\n"
            "4. Match conditions (Yes/No, ON/OFF, Green/Red Light, etc.) precisely based on the user's state. "
            "Identify the user's current condition and clearly state the immediate next step or corrective action.\n"
            "5. Keep your response professional, precise, and concise (maximum 3 to 4 sentences)."
        )

    def query(self, prompt, system_instruction=None, temperature=None, max_tokens=None):
        if system_instruction is None:
            system_instruction = self.get_system_instructions()
        if temperature is None:
            temperature = self.temperature
        if max_tokens is None:
            max_tokens = 512  # For answers, 512 tokens is a good concise limit

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
                return response.choices[0].message.content.strip()
            raise RuntimeError("vLLM response choices empty")
        except Exception as e:
            raise RuntimeError(f"vLLM Query Error: {e}")
