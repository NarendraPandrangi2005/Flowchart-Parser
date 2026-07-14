import os
import json
import urllib.request
import urllib.error

class GroqClient:
    """
    LEARNER TIP:
    This class handles sending request prompts to the Groq Cloud API.
    Instead of using heavy external HTTP libraries like `requests`, it uses Python's
    built-in `urllib` module which is lightweight and fast.
    """
    
    def __init__(self, api_key=None, model="llama-3.1-8b-instant"):
        # Retrieve the Groq API key from parameters, or search the OS environment variables
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "").strip()
        self.model = model
        # Groq uses an OpenAI-compatible endpoint URL for chat completions
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def get_system_instructions(self):
        """
        LEARNER TIP:
        This returns the 'system prompt'. A system prompt dictates the rules, personality, 
        and constraints of the LLM. Setting strict guidelines here prevents the model
        from hallucinating or using its pre-trained external knowledge.
        """
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

    def query(self, prompt):
        """
        LEARNER TIP:
        Sends the final formulated prompt to the Groq API and returns the generated text answer.
        This illustrates how to format standard HTTP POST requests with JSON payloads.
        """
        # Ensure we have an API key, otherwise the request will fail with an HTTP 401 Unauthorized error
        if not self.api_key:
            raise ValueError("Groq API Key is not set. Please set the GROQ_API_KEY environment variable or pass it to the constructor.")

        # HTTP Headers: Tell Groq how to authenticate the request and that we are sending JSON data
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "FlowchartRAG-Assistant/1.0"
        }
        
        # Construct the API payload dictionary containing model preferences and system/user prompts
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.get_system_instructions() # Rule definitions
                },
                {
                    "role": "user",
                    "content": prompt                          # Combined query + graph context
                }
            ],
            # Low temperature (0.1) makes the LLM highly deterministic and factual instead of creative
            "temperature": 0.1,
            "max_tokens": 512
        }
        
        # Serialize Python dict into JSON string and encode it to raw bytes for transmission
        payload = json.dumps(data).encode("utf-8")
        
        # Create an HTTP Request object specifying the target URL, headers, payload, and POST method
        req = urllib.request.Request(self.api_url, data=payload, headers=headers, method="POST")
        
        try:
            # Perform the request block with a 15-second timeout safeguard
            with urllib.request.urlopen(req, timeout=15) as response:
                # Read raw bytes, decode to UTF-8 string, and parse JSON string back into a Python dict
                res_data = json.loads(response.read().decode("utf-8"))
                # Extract the LLM text message from the standard chat-completion response structure
                return res_data["choices"][0]["message"]["content"].strip()
                
        except urllib.error.HTTPError as e:
            # If the server returned an error code (e.g. 400, 401, 429), read the error description
            error_msg = e.read().decode('utf-8')
            try:
                # Attempt to extract the clean error message from Groq's JSON response
                error_json = json.loads(error_msg)
                detail = error_json.get("error", {}).get("message", error_msg)
            except Exception:
                detail = error_msg
            raise RuntimeError(f"Groq API Error ({e.code}): {detail}")
            
        except Exception as e:
            # Handle general network errors (e.g., connection timed out, DNS lookup failure)
            raise RuntimeError(f"Failed to connect to Groq API: {e}")

