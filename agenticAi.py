from langchain_groq import ChatGroq
from langchain import PromptTemplate, LLMChain
import warnings

# Suppress LangChain deprecation warnings globally
warnings.filterwarnings(
    "ignore",
    message="Importing .* from langchain root module is no longer supported"
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from tavily import TavilyClient

from dotenv import load_dotenv
import os
from typing import Dict, Any
import requests
from pydantic import BaseModel, Field
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import SerpAPIWrapper
import json

# Load environment variables from .env file
load_dotenv()

## Groq initialization
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

tool = DuckDuckGoSearchResults(output_format="json", max_results=5)
serpapi = SerpAPIWrapper()
tavily = TavilyClient(TAVILY_API_KEY)


class IntentResult(BaseModel):
    intent: str = Field(..., description="One of 'company_research', 'schedule_meeting', or 'other'")
    company: str | None = Field(None, description="Company name if intent is company_research")
    meeting_datetime: str | None = Field(None, description="ISO datetime if intent is schedule_meeting")
    participants: list[str] | None = Field(None, description="List of participant emails if schedule_meeting")

# 💬 Create ChatPrompt for intent classification + detail extraction
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful agent. Extract the intent and relevant details in JSON."),
    ("user", 
     "Email: {email_text}\n\n"
     "Output a JSON matching the schema:\n"
     "- intent: 'company_research' | 'schedule_meeting' | 'other'\n"
     "- company (string|null)\n"
     "- meeting_datetime (string|null)\n"
     "- participants (list of strings|null)\n"
     "If no relevant info, use null.")
])
llm = ChatGroq(
    model="deepseek-r1-distill-llama-70b",
    temperature=0.7,
    max_tokens=None,
    reasoning_format="parsed",
    timeout=None,
)
parser = PydanticOutputParser(pydantic_object=IntentResult)
intent_chain = prompt | llm | parser


# ════════════════════ Intent Agent ════════════════════
async def intent_agent(email_text: str) -> IntentResult:
    """Return structured intent + details from email_text."""
    result: IntentResult = await intent_chain.ainvoke({"email_text": email_text})
    return result

# ════════════════════ Router ════════════════════
async def router(intent: str, email_text: str) -> Dict[str, Any]:
    """
    Decide which agent to run based on identified intent
    """
    if intent == "company_research":
        return await company_research_agent(email_text)
    elif intent == "schedule_meeting":
        return await meeting_agent(email_text)
    else:
        return {"status": "no_action", "reason": "unsupported_intent"}

# ════════════════════ Company Research Agent ════════════════════

company_llm_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a research assistant extracting structured company details."),
    ("user", 
     "Here are search result snippets:\n\n{snippets}\n\n"
     "Please summarize and extract:\n"
     "- Headquarters\n"
     "- Total number of employees (approximate)\n"
     "- Office locations mention\n"
     "- One‑line company description\n\nOutput as JSON.")
])
company_chain = company_llm_prompt | llm

async def extract_company_details(raw_results):
    """ 
    Extract structured company details from raw search results.

    """
    resp = await company_llm_prompt | llm
    result = await (company_llm_prompt | llm).ainvoke({"raw_results": raw_results})
    return result.content

async def company_research_agent(comp: str) -> Dict[str, Any]:
    """
    Fetch details about the company from web and return important details.
    """
    raw = tool.invoke(comp)
    summary = " ".join([r.get("snippet","") for r in json.loads(raw)])

    serpData = serpapi.results(comp)
    knowledge_graph = serpData.get("knowledge_graph", {})

    serp_summary_parts = []
    for key, val in knowledge_graph.items():
        serp_summary_parts.append(f"{key}: {val}")

    serp_summary = "\n".join(serp_summary_parts)

    final_summary = summary + "\n\n" + serp_summary
    #print("Final Summary Snippet: \n", final_summary)

    extracted_json = await company_chain.ainvoke({"snippets": final_summary})
    content_str = extracted_json.content.strip()

    if content_str.startswith("```json"):
        content_str = content_str.removeprefix("```json").removesuffix("```").strip()
    elif content_str.startswith("```"):
        content_str = content_str.removeprefix("```").removesuffix("```").strip()

    try:
        details = json.loads(content_str)
    except json.JSONDecodeError:
        details = {"error": "LLM output not JSON", "raw_output": extracted_json}

    return {
        "company": comp,
        "summary_snippet": summary,
        "raw_results": raw,
        "extracted": details
    }

# ════════════════════ Meeting Agent ════════════════════
async def meeting_agent(email_text: str) -> Dict[str, Any]:
    """
    Parse email to find meeting datetime, participants, return event data
    """
    # stub parser
    meeting = {
        "datetime": "2025-07-10T15:00:00",
        "participants": ["alice@example.com"],
        "subject": "Discuss Q3 strategy"
    }
    return {"intent": "schedule_meeting", "meeting": meeting}

# ════════════════════ DB Agent ════════════════════
async def db_agent(result: Dict[str, Any]) -> None:
    """
    Persist enriched result in your database
    """
    # stub: pretend to insert into DB
    print("DB save:", result)

# ════════════════════ Notifier Agent ════════════════════
async def notifier_agent(result: Dict[str, Any]) -> None:
    """
    Send a summary email or store summary in UI/DB
    """
    print("Notify user:", result.get("summary") or result)

# ════════════════════ Orchestrator / Main Flow ════════════════════
async def process_email(id: str, msg_id: str, email_text: str):

    intent = await intent_agent(email_text)
    #print("Identified intent:", intent)
    #print("Company:", intent.company)
    if not intent.company:
        return
    return await company_research_agent(intent.company)

    # companyData = await company_research_agent(intent.company)
    # add_to_detailsTable(companyData, msg_id, id)


    # result = await router(intent, email_text)
    # await db_agent(result)
    # await notifier_agent(result)




'''

from agno.agent import Agent, RunResponse
from agno.models.groq import Groq
from agno.tools.models.groq import GroqTools
from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Create an Agno Agent for intent classification using your Groq LLM & tools
intent_agent = Agent(
    model=Groq(id="deepseek-r1-distill-llama-70b", temperature=0.7),
    description="Classify email intent: company_research, schedule_meeting, or other.",
    tools=[GroqTools()],
    show_tool_calls=True,
    markdown=False
)


async def intent_agent_fn(email_text: str) -> str:
    """
    Uses Agno agent to decide intent. Returns 'company_research', 'schedule_meeting' or 'other'.
    """
    input_prompt = f"Email: {email_text}\nWhat is the intent?"
    response: RunResponse = intent_agent.run(input_prompt)
    # intent = response.strip().lower()
    return response

# SAMPLE USAGE
async def process_email(email_text: str):
    intent = await intent_agent_fn(email_text)
    print("Determined intent:", intent)
    # Continue with your router, DB, notifier, etc.



'''