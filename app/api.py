from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.agent import SupplyChainSQLAgent, AgentResponse
from app.tools import inspect_schema_tool, detect_delivery_delay_anomalies_tool

app = FastAPI(
    title="SupplyChain-SQL-Agent API (DataCo Smart Supply Chain)",
    version="2.0.0",
    description="Agentic Text-to-SQL assistant with read-only SQL guardrails, delivery delay anomaly detection, and auto-chart generation.",
)

agent = SupplyChainSQLAgent()

class AgentQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Plain-English supply chain question or SQL guardrail test")

@app.get("/health")
def health():
    schema = inspect_schema_tool("all")
    return {"status": "healthy", "tables": list(schema["schemas"].keys())}

@app.get("/anomalies")
def get_anomalies(z_threshold: float = 2.0):
    return detect_delivery_delay_anomalies_tool(z_threshold=z_threshold)

@app.post("/ask", response_model=AgentResponse)
def ask_agent(req: AgentQueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    return agent.run(req.question)
