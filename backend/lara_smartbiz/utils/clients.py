import httpx
from google import genai
from openai import AsyncOpenAI
from lara_smartbiz.config import settings

def get_http_client() -> httpx.AsyncClient | None:
    """Returns an httpx client configured with proxy if set in config."""
    if settings.http_proxy:
        return httpx.AsyncClient(proxy=settings.http_proxy)
    return None

def get_gemini_client() -> genai.Client:
    """Initialize Gemini client, using proxy to prevent IP trackback."""
    http_client = None
    if settings.http_proxy:
        http_client = httpx.Client(proxy=settings.http_proxy)
    
    return genai.Client(
        api_key=settings.google_api_key,
        http_options={'httpxClient': http_client} if http_client else None
    )

def get_openai_client() -> AsyncOpenAI:
    """Initialize OpenAI client, using proxy if configured."""
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        http_client=get_http_client()
    )
