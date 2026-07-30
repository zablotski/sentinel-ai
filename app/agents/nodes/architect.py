from langchain_openai import ChatOpenAI
from app.agents.state import AgentState

llm = ChatOpenAI(base_url="http://localhost:11434/v1", api_key="ollama", model="llama3.1:8b")

async def architect_node(state: AgentState):
    print("--- ARCHITECT: FINALIZING ---")
    issues = state["analyzed_dependencies"]
    
    for issue in issues:
        if "license_text" in issue:
            del issue["license_text"]
            
        if issue['verdict'] == "FORBIDDEN":
            issue['risk_score'] = 100
            prompt = f"Suggest one safe NPM alternative for {issue['package_name']}."
            res = await llm.ainvoke(prompt)
            issue['reasoning'] += f"\nRECO: {res.content}"
        else:
            issue['risk_score'] = 0

    return {"analyzed_dependencies": issues, "current_step": "architect"}
