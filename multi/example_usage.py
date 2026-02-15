import json
from .manager import MemoryMultiManager
from .adapters import OpenAIAdapter, AnthropicAdapter, GoogleAdapter, OllamaAdapter
try:
    from .frameworks import get_langchain_tools, get_crewai_tools
except ImportError:
    get_langchain_tools = None
    get_crewai_tools = None

# 1. Инициализация (Core memory может быть моком для теста)
class MockCore:
    def record_decision(self, **kwargs):
        print(f"   [Core] Recording decision: {kwargs.get('title')}")
        return type('obj', (object,), {'id': 'DEC-123'})()

    def supersede_decision(self, **kwargs):
        print(f"   [Core] Superseding: {kwargs.get('old_decision_ids')}")
        return True

core = MockCore()
manager = MemoryMultiManager(core)

print("=== 1. OpenAI Adapter ===")
openai_adapter = OpenAIAdapter(manager)
openai_tools = openai_adapter.get_tool_definitions()
print(f"Tools for OpenAI: {len(openai_tools)} tools generated.")
# Имитация входящего вызова
mock_tool_call = type('obj', (object,), {
    'id': 'call_abc',
    'function': type('obj', (object,), {
        'name': 'record_decision',
        'arguments': json.dumps({"title": "Use FastAPI", "target": "backend", "rationale": "High performance"})
    })
})()
openai_res = openai_adapter.process_tool_calls([mock_tool_call])
print(f"OpenAI Response: {openai_res[0]['content']}\n")


print("=== 2. Anthropic Adapter ===")
anthropic_adapter = AnthropicAdapter(manager)
anthropic_tools = anthropic_adapter.get_tool_definitions()
print(f"Tools for Anthropic: {len(anthropic_tools)} tools generated.")
# Имитация входящего блока
mock_block = type('obj', (object,), {
    'type': 'tool_use',
    'id': 'toolu_123',
    'name': 'supersede_decision',
    'input': {"title": "Use SQLite", "target": "db", "rationale": "Simplicity", "old_decision_ids": ["DEC-001"]}
})()
anthropic_res = anthropic_adapter.process_tool_use([mock_block])
print(f"Anthropic Response: {anthropic_res[0]['content']}\n")


print("=== 3. Google Adapter ===")
google_adapter = GoogleAdapter(manager)
google_tools = google_adapter.get_tool_definitions()
print(f"Tools for Gemini: {len(google_tools['function_declarations'])} declarations.")
# Имитация входящего function_call
mock_part = type('obj', (object,), {
    'function_call': type('obj', (object,), {
        'name': 'record_decision',
        'args': {"title": "Add Auth", "target": "security", "rationale": "Security first"}
    })
})()
google_res = google_adapter.process_function_calls(mock_part)
print(f"Google Response: {google_res[0]['function_response']['response']}\n")


print("=== 4. Ollama Adapter ===")
ollama_adapter = OllamaAdapter(manager)
# Имитация ответа Ollama
mock_ollama_msg = {
    "role": "assistant",
    "tool_calls": [{
        "function": {
            "name": "record_decision",
            "arguments": {"title": "Ollama Rule", "target": "local_llm", "rationale": "Privacy"}
        }
    }]
}
ollama_res = ollama_adapter.process_tool_calls(mock_ollama_msg)
print(f"Ollama Response: {ollama_res[0]['content']}\n")


print("=== 5. CrewAI Integration ===")
try:
    if get_crewai_tools is None:
        raise Exception("CrewAI tools not available")
    crew_tools = get_crewai_tools(manager)
    print(f"CrewAI tools: {[t.name for t in crew_tools]}")
    print(f"Example run: {crew_tools[0].run(title='Crew Decision', target='team', rationale='efficiency')}\n")
except Exception as e:
    print(f"CrewAI Demo skipped: {e}\n")


print("=== 6. LangChain Integration ===")
try:
    if get_langchain_tools is None:
        raise Exception("LangChain tools not available")
    lc_tools = get_langchain_tools(manager)
    print(f"LangChain tools: {[t.name for t in lc_tools]}")
    print(f"Example run: {lc_tools[0].run({'title': 'Test LC', 'target': 'dev', 'rationale': 'test'})}")
except Exception as e:
    print(f"LangChain Demo skipped: {e}")
