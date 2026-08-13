from google import genai


class AIConfigurationError(RuntimeError):
    pass


def send_message(settings, prompt):
    if not settings.gemini_api_key:
        raise AIConfigurationError("GEMINI_API_KEY não foi configurada.")
    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.chats.create(model=settings.gemini_model).send_message(prompt)
    if not response.text:
        raise RuntimeError("A IA retornou uma resposta vazia.")
    return response.text
