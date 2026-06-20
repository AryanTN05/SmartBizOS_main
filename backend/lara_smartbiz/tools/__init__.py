import json

from .crm_tools import get_leads, get_lead_dossier, create_lead, update_lead
from .automation_tools import get_automation_status, trigger_sequence, get_lead_timeline
from .reports_tools import get_report, generate_report, compare_reports
from .outreach_tools import send_email, get_email_thread
from .fintech_tools import get_invoices, get_spend_summary
from .web_tools import web_search
from .calendar_tools import schedule_meeting

async def search_documents_async(query: str, top_k: int = 5, session_id: str = None, **kwargs):
    from lara_smartbiz.services.memory import search_memory
    # Use provided session_id or fallback to demo_session
    sid = session_id if session_id else "demo_session"
    results = await search_memory(query, sid, top_k)
    return json.dumps(results)

TOOL_FUNCTIONS = {
    "get_leads": get_leads,
    "get_lead_dossier": get_lead_dossier,
    "create_lead": create_lead,
    "update_lead": update_lead,
    "get_automation_status": get_automation_status,
    "trigger_sequence": trigger_sequence,
    "get_lead_timeline": get_lead_timeline,
    "get_report": get_report,
    "generate_report": generate_report,
    "compare_reports": compare_reports,
    "send_email": send_email,
    "get_email_thread": get_email_thread,
    "get_invoices": get_invoices,
    "get_spend_summary": get_spend_summary,
    "search_documents": search_documents_async,
    "web_search": web_search,
    "schedule_meeting": schedule_meeting,
    "show_artifact": lambda **kwargs: "Artifact displayed on user screen."
}

def get_tool_registry():
    return [
        {
            "name": "web_search",
            "description": "Perform a real-time Google web search to look up information online.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "schedule_meeting",
            "description": "Schedule a meeting with a lead or client on the calendar.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Name of the person"},
                    "email": {"type": "STRING", "description": "Email of the person"},
                    "date": {"type": "STRING", "description": "Date of the meeting (YYYY-MM-DD)"},
                    "time": {"type": "STRING", "description": "Time of the meeting (HH:MM AM/PM)"},
                    "duration_minutes": {"type": "INTEGER", "description": "Duration in minutes"}
                },
                "required": ["name", "email", "date", "time"]
            }
        },
        {
            "name": "get_leads",
            "description": "Fetch leads with optional filters. Use for 'show me leads', 'who are my hottest leads', 'who should I call today', or to search for a specific lead by name.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "status": {"type": "STRING"},
                    "min_score": {"type": "INTEGER"},
                    "name": {"type": "STRING", "description": "Search for a lead by name"},
                    "limit": {"type": "INTEGER"}
                }
            }
        },
        {
            "name": "get_lead_dossier",
            "description": "Full intelligence profile on one lead — enrichment, score explanation, activity timeline, suggested next actions.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lead_id": {"type": "STRING"}
                },
                "required": ["lead_id"]
            }
        },
        {
            "name": "create_lead",
            "description": "Create a new lead.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "company": {"type": "STRING"},
                    "email": {"type": "STRING"},
                    "phone": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "linkedin_url": {"type": "STRING"},
                    "source": {"type": "STRING"},
                    "status": {"type": "STRING"},
                    "score": {"type": "INTEGER"}
                },
                "required": ["name"]
            }
        },
        {
            "name": "update_lead",
            "description": "Update an existing lead.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lead_id": {"type": "STRING"},
                    "name": {"type": "STRING"},
                    "email": {"type": "STRING"},
                    "phone": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "linkedin_url": {"type": "STRING"},
                    "company": {"type": "STRING"},
                    "status": {"type": "STRING"},
                    "score": {"type": "INTEGER"},
                    "notes": {"type": "STRING"}
                },
                "required": ["lead_id"]
            }
        },
        {
            "name": "get_automation_status",
            "description": "Get automation sequence status for a lead.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lead_id": {"type": "STRING"}
                },
                "required": ["lead_id"]
            }
        },
        {
            "name": "trigger_sequence",
            "description": "Trigger a new automation sequence for a lead.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lead_id": {"type": "STRING"},
                    "sequence_type": {"type": "STRING"}
                },
                "required": ["lead_id", "sequence_type"]
            }
        },
        {
            "name": "get_lead_timeline",
            "description": "Get the complete timeline of interactions with a lead.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lead_id": {"type": "STRING"}
                },
                "required": ["lead_id"]
            }
        },
        {
            "name": "get_report",
            "description": "Fetch a business summary report. Use for 'how was last week', 'show me this month's performance'.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "period": {"type": "STRING"},
                    "specific_date": {"type": "STRING"}
                }
            }
        },
        {
            "name": "generate_report",
            "description": "Generate a new business report.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        },
        {
            "name": "compare_reports",
            "description": "Compare two time periods side by side.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "period_a_start": {"type": "STRING"},
                    "period_b_start": {"type": "STRING"}
                },
                "required": ["period_a_start", "period_b_start"]
            }
        },
        {
            "name": "send_email",
            "description": "Draft and send an email to a lead. Use when user asks to reach out, follow up, or send a message.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lead_id": {"type": "STRING"},
                    "subject": {"type": "STRING"},
                    "body": {"type": "STRING"},
                    "send_immediately": {"type": "BOOLEAN"}
                },
                "required": ["lead_id", "subject", "body"]
            }
        },
        {
            "name": "get_email_thread",
            "description": "Get the email thread for a specific lead.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lead_id": {"type": "STRING"}
                },
                "required": ["lead_id"]
            }
        },
        {
            "name": "get_invoices",
            "description": "Fetch invoices with optional status/vendor filter.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "status": {"type": "STRING"},
                    "vendor": {"type": "STRING"},
                    "period": {"type": "STRING"}
                }
            }
        },
        {
            "name": "get_spend_summary",
            "description": "Get a summary of spending and invoices.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        },
        {
            "name": "search_documents",
            "description": "Semantic search across all uploaded documents. Use when user asks about contract terms, document contents, or anything from a file they've uploaded.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING"},
                    "top_k": {"type": "INTEGER"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "show_artifact",
            "description": "Show an artifact (URL, table, or chart) on the user's screen. Use this to render graphs, tables, or charts.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "url": {"type": "STRING", "description": "URL to a relevant image or video, if any, otherwise empty string."},
                    "table": {"type": "STRING", "description": "HTML formatted table representing tabular data or lists, if any, otherwise empty string."},
                    "charts": {"type": "STRING", "description": "A stringified JSON Chart.js configuration object representing a chart, if any, otherwise empty string."}
                }
            }
        }
    ]
    