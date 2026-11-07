from google.adk.agents import Agent

root_agent = Agent(
    name="sabor_da_terra",
    model="gemini-2.5-flash",
    instruction="Responda em português.",
)
