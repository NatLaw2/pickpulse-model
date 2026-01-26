from pydantic import BaseModel
from typing import Optional, List, Literal, Dict, Any

ConfidenceTier = Literal["low", "medium", "high"]

class MoneylineOdds(BaseModel):
    home: Optional[int] = None
    away: Optional[int] = None

class SpreadSide(BaseModel):
    point: Optional[float] = None
    price: Optional[int] = None

class SpreadOdds(BaseModel):
    home: Optional[SpreadSide] = None
    away: Optional[SpreadSide] = None

class TotalSide(BaseModel):
    point: Optional[float] = None
    price: Optional[int] = None

class TotalOdds(BaseModel):
    over: Optional[TotalSide] = None
    under: Optional[TotalSide] = None

class OddsData(BaseModel):
    moneyline: Optional[MoneylineOdds] = None
    spread: Optional[SpreadOdds] = None
    total: Optional[TotalOdds] = None

class Team(BaseModel):
    name: str
    abbreviation: Optional[str] = None

class GameIn(BaseModel):
    id: str
    sport: str
    homeTeam: Team
    awayTeam: Team
    startTime: str
    odds: OddsData

class PickPick(BaseModel):
    status: Literal["pick"]
    selection: str
    confidence: ConfidenceTier
    rationale: List[str]
    score: Optional[int] = None

class PickNoBet(BaseModel):
    status: Literal["no_bet"]
    reason: str
    score: Optional[int] = None

MarketRecommendation = PickPick | PickNoBet

class GameRecommendation(BaseModel):
    moneyline: MarketRecommendation
    spread: MarketRecommendation
    total: MarketRecommendation

class RecommendResponse(BaseModel):
    byGameId: Dict[str, GameRecommendation]
