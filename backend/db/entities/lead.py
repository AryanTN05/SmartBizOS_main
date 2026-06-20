from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.sql import func
from db.connection import Base
import uuid

class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    company_name = Column(String)       # Human-readable display name e.g. "Stripe"
    company_domain = Column(String)     # Root domain e.g. "stripe.com" — used for enrichment
    title = Column(String)
    linkedin_url = Column(String)
    
    status = Column(String, nullable=False, default='new')
    
    score = Column(Integer, default=0)
    score_reason = Column(Text)
    
    source = Column(String, nullable=False, default='manual')
    source_ref_id = Column(String)
    
    notes = Column(Text)
    tags = Column(ARRAY(String), default=list)

    # AI-generated personalized opening sentence grounded in the lead's
    # source signal (PH launch, YC batch, HN post, GitHub trending). NULL
    # = not yet generated; user can regenerate or hand-edit. Threaded into
    # email templates as the {{opening_line}} variable.
    opening_line = Column(Text)
    opening_line_generated_at = Column(DateTime(timezone=True), nullable=True)

    # Sequence-state machine for reply-detection. Without this the scheduler
    # keeps firing send_* steps even after a prospect replied, which is the
    # #1 reason solo founders ditch outbound automation. Values:
    #   active           — sequence runs as scheduled
    #   paused_replied   — prospect replied, halt sends
    #   paused_manual    — user paused via UI
    #   completed        — sequence ran to end
    sequence_state = Column(String, nullable=False, default='active')
    last_reply_at = Column(DateTime(timezone=True), nullable=True)

    # LLM-classified intent for the most-recent reply. NULL = no reply yet
    # or classifier unavailable. Values: positive, negative, neutral,
    # wrong_person, unsubscribe, auto_reply. Surfaced as a chip on the lead
    # card and as an Inbox filter so the SDR triages hottest replies first.
    last_reply_intent = Column(String, nullable=True)

    # Detected buying-intent triggers from the source enrichment (hiring,
    # funding, tech-stack-change, etc). List of strings. Each trigger adds
    # a score multiplier and renders as a badge on the lead card.
    triggers = Column(JSONB, nullable=True)

    # A/B opener variants. List of {text, sent_count, replied_count,
    # generated_at_unix}. The active variant is mirrored to opening_line;
    # the scheduler rotates among variants until each has 3+ sends, then
    # picks the highest reply rate. Zero-sample variants get explored
    # first (cheap epsilon-greedy without the math overhead).
    opening_line_variants = Column(JSONB, nullable=True)

    # Set when the recipient hit the 1-click unsubscribe link or was
    # added to the suppression list. The scheduler hard-blocks any
    # send_* step when this is non-NULL.
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True)   # Soft delete — NULL means active

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_activity = Column(DateTime(timezone=True), server_default=func.now())
