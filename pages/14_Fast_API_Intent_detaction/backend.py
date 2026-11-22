"""
AT&T Fiber Agent Assist in-process service layer
Orchestrates Redis caching, rule-based propensity matching, Ollama AI generation, and CSV audit logging.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any
from dataclasses import dataclass

from dotenv import load_dotenv
import ollama
import redis

# ==========================================
# 1. ENVIRONMENT & CONFIGURATION SETUP
# ==========================================
# Resolve base directory path and load local environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# This module is an in-process service used by the Streamlit workspace.

# Define synthetic mock customer profiles representing active subscribers
SAMPLE_CUSTOMERS: dict[str, dict[str, Any]] = {
    "fiber_demo_10001": {"name": "Alex Morgan", "plan": "AT&T Fiber 1 GIG", "gateway": "BGW320", "status": "Degraded", "issue": "Planned neighborhood maintenance until 4:00 PM", "case": "NET-1042", "sentiment": "Frustrated"},
    "fiber_demo_10002": {"name": "Jordan Lee", "plan": "AT&T Fiber 500", "gateway": "BGW320", "status": "Online", "issue": "No known outage", "case": None, "sentiment": "Neutral"},
    "fiber_demo_10003": {"name": "Taylor Brooks", "plan": "AT&T Fiber 2 GIG", "gateway": "BGW320", "status": "Online", "issue": "Wi-Fi optimization opportunity", "case": "WIFI-2088", "sentiment": "Concerned"},
}
EVENT_CHANNEL = "att.fiber.agent-assist.events"
CSV_AUDIT_FILE = BASE_DIR / "agent_audit_log.csv"

# Read environment configurations for Redis connection and Ollama model selection
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
use_ollama = os.getenv("USE_OLLAMA", "true").strip().lower() in {"1", "true", "yes", "on"}


# ==========================================
# 2. INFRASTRUCTURE & DATA SCHEMAS
# ==========================================
def get_redis_client() -> redis.Redis | None:
    """Establish and test a connection to the Redis container database. Returns None if unreachable."""
    try:
        client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True, socket_connect_timeout=2, socket_timeout=4)
        client.ping()
        return client
    except redis.RedisError:
        return None


@dataclass
class ChatRequest:
    """Input payload for in-process customer chat processing."""
    customer_id: str
    message: str


# ==========================================
# 3. CSV AUDIT LOGGING UTILITIES
# ==========================================
def initialize_csv_file() -> None:
    """Ensure the local CSV audit file exists with pre-defined schema headers for tracking interactions."""
    if not CSV_AUDIT_FILE.exists():
        with open(CSV_AUDIT_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "InteractionId", "CreatedAtUtc", "CustomerId", "Intent", 
                "Sentiment", "CustomerMessage", "AiResponse", "SuggestedReply", 
                "CallSummary", "RecommendedOffer", "PropensityScore", "EventStatus"
            ])


def save_interaction_to_csv(record: dict[str, Any]) -> None:
    """Append a completed chat session and propensity record securely to the local CSV audit file."""
    initialize_csv_file()
    with open(CSV_AUDIT_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            record["id"],
            datetime.now(timezone.utc).isoformat(),
            record["customer_id"],
            record["intent"],
            record["sentiment"],
            record["message"],
            record["response"],
            record["reply"],
            record["summary"],
            record.get("offer", "None"),
            record.get("score", "0%"),
            "published"
        ])


# ==========================================
# 4. NLP CLASSIFICATION & PROPENSITY ENGINE
# ==========================================
def classify_sentiment(text: str) -> str:
    """Analyze text using regex patterns to categorize customer emotional sentiment."""
    normalized = re.sub(r"[^a-z0-9\s']", " ", text.lower())
    frustrated_patterns = (
        r"\b(?:angry|annoyed|frustrated|furious|upset|disappointed|unacceptable)\b",
        r"\b(?:terrible|awful|horrible|worst|ridiculous|useless)\b",
        r"\b(?:not working|doesn'?t work|cannot connect|can'?t connect|keeps? (?:dropping|disconnecting|buffering))\b",
    )
    concerned_patterns = (
        r"\b(?:slow|intermittent|unstable|poor|weak)\b",
        r"\b(?:issue|problem|trouble|help|concerned|worried)\b",
    )
    positive_patterns = (
        r"\b(?:thank you|thanks|great|excellent|perfect|appreciate|resolved|working now)\b",
    )
    if any(re.search(p, normalized) for p in frustrated_patterns):
        return "frustrated"
    if any(re.search(p, normalized) for p in concerned_patterns):
        return "concerned"
    if any(re.search(p, normalized) for p in positive_patterns):
        return "positive"
    return "neutral"


def detect_intent(message: str) -> tuple[str, str]:
    """Scan message keywords to categorize support intent and route text to sentiment classification."""
    text = message.lower()
    if any(w in text for w in ("slow", "wifi", "internet", "disconnect", "outage")):
        intent = "fiber_connectivity"
    elif any(w in text for w in ("bill", "charge", "payment", "price")):
        intent = "billing_inquiry"
    elif any(w in text for w in ("install", "appointment", "technician")):
        intent = "appointment_support"
    else:
        intent = "Support"
    return intent, classify_sentiment(text)


def evaluate_cross_sell_propensity(profile: dict[str, Any], intent: str, sentiment: str) -> tuple[str, str, str]:
    """Determine the Next Best Offer (NBO) and propensity score using business logic rules based on plan and context."""
    plan = profile.get("plan", "")
    if "500" in plan:
        if intent == "fiber_connectivity" or sentiment in ("neutral", "positive"):
            return "AT&T Fiber 1 GIG Speed Tier Upgrade", "88% (High)", "Customer is on a mid-tier plan inquiring about speed/service."
        else:
            return "AT&T In-Home Wi-Fi Mesh Extender", "65% (Medium)", "Customer experiencing friction. Propose Wi-Fi hardware stabilization."
    elif "1 GIG" in plan:
        if intent == "appointment_support" or sentiment in ("positive", "neutral"):
            return "AT&T Fiber 2 GIG Multi-Gig Tier", "82% (High)", "High-value subscriber demonstrating interest in optimal performance."
        else:
            return "AT&T ActiveArmor Advanced Security Bundle", "70% (Medium)", "Offer security features to add value."
    else:
        return "AT&T Fiber Family Bundle & Wi-Fi Extender", "75% (Medium)", "General cross-sell opportunity."


# ==========================================
# 5. LLM & FALLBACK GENERATION LOGIC
# ==========================================
def local_assist(profile: dict[str, Any], message: str, intent: str) -> tuple[str, str, str]:
    """Generate rule-based deterministic response fallback if the local LLM service is offline."""
    action = "check the service status and guide the customer through a gateway and Wi-Fi health check"
    if profile["status"] == "Degraded":
        action = "acknowledge the known maintenance window and set clear restoration expectations"
    response = f"I understand the disruption is frustrating. Your {profile['plan']} service is currently marked {profile['status'].lower()}. The next best step is to {action}."
    reply = "I’m sorry you’re dealing with this. I’ve reviewed the service context and will help you right now."
    summary = f"{intent}; customer reported: {message}. Service context: {profile['status']}. Recommended action: {action}."
    return response, reply, summary


def ollama_assist(profile: dict[str, Any], message: str, intent: str) -> tuple[str, str, str]:
    """Interact with local Ollama LLM to produce context-aware AI text responses, replies, and summaries."""
    prompt = f"""You are an AT&T Fiber customer-care agent assist tool. Use only this synthetic context.
Customer: {json.dumps(profile)}
Customer message: {message}
Detected intent: {intent}
Return exactly three labeled short lines: AI Response:, Suggested Reply:, Call Summary:."""
    try:
        content = ollama.chat(model=ollama_model, messages=[{"role": "user", "content": prompt}])["message"]["content"].strip()
        lines = {}
        for key in ("AI Response", "Suggested Reply", "Call Summary"):
            match = re.search(rf"{key}:\s*(.*?)(?=\n(?:AI Response|Suggested Reply|Call Summary):|\Z)", content, re.S | re.I)
            lines[key] = match.group(1).strip() if match else ""
        if not all(lines.values()):
            return local_assist(profile, message, intent)
        return lines["AI Response"], lines["Suggested Reply"], lines["Call Summary"]
    except Exception:
        return local_assist(profile, message, intent)


# ==========================================
# 6. IN-PROCESS SERVICE FUNCTIONS
# ==========================================
def get_customers() -> dict[str, dict[str, Any]]:
    """Return available customer profiles without requiring a separate API server."""
    return SAMPLE_CUSTOMERS


def process_chat(payload: ChatRequest) -> dict[str, Any]:
    """Process a customer chat directly inside the Streamlit application."""
    client = get_redis_client()
    customer_id = payload.customer_id
    message = payload.message.strip()
    if not message:
        raise ValueError("Customer message cannot be empty.")

    profile = SAMPLE_CUSTOMERS.get(customer_id, SAMPLE_CUSTOMERS["fiber_demo_10001"])
    if client:
        raw = client.get(f"att:fiber:customer:{customer_id}")
        if raw:
            profile = json.loads(raw)

    intent, sentiment = detect_intent(message)
    offer, score, rationale = evaluate_cross_sell_propensity(profile, intent, sentiment)
    if use_ollama:
        response, reply, summary = ollama_assist(profile, message, intent)
        engine = f"Ollama · {ollama_model}"
    else:
        response, reply, summary = local_assist(profile, message, intent)
        engine = "Deterministic fallback"

    record = {
        "id": str(uuid.uuid4()),
        "customer_id": customer_id,
        "intent": intent,
        "sentiment": sentiment,
        "message": message,
        "response": response,
        "reply": reply,
        "summary": summary,
        "offer": offer,
        "score": score,
    }

    pubsub_note = "Redis not connected"
    if client:
        try:
            client.publish(EVENT_CHANNEL, json.dumps({**record, "event_type": "agent_assist.completed", "created_at": datetime.now(timezone.utc).isoformat()}))
            client.lpush(f"att:fiber:memory:{customer_id}", json.dumps(record))
            client.ltrim(f"att:fiber:memory:{customer_id}", 0, 19)
            pubsub_note = "Published"
        except redis.RedisError as exc:
            pubsub_note = f"Publish failed: {exc}"

    try:
        save_interaction_to_csv(record)
        csv_note = "Saved"
    except Exception as exc:
        csv_note = f"Save failed: {str(exc)[:90]}"

    return {
        "record": record,
        "engine": engine,
        "pubsub_note": pubsub_note,
        "csv_note": csv_note,
        "profile": profile,
        "rationale": rationale,
    }
