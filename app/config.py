from pydantic import BaseModel
import os

class Settings(BaseModel):
    # Simple shared-secret auth from Supabase -> Model API
    MODEL_API_KEY: str = os.getenv("MODEL_API_KEY", "")

    # Elo config (NBA v1)
    HOME_ADV_ELO: float = float(os.getenv("HOME_ADV_ELO", "65"))  # typical NBA HFA
    MIN_EDGE_ML: float = float(os.getenv("MIN_EDGE_ML", "0.03"))  # 3% edge
    MIN_EDGE_SPREAD: float = float(os.getenv("MIN_EDGE_SPREAD", "1.5"))  # points edge

    # Confidence tier thresholds (0-100)
    TIER_HIGH: int = int(os.getenv("TIER_HIGH", "75"))
    TIER_MED: int = int(os.getenv("TIER_MED", "60"))

settings = Settings()
