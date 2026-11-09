"""Testa Gemini no Vertex AI e uma chamada de ferramenta via ADK."""

import asyncio

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types


def saudacao(nome: str) -> dict:
    """Retorna uma saudação para a pessoa informada."""
    return {"mensagem": f"Olá, {nome}! Ferramenta executada."}


agent = Agent(
    name="hello_world",
    model="gemini-3.5-flash",
    instruction="Use a ferramenta saudacao para responder, sem inventar seu resultado.",
    tools=[saudacao],
)


async def main():
    runner = InMemoryRunner(agent=agent, app_name="validacao_hello")
    session = await runner.session_service.create_session(
        app_name="validacao_hello", user_id="teste"
    )
    tool_called = False
    tool_succeeded = False
    final_text = []
    async for event in runner.run_async(
        user_id="teste",
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part(text="Use a ferramenta para saudar Ana.")]
        ),
    ):
        for call in event.get_function_calls():
            tool_called |= call.name == "saudacao"
        for response in event.get_function_responses():
            tool_succeeded |= (
                response.name == "saudacao"
                and response.response.get("mensagem") == "Olá, Ana! Ferramenta executada."
            )
        if event.is_final_response() and event.content:
            final_text.extend(part.text for part in event.content.parts or [] if part.text)
    if not tool_called or not tool_succeeded or not final_text:
        raise RuntimeError("A chamada da ferramenta ou a resposta final não foi confirmada.")
    print("Ferramenta executada com sucesso. Resposta:", " ".join(final_text))


if __name__ == "__main__":
    asyncio.run(main())
