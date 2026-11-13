DEFAULT_WEIGHTS = {"price": 50, "delivery": 25, "payment": 10, "reliability": 15}
NEUTRAL = 0.5
MAX_WEIGHT = 1000

from .reliability import reliability_stats, reliability_summary

class WeightError(Exception):
  def __init__(self, message, code="INVALID_WEIGHTS"):
    super().__init__(message)
    self.message = message
    self.code = code


def parse_weights(params):
  if not any(f"weight_{key}" in params for key in DEFAULT_WEIGHTS):
    return dict(DEFAULT_WEIGHTS)
  weights = {}
  for key in DEFAULT_WEIGHTS:
    raw = params.get(f"weight_{key}", "0")
    try:
      value = float(raw)
    except (TypeError, ValueError):
      value = -1
    if not 0 <= value <= MAX_WEIGHT:
      raise WeightError(f"weight_{key} must be a number from 0 to {MAX_WEIGHT}.")
    weights[key] = value
  return weights


def rank_quotations(quotations, weights):
  if not quotations:
    return []

  stats = reliability_stats(q.supplier_profile_id for q in quotations)
  created = quotations[0].rfq.created_at.date()
  prices = {q.pk: float(q.grand_total) for q in quotations}
  days = {q.pk: max((q.delivery_date - created).days, 1) for q in quotations}
  best_price = min(prices.values())
  best_days = min(days.values())

  raw = {}
  for q in quotations:
    price = prices[q.pk]
    advance_share = float(q.advance_amount) / price if price > 0 else 0.0
    history = stats.get(q.supplier_profile_id)
    raw[q.pk] = {
      "price": best_price / price if price > 0 else 1.0,
      "delivery": best_days / days[q.pk],
      "payment": max(0.0, 1.0 - advance_share),
      "reliability": history["score"] if history else None,
    }

  active = {
    key: weight for key, weight in weights.items()
    if weight > 0 and any(raw[q.pk][key] is not None for q in quotations)
  }
  total = sum(active.values())
  if total <= 0:
    raise WeightError("Give at least one scorable parameter a weight above 0.")

  results = []
  for q in quotations:
    score = 0.0
    breakdown = {}
    for key in DEFAULT_WEIGHTS:
      value = raw[q.pk][key]
      share = 0.0
      if key in active:
        share = active[key] / total
        score += (NEUTRAL if value is None else value) * share
        if value is None:
          value = NEUTRAL
      breakdown[key] = {
        "score": None if value is None else round(value * 100, 1),
        "weight": round(share * 100, 1),
      }

    results.append({
      "quotation": q,
      "score": round(score * 100, 1),
      "breakdown": breakdown,
      "reliability": reliability_summary(stats.get(q.supplier_profile_id)),
    })

  results.sort(key=lambda r: (
    -r["score"], r["quotation"].grand_total, r["quotation"].submitted_at
  ))

  earliest = min(q.delivery_date for q in quotations)
  for position, r in enumerate(results, start=1):
    q = r["quotation"]
    badges = []
    if position == 1:
      badges.append("recommended")
    if len(results) > 1:
      if prices[q.pk] == best_price:
        badges.append("cheapest")
      if q.delivery_date == earliest:
        badges.append("fastest")
    r["rank"] = position
    r["badges"] = badges
  return results
