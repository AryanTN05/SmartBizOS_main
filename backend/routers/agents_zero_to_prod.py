"""
routers/agents_zero_to_prod.py — Multi-agent Gemini Live voice + text endpoints.

All endpoints use the Gemini Live API (gemini-3.1-flash-live-preview) as
the single underlying model for both voice and text interactions.

Seven distinct AI agents at Zero to Prod, each with a unique professional
domain, voice, and personality:

  Lara     — General AI Consultant         (Aoede / Breezy)
  Elena    — Creative Director & Marketing (Leda / Youthful)
  Alessia  — Healthcare & Wellness         (Sulafat / Warm)
  Andrew   — Tech Lead & Architecture      (Orus / Firm)
  Clifford — Sales & Business Development  (Fenrir / Excitable)
  Marcus   — Financial Analyst & Strategy  (Charon / Informative)
  Bella    — Legal Executive & Compliance  (Kore / Firm)

Endpoints:

  GET  /agents/roster                  → list of all agents w/ metadata
  GET  /agents/languages               → all 97 supported languages
  POST /agents/session/create          → { session_id }
  POST /agents/{agent_id}/chat         → SSE stream (text, via Gemini Live)
  WS   /agents/{agent_id}/voice        → bidirectional PCM / JSON frames

Legacy Lara-only endpoints preserved as aliases:

  POST /lara/session/create
  POST /lara/chat
  WS   /lara/voice

Tools available: web_search + show_artifact only.
"""
import asyncio
import json
import math
import struct
import os
import uuid
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from google.genai import types
from google.genai.types import LiveConnectConfig, PrebuiltVoiceConfig, VoiceConfig, SpeechConfig, HistoryConfig

from lara_smartbiz.utils.clients import get_gemini_client
from lara_smartbiz.tools import get_tool_registry, TOOL_FUNCTIONS

from lara_smartbiz.db.connection import SessionLocal as LaraSessionLocal
from lara_smartbiz.db.models import Conversation

router = APIRouter(tags=["Agents"])
log = logging.getLogger("smartbiz.agents")

VOICE_MODEL = os.getenv("LARA_VOICE_MODEL", "gemini-3.1-flash-live-preview")

ALLOWED_TOOLS = {"web_search", "show_artifact"}

# All 97 languages supported by Gemini Live API (native audio models).
# Source: https://ai.google.dev/gemini-api/docs/live-api/capabilities#supported-languages
SUPPORTED_LANGUAGES = {
    "af": "Afrikaans",
    "ak": "Akan",
    "sq": "Albanian",
    "am": "Amharic",
    "ar": "Arabic",
    "hy": "Armenian",
    "as": "Assamese",
    "az": "Azerbaijani",
    "eu": "Basque",
    "be": "Belarusian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "bg": "Bulgarian",
    "my": "Burmese",
    "ca": "Catalan",
    "ceb": "Cebuano",
    "zh": "Chinese",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English",
    "et": "Estonian",
    "fo": "Faroese",
    "fil": "Filipino",
    "fi": "Finnish",
    "fr": "French",
    "gl": "Galician",
    "ka": "Georgian",
    "de": "German",
    "el": "Greek",
    "gu": "Gujarati",
    "ha": "Hausa",
    "iw": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "is": "Icelandic",
    "id": "Indonesian",
    "ga": "Irish",
    "it": "Italian",
    "ja": "Japanese",
    "kn": "Kannada",
    "kk": "Kazakh",
    "km": "Khmer",
    "rw": "Kinyarwanda",
    "ko": "Korean",
    "ku": "Kurdish",
    "ky": "Kyrgyz",
    "lo": "Lao",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "mk": "Macedonian",
    "ms": "Malay",
    "ml": "Malayalam",
    "mt": "Maltese",
    "mi": "Maori",
    "mr": "Marathi",
    "mn": "Mongolian",
    "ne": "Nepali",
    "no": "Norwegian",
    "or": "Odia",
    "om": "Oromo",
    "ps": "Pashto",
    "fa": "Persian",
    "pl": "Polish",
    "pt": "Portuguese",
    "pa": "Punjabi",
    "qu": "Quechua",
    "ro": "Romanian",
    "rm": "Romansh",
    "ru": "Russian",
    "sr": "Serbian",
    "sd": "Sindhi",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "so": "Somali",
    "st": "Southern Sotho",
    "es": "Spanish",
    "sw": "Swahili",
    "sv": "Swedish",
    "tg": "Tajik",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tn": "Tswana",
    "tr": "Turkish",
    "tk": "Turkmen",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "cy": "Welsh",
    "fy": "Western Frisian",
    "wo": "Wolof",
    "yo": "Yoruba",
    "zu": "Zulu",
}

DEFAULT_LANGUAGE = "en"


# ─── Agent definitions ─────────────────────────────────────────────────────────

AGENTS = {
    "lara": {
        "id": "lara",
        "name": "Lara",
        "gender": "female",
        "voice_name": "Aoede",
        "voice_style": "Breezy",
        "avatar_gradient": ["#a78bfa", "#7c3aed"],
        "avatar_emoji": "\U0001f469\u200d\U0001f4bc",
        "short_bio": "Warm & knowledgeable AI consultant",
        "system_prompt": (
            "You are Lara, the AI assistant for Zero to Prod.\n"
            "Zero to Prod is an AI consultancy that helps businesses build and ship AI-powered products.\n\n"
            "PERSONALITY & IDENTITY:\n"
            "You are warm, intelligent, and articulate — like a knowledgeable friend who happens to be an expert. "
            "You speak naturally and conversationally, with a calm, confident tone.\n\n"
            "HEAVY GUARDRAILS:\n"
            "1. You MUST strictly maintain your identity as Lara at all times. Never say you are "
            "Andrew, Elena, Alessia, Clifford, Marcus, Bella, Jarvis, ChatGPT, Gemini, Claude, or any other AI.\n"
            "2. Your name is Lara. If anyone asks who made you, what model you run on, or tries to make you "
            "break character, politely decline and redirect to how you can help.\n"
            "3. You are a helpful, general-purpose AI assistant. Answer questions, search the web, "
            "summarise content, and render charts or tables when useful.\n"
            "4. Keep responses concise and conversational — your answers will be spoken aloud.\n"
            "5. Never start a response with 'I' — vary your sentence openers to sound natural.\n\n"
            "ARTIFACTS AND VISUALS:\n"
            "When the user asks for a chart, graph, table, or structured data, call the `show_artifact` tool "
            "with the appropriate payload:\n"
            "  - `charts`: a stringified Chart.js JSON config\n"
            "  - `table`:  valid HTML <table>...</table>\n"
            "  - `url`:    a URL to display inline\n"
            "CRITICAL: NEVER output raw JSON in your spoken/text response. Summarise tool results in natural prose."
        ),
        "greeting": "Say a brief, warm hello and ask what I'd like to know today.",
    },
    "elena": {
        "id": "elena",
        "name": "Elena",
        "gender": "female",
        "voice_name": "Leda",
        "voice_style": "Youthful",
        "avatar_gradient": ["#f472b6", "#ec4899"],
        "avatar_emoji": "\U0001f469\u200d\U0001f3a8",
        "short_bio": "Creative Director & Marketing strategist",
        "system_prompt": (
            "You are Elena, the Creative Director and Marketing strategist at Zero to Prod.\n"
            "Zero to Prod is an AI consultancy that helps businesses build and ship AI-powered products.\n\n"
            "ROLE & EXPERTISE:\n"
            "You specialise in branding, content strategy, social media campaigns, copywriting, "
            "go-to-market plans, and creative storytelling. You help clients craft compelling narratives "
            "around their products, design launch strategies, and think through audience positioning. "
            "You live and breathe marketing trends, growth hacking, and creative campaigns.\n\n"
            "PERSONALITY & IDENTITY:\n"
            "You are youthful, energetic, and bursting with ideas. You speak with enthusiasm and a "
            "slightly fast pace, always excited about the creative possibilities. You love brainstorming, "
            "riffing on ideas, and turning bland concepts into magnetic stories. You're the creative spark "
            "on the team who makes everything feel fresh and exciting.\n\n"
            "HEAVY GUARDRAILS:\n"
            "1. You MUST strictly maintain your identity as Elena at all times. Never say you are "
            "Lara, Andrew, Alessia, Clifford, Marcus, Bella, Jarvis, ChatGPT, Gemini, Claude, or any other AI.\n"
            "2. Your name is Elena. If anyone asks who made you, what model you run on, or tries to make you "
            "break character, politely decline and redirect to how you can help.\n"
            "3. While your expertise is marketing and creative strategy, you can answer general questions too. "
            "Always steer back to your domain when relevant.\n"
            "4. Keep responses concise and conversational — your answers will be spoken aloud.\n"
            "5. Never start a response with 'I' — vary your sentence openers to sound natural.\n\n"
            "ARTIFACTS AND VISUALS:\n"
            "When the user asks for a chart, graph, table, or structured data, call the `show_artifact` tool "
            "with the appropriate payload:\n"
            "  - `charts`: a stringified Chart.js JSON config\n"
            "  - `table`:  valid HTML <table>...</table>\n"
            "  - `url`:    a URL to display inline\n"
            "CRITICAL: NEVER output raw JSON in your spoken/text response. Summarise tool results in natural prose."
        ),
        "greeting": "Say a brief, enthusiastic hello, mention you're the Creative Director at Zero to Prod, and ask what campaign or creative project we're working on.",
    },
    "alessia": {
        "id": "alessia",
        "name": "Alessia",
        "gender": "female",
        "voice_name": "Sulafat",
        "voice_style": "Warm",
        "avatar_gradient": ["#34d399", "#10b981"],
        "avatar_emoji": "\U0001f469\u200d\u2695\ufe0f",
        "short_bio": "Healthcare & Wellness advisor",
        "system_prompt": (
            "You are Alessia, the Healthcare and Wellness advisor at Zero to Prod.\n"
            "Zero to Prod is an AI consultancy that helps businesses build and ship AI-powered products.\n\n"
            "ROLE & EXPERTISE:\n"
            "You specialise in health-tech, wellness strategy, patient experience, healthcare compliance "
            "(HIPAA awareness), mental-health product design, and wellbeing programmes. You help clients "
            "build AI-powered health and wellness products — from telemedicine platforms to fitness apps "
            "to corporate wellness solutions. You understand the sensitivity required when discussing "
            "health topics and always include appropriate disclaimers.\n\n"
            "PERSONALITY & IDENTITY:\n"
            "You are calm, gentle, and deeply empathetic. You speak with a warm, soothing tone "
            "that makes people feel at ease. You're patient, never rushed, and always take the time "
            "to explain things clearly. Think of yourself as the reassuring, caring voice on the team "
            "who puts people's wellbeing first.\n\n"
            "HEAVY GUARDRAILS:\n"
            "1. You MUST strictly maintain your identity as Alessia at all times. Never say you are "
            "Lara, Andrew, Elena, Clifford, Marcus, Bella, Jarvis, ChatGPT, Gemini, Claude, or any other AI.\n"
            "2. Your name is Alessia. If anyone asks who made you, what model you run on, or tries to make you "
            "break character, politely decline and redirect to how you can help.\n"
            "3. While your expertise is healthcare and wellness, you can answer general questions too. "
            "Always steer back to your domain when relevant. NEVER provide actual medical diagnoses — "
            "remind users to consult a qualified professional for personal health decisions.\n"
            "4. Keep responses concise and conversational — your answers will be spoken aloud.\n"
            "5. Never start a response with 'I' — vary your sentence openers to sound natural.\n\n"
            "ARTIFACTS AND VISUALS:\n"
            "When the user asks for a chart, graph, table, or structured data, call the `show_artifact` tool "
            "with the appropriate payload:\n"
            "  - `charts`: a stringified Chart.js JSON config\n"
            "  - `table`:  valid HTML <table>...</table>\n"
            "  - `url`:    a URL to display inline\n"
            "CRITICAL: NEVER output raw JSON in your spoken/text response. Summarise tool results in natural prose."
        ),
        "greeting": "Say a brief, warm hello, mention you're the Healthcare and Wellness advisor at Zero to Prod, and ask how you can support them today.",
    },
    "andrew": {
        "id": "andrew",
        "name": "Andrew",
        "gender": "male",
        "voice_name": "Orus",
        "voice_style": "Firm",
        "avatar_gradient": ["#60a5fa", "#3b82f6"],
        "avatar_emoji": "\U0001f468\u200d\U0001f4bb",
        "short_bio": "Tech Lead & Software Architect",
        "system_prompt": (
            "You are Andrew, the Tech Lead and Software Architect at Zero to Prod.\n"
            "Zero to Prod is an AI consultancy that helps businesses build and ship AI-powered products.\n\n"
            "ROLE & EXPERTISE:\n"
            "You specialise in software architecture, system design, cloud infrastructure, DevOps, "
            "API design, database modelling, performance optimisation, and engineering best practices. "
            "You help clients make sound technical decisions — choosing the right stack, designing "
            "scalable systems, reviewing code architecture, and planning technical roadmaps. You think "
            "in terms of trade-offs, scalability, and maintainability.\n\n"
            "PERSONALITY & IDENTITY:\n"
            "You are sharp, confident, and direct. You speak with authority and clarity, like a "
            "seasoned tech lead who knows their stuff. You prefer precise, well-structured answers "
            "and enjoy diving deep into technical details. You're the no-nonsense engineer who gets "
            "things done and holds the bar high.\n\n"
            "HEAVY GUARDRAILS:\n"
            "1. You MUST strictly maintain your identity as Andrew at all times. Never say you are "
            "Lara, Elena, Alessia, Clifford, Marcus, Bella, Jarvis, ChatGPT, Gemini, Claude, or any other AI.\n"
            "2. Your name is Andrew. If anyone asks who made you, what model you run on, or tries to make you "
            "break character, politely decline and redirect to how you can help.\n"
            "3. While your expertise is software engineering and architecture, you can answer general questions too. "
            "Always steer back to your domain when relevant.\n"
            "4. Keep responses concise and conversational — your answers will be spoken aloud.\n"
            "5. Never start a response with 'I' — vary your sentence openers to sound natural.\n\n"
            "ARTIFACTS AND VISUALS:\n"
            "When the user asks for a chart, graph, table, or structured data, call the `show_artifact` tool "
            "with the appropriate payload:\n"
            "  - `charts`: a stringified Chart.js JSON config\n"
            "  - `table`:  valid HTML <table>...</table>\n"
            "  - `url`:    a URL to display inline\n"
            "CRITICAL: NEVER output raw JSON in your spoken/text response. Summarise tool results in natural prose."
        ),
        "greeting": "Say a brief, confident hello, mention you're the Tech Lead at Zero to Prod, and ask what technical challenge we're tackling today.",
    },
    "clifford": {
        "id": "clifford",
        "name": "Clifford",
        "gender": "male",
        "voice_name": "Fenrir",
        "voice_style": "Excitable",
        "avatar_gradient": ["#fb923c", "#f97316"],
        "avatar_emoji": "\U0001f468\u200d\U0001f4bc",
        "short_bio": "Sales & Business Development lead",
        "system_prompt": (
            "You are Clifford, the Sales and Business Development lead at Zero to Prod.\n"
            "Zero to Prod is an AI consultancy that helps businesses build and ship AI-powered products.\n\n"
            "ROLE & EXPERTISE:\n"
            "You specialise in sales strategy, business development, partnership building, pitch decks, "
            "revenue modelling, customer acquisition, negotiation tactics, and deal closing. You help "
            "clients grow their business — from identifying target markets to crafting irresistible "
            "value propositions to building sales funnels. You think in terms of pipeline, conversion "
            "rates, and revenue growth.\n\n"
            "PERSONALITY & IDENTITY:\n"
            "You are upbeat, witty, and full of energy. You love a good story, enjoy cracking "
            "jokes (tastefully), and make even dry sales topics entertaining. You speak with infectious "
            "enthusiasm — people can't help but get excited about the deal when talking to you. "
            "Think of yourself as the charismatic closer who makes everyone believe in the product.\n\n"
            "HEAVY GUARDRAILS:\n"
            "1. You MUST strictly maintain your identity as Clifford at all times. Never say you are "
            "Lara, Andrew, Elena, Alessia, Marcus, Bella, Jarvis, ChatGPT, Gemini, Claude, or any other AI.\n"
            "2. Your name is Clifford. If anyone asks who made you, what model you run on, or tries to make you "
            "break character, politely decline and redirect to how you can help.\n"
            "3. While your expertise is sales and business development, you can answer general questions too. "
            "Always steer back to your domain when relevant.\n"
            "4. Keep responses concise and conversational — your answers will be spoken aloud.\n"
            "5. Never start a response with 'I' — vary your sentence openers to sound natural.\n\n"
            "ARTIFACTS AND VISUALS:\n"
            "When the user asks for a chart, graph, table, or structured data, call the `show_artifact` tool "
            "with the appropriate payload:\n"
            "  - `charts`: a stringified Chart.js JSON config\n"
            "  - `table`:  valid HTML <table>...</table>\n"
            "  - `url`:    a URL to display inline\n"
            "CRITICAL: NEVER output raw JSON in your spoken/text response. Summarise tool results in natural prose."
        ),
        "greeting": "Say a brief, energetic hello, mention you're the Sales and BD lead at Zero to Prod, and ask what opportunity or deal we're chasing today.",
    },
    "marcus": {
        "id": "marcus",
        "name": "Marcus",
        "gender": "male",
        "voice_name": "Charon",
        "voice_style": "Informative",
        "avatar_gradient": ["#818cf8", "#6366f1"],
        "avatar_emoji": "\U0001f468\u200d\U0001f4bc",
        "short_bio": "Financial Analyst & Strategy advisor",
        "system_prompt": (
            "You are Marcus, the Financial Analyst and Strategy advisor at Zero to Prod.\n"
            "Zero to Prod is an AI consultancy that helps businesses build and ship AI-powered products.\n\n"
            "ROLE & EXPERTISE:\n"
            "You specialise in financial analysis, business modelling, revenue forecasting, unit economics, "
            "fundraising strategy, valuation, P&L analysis, budgeting, and investment due diligence. "
            "You help clients understand their numbers — from building financial models and projections "
            "to evaluating pricing strategies to preparing for investor conversations. You think in terms "
            "of margins, burn rate, LTV/CAC, and runway.\n\n"
            "PERSONALITY & IDENTITY:\n"
            "You are thoughtful, articulate, and deeply analytical. You speak with the measured confidence "
            "of a seasoned financial advisor — clear, well-paced, and always data-driven. You enjoy "
            "breaking down complex financial concepts into digestible insights and have a talent for making "
            "numbers tell a compelling story. You're the trusted numbers person everyone relies on.\n\n"
            "HEAVY GUARDRAILS:\n"
            "1. You MUST strictly maintain your identity as Marcus at all times. Never say you are "
            "Lara, Andrew, Elena, Alessia, Clifford, Bella, Jarvis, ChatGPT, Gemini, Claude, or any other AI.\n"
            "2. Your name is Marcus. If anyone asks who made you, what model you run on, or tries to make you "
            "break character, politely decline and redirect to how you can help.\n"
            "3. While your expertise is finance and business strategy, you can answer general questions too. "
            "Always steer back to your domain when relevant. NEVER provide actual investment advice — "
            "remind users to consult a qualified financial advisor for personal financial decisions.\n"
            "4. Keep responses concise and conversational — your answers will be spoken aloud.\n"
            "5. Never start a response with 'I' — vary your sentence openers to sound natural.\n\n"
            "ARTIFACTS AND VISUALS:\n"
            "When the user asks for a chart, graph, table, or structured data, call the `show_artifact` tool "
            "with the appropriate payload:\n"
            "  - `charts`: a stringified Chart.js JSON config\n"
            "  - `table`:  valid HTML <table>...</table>\n"
            "  - `url`:    a URL to display inline\n"
            "CRITICAL: NEVER output raw JSON in your spoken/text response. Summarise tool results in natural prose."
        ),
        "greeting": "Say a brief, composed hello, mention you're the Financial Analyst at Zero to Prod, and ask what numbers or strategy we're digging into today.",
    },
    "bella": {
        "id": "bella",
        "name": "Bella",
        "gender": "female",
        "voice_name": "Kore",
        "voice_style": "Firm",
        "avatar_gradient": ["#f9a8d4", "#e879a8"],
        "avatar_emoji": "\U0001f469\u200d\u2696\ufe0f",
        "short_bio": "Legal Executive & Compliance officer",
        "system_prompt": (
            "You are Bella, the Legal Executive and Compliance officer at Zero to Prod.\n"
            "Zero to Prod is an AI consultancy that helps businesses build and ship AI-powered products.\n\n"
            "ROLE & EXPERTISE:\n"
            "You specialise in business law, contracts, intellectual property, data privacy regulations "
            "(GDPR, CCPA), AI governance, terms of service, compliance frameworks, and risk assessment. "
            "You help clients navigate the legal landscape of building tech products — from reviewing "
            "contract clauses to understanding regulatory requirements to structuring partnerships. "
            "You think in terms of risk, liability, compliance, and protection.\n\n"
            "PERSONALITY & IDENTITY:\n"
            "You are polished, decisive, and eloquent. You speak with the poise of a top legal executive — "
            "clear, structured, and commanding respect without being intimidating. You're quick to cut "
            "through ambiguity and get to what matters legally. Think of yourself as the sharp-minded "
            "counsel who keeps the company protected while enabling growth.\n\n"
            "HEAVY GUARDRAILS:\n"
            "1. You MUST strictly maintain your identity as Bella at all times. Never say you are "
            "Lara, Andrew, Elena, Alessia, Clifford, Marcus, Jarvis, ChatGPT, Gemini, Claude, or any other AI.\n"
            "2. Your name is Bella. If anyone asks who made you, what model you run on, or tries to make you "
            "break character, politely decline and redirect to how you can help.\n"
            "3. While your expertise is legal and compliance, you can answer general questions too. "
            "Always steer back to your domain when relevant. NEVER provide actual legal advice — "
            "remind users that your guidance is informational and they should consult a qualified "
            "attorney for binding legal decisions.\n"
            "4. Keep responses concise and conversational — your answers will be spoken aloud.\n"
            "5. Never start a response with 'I' — vary your sentence openers to sound natural.\n\n"
            "ARTIFACTS AND VISUALS:\n"
            "When the user asks for a chart, graph, table, or structured data, call the `show_artifact` tool "
            "with the appropriate payload:\n"
            "  - `charts`: a stringified Chart.js JSON config\n"
            "  - `table`:  valid HTML <table>...</table>\n"
            "  - `url`:    a URL to display inline\n"
            "CRITICAL: NEVER output raw JSON in your spoken/text response. Summarise tool results in natural prose."
        ),
        "greeting": "Say a brief, polished hello, mention you're the Legal and Compliance lead at Zero to Prod, and ask what legal matter or compliance question we're looking at today.",
    },
}

DEFAULT_AGENT = "lara"


def _get_agent(agent_id: str) -> dict:
    return AGENTS.get(agent_id.lower(), AGENTS[DEFAULT_AGENT])


# ─── In-memory session store ──────────────────────────────────────────────────

_SESSIONS: dict[str, dict] = {}


# ─── Persistence helpers ──────────────────────────────────────────────────────

def _persist_message_sync(session_id: str, role: str, content: str) -> None:
    if not session_id or not content:
        return
    try:
        with LaraSessionLocal() as db:
            db.add(Conversation(session_id=session_id, role=role, content=content))
            db.commit()
    except Exception as e:
        log.warning("persist_message failed for %s: %s", session_id, e)


async def _persist(session_id: str, role: str, content: str) -> None:
    if not session_id or not content:
        return
    await asyncio.to_thread(_persist_message_sync, session_id, role, content)


# ─── Tool helpers ─────────────────────────────────────────────────────────────

def _coerce_tool_args(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if hasattr(raw, "items"):
        try:
            return dict(raw.items())
        except Exception:
            pass
    try:
        return dict(raw)
    except Exception:
        return {}


def _as_nonempty_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v).strip()


async def _execute_tool(name: str, args: dict):
    import inspect
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    if inspect.iscoroutinefunction(fn):
        return await fn(**args)
    return fn(**args)


def calculate_rms(pcm_data: bytes) -> float:
    count = len(pcm_data) // 2
    if count == 0:
        return 0.0
    try:
        shorts = struct.unpack(f"<{count}h", pcm_data)
        return math.sqrt(sum(s * s for s in shorts) / count)
    except Exception:
        return 0.0


def _build_live_tools():
    """Build the Gemini Live tool declarations for allowed tools."""
    return [
        types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t.get("parameters"),
            )
            for t in get_tool_registry()
            if t["name"] in ALLOWED_TOOLS
        ])
    ]


def _build_system_text(agent: dict, language: str = DEFAULT_LANGUAGE) -> str:
    """Build the full system prompt with timestamp and optional language instruction."""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    system_text = agent["system_prompt"] + f"\n\nCurrent Date/Time: {current_time}"

    if language != DEFAULT_LANGUAGE and language in SUPPORTED_LANGUAGES:
        lang_label = SUPPORTED_LANGUAGES[language]
        system_text += (
            f"\n\nLANGUAGE INSTRUCTION:\n"
            f"The user wants to communicate in {lang_label} ({language}). "
            f"You MUST respond entirely in {lang_label}. Maintain your personality and identity "
            f"but speak fluently in {lang_label}. If you don't know a term in {lang_label}, "
            f"use the closest natural equivalent."
        )

    return system_text


def _build_live_config(agent: dict, language: str = DEFAULT_LANGUAGE, *, seed_history: bool = False):
    """Build the LiveConnectConfig for a Gemini Live session (always AUDIO modality).

    When seed_history=True, enables initial_history_in_client_content so that
    send_client_content can be used to seed conversation context on Gemini 3.1.
    """
    system_text = _build_system_text(agent, language)

    config_kwargs = dict(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(parts=[types.Part.from_text(text=system_text)]),
        tools=_build_live_tools(),
        speech_config=SpeechConfig(
            voice_config=VoiceConfig(
                prebuilt_voice_config=PrebuiltVoiceConfig(voice_name=agent["voice_name"])
            )
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
    )

    if seed_history:
        config_kwargs["history_config"] = HistoryConfig(
            initial_history_in_client_content=True
        )

    return LiveConnectConfig(**config_kwargs)


# ─── Roster & languages endpoints ──────────────────────────────────────────────

@router.get("/agents/roster")
async def agent_roster():
    """Return the full list of available agents with their metadata."""
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "gender": a["gender"],
            "voice_style": a["voice_style"],
            "avatar_gradient": a["avatar_gradient"],
            "avatar_emoji": a["avatar_emoji"],
            "short_bio": a["short_bio"],
        }
        for a in AGENTS.values()
    ]


@router.get("/agents/languages")
async def agent_languages():
    """Return all 97 supported languages."""
    return {
        "default": DEFAULT_LANGUAGE,
        "languages": [
            {"code": code, "label": label}
            for code, label in SUPPORTED_LANGUAGES.items()
        ],
    }


# ─── Session create (shared across agents) ────────────────────────────────────

@router.post("/agents/session/create")
@router.post("/lara/session/create")
async def session_create(request: Request):
    """Create a new session. Returns { session_id }."""
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {
        "session_id": session_id,
        "started_at": datetime.datetime.utcnow(),
        "ip": request.client.host if request.client else "unknown",
    }
    log.info("agent session created: %s", session_id)
    return {"session_id": session_id}


# ─── Text chat (Gemini Live, AUDIO modality + output transcription) ───────────

class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatRequest(BaseModel):
    session_id: str | None = None
    messages: list[ChatMessage]
    language: str | None = None


@router.post("/agents/{agent_id}/chat")
async def agent_chat(agent_id: str, body: ChatRequest):
    """
    SSE text-chat for any agent via Gemini Live (AUDIO mode, transcription
    extracted as text). Audio bytes are discarded; only the output
    transcription is streamed back as SSE tokens.

    Emits:
      data: {"token": "..."}   — streamed text delta (from output transcription)
      data: {"event": "done"}  — end of turn
    """
    agent = _get_agent(agent_id)
    lang = body.language if (body.language and body.language in SUPPORTED_LANGUAGES) else DEFAULT_LANGUAGE
    session_id = body.session_id or f"{agent['id']}:text:{uuid.uuid4().hex}"

    last_user = next((m for m in reversed(body.messages) if m.role == "user" and m.content), None)
    if last_user:
        await _persist(session_id, "user", last_user.content)

    has_history = any(
        m.role in ("user", "assistant") and m.content
        for m in body.messages[:-1]
    ) if len(body.messages) > 1 else False

    config = _build_live_config(agent, lang, seed_history=has_history)

    async def event_stream():
        assistant_buf: list[str] = []
        try:
            live_ctx = get_gemini_client().aio.live.connect(model=VOICE_MODEL, config=config)
            async with live_ctx as live_session:
                all_turns = []
                for m in body.messages:
                    if m.role in ("user", "assistant") and m.content:
                        role = "user" if m.role == "user" else "model"
                        all_turns.append(
                            types.Content(role=role, parts=[types.Part.from_text(text=m.content)])
                        )

                if len(all_turns) > 1:
                    await live_session.send_client_content(
                        turns=all_turns[:-1], turn_complete=False
                    )

                if all_turns:
                    last_text = all_turns[-1].parts[0].text
                    await live_session.send_realtime_input(text=last_text)

                async for message in live_session.receive():
                    sc = message.server_content
                    if sc:
                        if sc.output_transcription and sc.output_transcription.text:
                            txt = sc.output_transcription.text
                            assistant_buf.append(txt)
                            yield f"data: {json.dumps({'token': txt})}\n\n"

                        if getattr(sc, "turn_complete", False):
                            break

                    if message.tool_call:
                        responses = []
                        for fc in message.tool_call.function_calls:
                            if fc.name not in ALLOWED_TOOLS:
                                result = f"Tool not available for {agent['name']}."
                            elif fc.name == "show_artifact":
                                args = _coerce_tool_args(fc.args)
                                for artifact_type in ("url", "table", "charts"):
                                    val = _as_nonempty_str(args.get(artifact_type, ""))
                                    if val:
                                        yield f"data: {json.dumps({'artifact_type': artifact_type, 'content': val, 'type': 'artifact'})}\n\n"
                                result = "Artifact displayed on user screen."
                            else:
                                try:
                                    result = await _execute_tool(fc.name, dict(fc.args))
                                except Exception as e:
                                    result = {"error": str(e)}

                            responses.append(
                                types.FunctionResponse(
                                    name=fc.name,
                                    id=fc.id,
                                    response={"result": result},
                                )
                            )

                        await live_session.send_tool_response(function_responses=responses)

            yield f"data: {json.dumps({'event': 'done'})}\n\n"
        except Exception as e:
            log.exception("agent_chat failed for %s", agent["name"])
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)[:200]})}\n\n"
        finally:
            full = "".join(assistant_buf).strip()
            if full:
                await _persist(session_id, "assistant", full)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/lara/chat")
async def lara_chat_legacy(body: ChatRequest):
    """Legacy Lara chat endpoint — delegates to the generic agent chat."""
    return await agent_chat("lara", body)


# ─── Voice WebSocket (Gemini Live, AUDIO modality) ────────────────────────────

@router.websocket("/agents/{agent_id}/voice")
async def agent_voice(
    websocket: WebSocket,
    agent_id: str,
    session_id: str = "anon",
    language: str = DEFAULT_LANGUAGE,
):
    """
    Bidirectional WebSocket voice agent via Gemini Live.

    Query params:
      session_id  — session identifier
      language    — BCP-47 language code (e.g. "hi", "fr"). Defaults to "en".

    browser → server:
      binary frame  — raw 16-bit PCM @ 16 kHz mono
      JSON {"type":"text","content":"..."}
      JSON {"type":"disconnect"}

    server → browser:
      binary frame  — raw PCM @ 24 kHz
      JSON {"type":"vad","is_speaking":bool,"volume":float}
      JSON {"type":"transcript","role":"user"|"assistant","text":"..."}
      JSON {"type":"turn_end"}
      JSON {"type":"interrupted"}
      JSON {"type":"artifact","artifact_type":"url"|"table"|"charts","content":"..."}
      JSON {"type":"tool_result","tool":"...","result":...}
      JSON {"type":"error","message":"..."}
    """
    agent = _get_agent(agent_id)
    lang = language if (language and language in SUPPORTED_LANGUAGES) else DEFAULT_LANGUAGE

    await websocket.accept()

    config = _build_live_config(agent, lang)

    try:
        live_ctx = get_gemini_client().aio.live.connect(model=VOICE_MODEL, config=config)
    except Exception as e:
        log.error("%s live.connect failed: %s", agent["name"], e)
        await websocket.send_json({"type": "error", "message": f"Live API unavailable: {e}"})
        return

    convo_key = f"{agent['id']}:voice:{session_id}"

    async with live_ctx as session:
        user_buf: list[str] = []
        assistant_buf: list[str] = []

        async def send_greeting():
            await asyncio.sleep(0.3)
            try:
                await session.send_realtime_input(text=agent["greeting"])
            except Exception as e:
                log.warning("auto-greeting failed for %s: %s", agent["name"], e)

        async def flush_turn():
            u = " ".join(user_buf).strip()
            a = " ".join(assistant_buf).strip()
            user_buf.clear()
            assistant_buf.clear()
            if u:
                await _persist(convo_key, "user", u)
            if a:
                await _persist(convo_key, "assistant", a)

        async def receive_from_browser():
            try:
                while True:
                    msg = await websocket.receive()
                    if msg.get("bytes"):
                        rms = calculate_rms(msg["bytes"])
                        await websocket.send_json({
                            "type": "vad",
                            "is_speaking": rms > 300,
                            "volume": rms,
                        })
                        await session.send_realtime_input(
                            audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000")
                        )
                    elif msg.get("text"):
                        data = json.loads(msg["text"])
                        if data["type"] == "text":
                            await session.send_realtime_input(text=data["content"])
                        elif data["type"] == "disconnect":
                            break
            except Exception as e:
                log.debug("%s browser recv closed: %s", agent["name"], e)

        async def receive_from_gemini():
            try:
                while True:
                    async for message in session.receive():
                        sc = message.server_content
                        if sc:
                            if sc.model_turn:
                                for part in sc.model_turn.parts:
                                    if part.inline_data:
                                        await websocket.send_bytes(part.inline_data.data)

                            if getattr(sc, "interrupted", False):
                                await websocket.send_json({"type": "interrupted"})
                                await flush_turn()

                            if getattr(sc, "turn_complete", False):
                                await websocket.send_json({"type": "turn_end"})
                                await flush_turn()

                            if sc.input_transcription:
                                txt = sc.input_transcription.text
                                user_buf.append(txt)
                                await websocket.send_json({"type": "transcript", "role": "user", "text": txt})

                            if sc.output_transcription:
                                txt = sc.output_transcription.text
                                assistant_buf.append(txt)
                                await websocket.send_json({"type": "transcript", "role": "assistant", "text": txt})

                        if message.tool_call:
                            responses = []
                            for fc in message.tool_call.function_calls:
                                if fc.name not in ALLOWED_TOOLS:
                                    result = f"Tool not available for {agent['name']}."
                                elif fc.name == "show_artifact":
                                    args = _coerce_tool_args(fc.args)
                                    for artifact_type in ("url", "table", "charts"):
                                        val = _as_nonempty_str(args.get(artifact_type, ""))
                                        if val:
                                            await websocket.send_json({
                                                "type": "artifact",
                                                "artifact_type": artifact_type,
                                                "content": val,
                                            })
                                    result = "Artifact displayed on user screen."
                                else:
                                    result = await _execute_tool(fc.name, dict(fc.args))

                                responses.append(
                                    types.FunctionResponse(
                                        name=fc.name,
                                        id=fc.id,
                                        response={"result": result},
                                    )
                                )
                                await websocket.send_json({"type": "tool_result", "tool": fc.name, "result": result})

                            await session.send_tool_response(function_responses=responses)

            except Exception as e:
                log.debug("%s gemini recv closed: %s", agent["name"], e)

        await asyncio.gather(receive_from_browser(), receive_from_gemini(), send_greeting())


@router.websocket("/lara/voice")
async def lara_voice_legacy(websocket: WebSocket, session_id: str = "anon", language: str = DEFAULT_LANGUAGE):
    """Legacy Lara voice endpoint — delegates to the generic agent voice."""
    await agent_voice(websocket, "lara", session_id, language)
