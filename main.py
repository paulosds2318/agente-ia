import os
import sys

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
modelo = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
if not api_key:
    sys.exit("Configure GEMINI_API_KEY no arquivo .env antes de iniciar.")

client = genai.Client(api_key=api_key)

chat = client.chats.create(
    model=modelo
)

print("Agente iniciado!")
print("Digite 'sair' para encerrar.\n")

while True:
    try:
        mensagem = input("Você: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAgente: Até mais!")
        break

    if mensagem.lower() == "sair":
        print("Agente: Até mais!")
        break

    if not mensagem:
        continue

    try:
        resposta = chat.send_message(mensagem)
        print(f"Agente: {resposta.text}\n")
    except Exception as erro:
        print(f"Agente: não foi possível responder ({type(erro).__name__}).\n")
