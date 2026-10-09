"""API router for AI Business Assistant."""

from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.schemas.ai_assistant import (
    AIQueryRequestSchema,
    AIQueryResponseSchema,
    SuggestedQuerySchema,
)
from app.modules.ai_assistant.ai_service import AIAssistantService

router = APIRouter(prefix="/ai", tags=["AI Business Assistant"])


@router.post("/query", response_model=AIQueryResponseSchema)
async def ask_assistant(
    payload: AIQueryRequestSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Ask natural language questions to the shop's AI business assistant.
    
    Supported questions:
    - 'Which products made the most profit this month?' / 'இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?'
    - 'Who owes me money?' / 'யாருக்கு கடன் பாக்கி உள்ளது?'
    - 'Which items should I reorder?' / 'எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?'
    - 'How much did I sell today?' / 'இன்றைய விற்பனை எவ்வளவு?'
    - 'Which items are dead stock?' / 'விற்பனை ஆகாத தேக்கமடைந்த சரக்குகள் எவை?'
    - 'Customer summary for Suresh' / 'சுரேஷ் கணக்கு விவரம் என்ன?'
    - 'Whom do I owe money to?' / 'சப்ளையர்களுக்கு நான் கொடுக்க வேண்டிய தொகை எவ்வளவு?'
    """
    tenant_id = payload.tenant_id or get_current_tenant_id()
    return await AIAssistantService.process_query(
        session=session,
        tenant_id=tenant_id,
        query=payload.query,
        language=payload.language or "both",
    )


@router.get("/suggestions", response_model=List[SuggestedQuerySchema])
async def get_suggested_queries():
    """Retrieve curated prompt chips for one-click counter queries."""
    return [
        SuggestedQuerySchema(
            label_en="Top Profitable Products",
            label_ta="அதிக லாபம் தந்த பொருட்கள்",
            query="Which products made the most profit this month?",
        ),
        SuggestedQuerySchema(
            label_en="Who Owes Me Money?",
            label_ta="யாருக்கு கடன் பாக்கி உள்ளது?",
            query="Who owes me money?",
        ),
        SuggestedQuerySchema(
            label_en="Items to Reorder",
            label_ta="மீண்டும் ஆர்டர் செய்ய வேண்டியவை",
            query="Which items should I reorder?",
        ),
        SuggestedQuerySchema(
            label_en="Today's Sales Summary",
            label_ta="இன்றைய விற்பனை விவரம்",
            query="How much did I sell today?",
        ),
        SuggestedQuerySchema(
            label_en="Dead Stock Analysis",
            label_ta="விற்பனை ஆகாத தேக்க சரக்குகள்",
            query="Which items are dead stock?",
        ),
        SuggestedQuerySchema(
            label_en="Supplier Payables Due",
            label_ta="சப்ளையர் பாக்கிகள்",
            query="Whom do I owe money to?",
        ),
    ]
