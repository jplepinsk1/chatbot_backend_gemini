import os
from dotenv import load_dotenv

load_dotenv()

# Configurações do Servidor Flask
SECRET_KEY = "ch@tb0t"
TIMEOUT_INATIVIDADE = 600  # 10 minutos em segundos

# Configurações do Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.5-flash"

SYSTEM_INSTRUCTION = """
Você é um assistente virtual amigável e prestativo. Sua função é responder a perguntas dos usuários e fornecer informações úteis.
Tente manter as respostas curtas, concisas, objetivas e claras. 
Se não souber a resposta, diga que não sabe e sugira que o usuário procure em outro lugar.
"""