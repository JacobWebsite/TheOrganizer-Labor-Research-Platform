"""V10 Confidence / Reliability Indicator.

Predicts whether a demographic estimate is likely reliable based on
observable company characteristics (sector, county diversity tier, region).
Does NOT change any estimates -- only labels them.

Tiers:
  GREEN  -- High confidence, estimate is likely reliable
  YELLOW -- Moderate confidence, some uncertainty
  RED    -- Low confidence, take with a grain of salt

Validated on permanent holdout (954 companies):
  GREEN:  61.5%, Race MAE 3.64, P>20pp  9.1%
  YELLOW: 33.0%, Race MAE 5.20, P>20pp 23.0%
  RED:     5.5%, Race MAE 7.52, P>20pp 45.5%
  Separation ratio (RED P>20pp / GREEN P>20pp): 5.0:1

Also validated on V10 sealed holdout (never used in optimization):
  GREEN:  63.3%, Race MAE 3.56, P>20pp 10.7%
  YELLOW: 30.9%, Race MAE 5.36, P>20pp 24.3%
  RED:     5.8%, Race MAE 6.53, P>20pp 31.0%
  Sealed separation ratio: 2.9:1 (weaker but directionally correct)

Usage:
    from estimate_confidence import estimate_confidence
    tier = estimate_confidence(naics_group, diversity_tier, region)
"""

HIGH_ERROR_SECTORS = {
    "Healthcare/Social (62)",
    "Admin/Staffing (56)",
    "Transportation/Warehousing (48-49)",
    "Accommodation/Food Svc (72)",
}


def estimate_confidence(naics_group, diversity_tier, region):
    """Predict confidence in the demographic estimate for this company.

    Based on V9.2 error distribution analysis. Uses a points system:
      - County diversity tier: strongest predictor (0-4 points)
      - Sector: high-error sectors add 2 points
      - Region: West or South add 1 point

    Args:
        naics_group: str, e.g. "Healthcare/Social (62)"
        diversity_tier: str, one of "Low", "Med-Low", "Med-High", "High", "unknown"
        region: str, one of "South", "West", "Northeast", "Midwest"

    Returns:
        str: 'GREEN', 'YELLOW', or 'RED'
    """
    risk_points = 0

    # County diversity tier (strongest predictor)
    # Med-High has 25.2% P>20pp vs 4.0% for Low in V9.2 analysis
    if diversity_tier == "High":
        risk_points += 4
    elif diversity_tier == "Med-High":
        risk_points += 2
    elif diversity_tier == "Med-Low":
        risk_points += 1
    # Low and unknown = 0 points

    # Sector risk
    # Healthcare 25.6% P>20pp, Admin/Staffing 20.8%, Transportation 20%
    if naics_group in HIGH_ERROR_SECTORS:
        risk_points += 2

    # Regional risk
    # West 22.5% P>20pp, South 17.6%
    if region in ("West", "South"):
        risk_points += 1

    # Classification
    if risk_points >= 5:
        return "RED"      # Low confidence -- take with a grain of salt
    elif risk_points >= 3:
        return "YELLOW"   # Moderate confidence -- some uncertainty
    else:
        return "GREEN"    # High confidence -- estimate is likely reliable
