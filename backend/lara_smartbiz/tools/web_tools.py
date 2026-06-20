import json
from google import genai
from google.genai.types import GoogleSearch
from lara_smartbiz.utils.clients import get_gemini_client

async def web_search(query: str, **kwargs):
    """
    Perform a real-time Google web search using Google's native Search Grounding.
    """
    try:
        client = get_gemini_client()
        response = await client.aio.models.generate_content(
            model='gemini-2.0-flash',
            contents=f'Please search Google to find information about: {query}\nProvide a concise and factual answer.',
            config={'tools': [{'google_search': {}}]}
        )
        return json.dumps({"query": query, "results": response.text})
    except Exception as e:
        return json.dumps({"error": f"Failed to execute web search: {str(e)}"})
