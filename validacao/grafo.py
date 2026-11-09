"""Verifica o fan-out e o JoinNode sem acessar um modelo externo."""

import asyncio

from google.adk import Event, Workflow
from google.adk.runners import InMemoryRunner
from google.adk.workflow import JoinNode
from google.genai import types


def triagem():
    return Event(output="triagem concluída")


def documentos():
    return Event(output="consulta concluída")


def conferir(node_input: dict):
    esperado = {"triagem": "triagem concluída", "documentos": "consulta concluída"}
    if node_input != esperado:
        raise ValueError(f"Resultados inesperados: {node_input!r}")
    return Event(output="OK: as duas ramificações chegaram ao JoinNode")


join = JoinNode(name="reunir")
workflow = Workflow(
    name="validacao_grafo",
    edges=[
        ("START", triagem, join),
        ("START", documentos, join),
        (join, conferir),
    ],
)


async def main():
    runner = InMemoryRunner(agent=workflow, app_name="validacao_grafo")
    session = await runner.session_service.create_session(
        app_name="validacao_grafo", user_id="teste"
    )
    outputs = []
    async for event in runner.run_async(
        user_id="teste",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="iniciar")]),
    ):
        if event.output is not None:
            outputs.append(event.output)
    expected = "OK: as duas ramificações chegaram ao JoinNode"
    if expected not in outputs:
        raise RuntimeError(f"Fluxo não concluiu: {outputs!r}")
    print(expected)


if __name__ == "__main__":
    asyncio.run(main())
