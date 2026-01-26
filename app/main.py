from fastapi import FastAPI, Header, HTTPException
from typing import List, Optional

from .config import settings
from .schema import GameIn, RecommendResponse
from .model_nba import recommend_nba

app = FastAPI(title="PickPulse Model API", version="0.1.0")

@app.get("/health")
def health():
    return {"ok": True}

def require_key(x_model_key: Optional[str]):
    if not settings.MODEL_API_KEY:
        # Allow dev runs without a key if not set
        return
    if not x_model_key or x_model_key != settings.MODEL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/v1/nba/recommendations", response_model=RecommendResponse)
def nba_recommendations(
    games: List[GameIn],
    x_model_key: Optional[str] = Header(default=None),
):
    require_key(x_model_key)
    by_game_id = recommend_nba(games)
    return {"byGameId": by_game_id}
