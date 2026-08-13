from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

chat = client.chats.create(
    model="gemini-3.6-flash"
)

print("Agente iniciado!")
print("Digite 'sair' para encerrar.\n")

while True:
    mensagem = input("Você: ")

    if mensagem.lower() == "sair":
        print("Agente: Até mais!")
        break

    resposta = chat.send_message(mensagem)

    print(f"Agente: {resposta.text}\n")
