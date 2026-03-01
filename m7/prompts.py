"""M7 Pairwise Comparison: prompt construction and response parsing."""

import re

from .config import PROMPT_METRICS


def _format_metrics_block(metrics_dict):
    """Format a stock's metrics dict into a readable text block."""
    lines = []
    for label in PROMPT_METRICS:
        value = metrics_dict.get(label)
        if value is None:
            continue
        if isinstance(value, float):
            if "Return" in label or "Margin" in label or "Yield" in label or label in ("ROE", "ROA"):
                lines.append(f"  {label}: {value * 100:.1f}%")
            else:
                lines.append(f"  {label}: {value:.2f}")
        else:
            lines.append(f"  {label}: {value}")
    return "\n".join(lines)


def build_prompt(stock_x_metrics, stock_y_metrics, variant="v1_direct"):
    """Build a prompt for the pairwise comparison task.

    Args:
        stock_x_metrics: dict of metric label -> value for Stock X
        stock_y_metrics: dict of metric label -> value for Stock Y
        variant: one of v1_direct, v2_cot, v3_expert, v4_structured

    Returns:
        tuple (system_prompt or None, user_prompt)
    """
    data_block = (
        f"Stock X:\n{_format_metrics_block(stock_x_metrics)}\n\n"
        f"Stock Y:\n{_format_metrics_block(stock_y_metrics)}"
    )

    if variant == "v1_direct":
        system = None
        user = (
            "Which stock will deliver higher total return over the next 6 months?\n\n"
            f"{data_block}\n\n"
            "Answer in this exact format:\n"
            "PICK: X or Y\n"
            "CONFIDENCE: 0.0 to 1.0\n"
            "REASONING: 2-3 sentences"
        )

    elif variant == "v2_cot":
        system = None
        user = (
            "Which stock will deliver higher total return over the next 6 months?\n"
            "Think step by step:\n"
            "1) Compare valuation metrics (P/E, P/B, EV/EBITDA)\n"
            "2) Compare profitability (ROE, ROA, margins)\n"
            "3) Compare financial health (D/E, Current Ratio, Piotroski)\n"
            "4) Compare momentum (trailing return, volatility)\n"
            "5) Make your decision\n\n"
            f"{data_block}\n\n"
            "After your analysis, conclude with:\n"
            "PICK: X or Y\n"
            "CONFIDENCE: 0.0 to 1.0\n"
            "REASONING: 2-3 sentence summary"
        )

    elif variant == "v3_expert":
        system = (
            "You are a senior quantitative analyst at a systematic hedge fund "
            "with 20 years of experience in factor-based equity selection. "
            "You evaluate stocks using fundamental data only, with no knowledge "
            "of company identity. Your decisions are driven by value, quality, "
            "and momentum factors."
        )
        user = (
            "Which anonymized stock will deliver higher total return over the next 6 months?\n\n"
            f"{data_block}\n\n"
            "Answer in this exact format:\n"
            "PICK: X or Y\n"
            "CONFIDENCE: 0.0 to 1.0\n"
            "REASONING: 2-3 sentences"
        )

    elif variant == "v4_structured":
        system = None
        user = (
            "Which stock will deliver higher total return over the next 6 months?\n\n"
            f"{data_block}\n\n"
            "Score each category 1-10 for both stocks:\n"
            "1. Valuation (lower P/E, P/B, EV/EBITDA = better)\n"
            "2. Profitability (higher ROE, ROA, margins = better)\n"
            "3. Financial Health (lower D/E, higher Current Ratio, higher Piotroski = better)\n"
            "4. Momentum (higher trailing return = better, lower volatility = better)\n"
            "5. Income Quality (higher FCF, dividend yield = better)\n\n"
            "Format:\n"
            "SCORES:\n"
            "  X: Valuation=?, Profitability=?, Health=?, Momentum=?, Quality=?\n"
            "  Y: Valuation=?, Profitability=?, Health=?, Momentum=?, Quality=?\n"
            "PICK: X or Y\n"
            "CONFIDENCE: 0.0 to 1.0\n"
            "REASONING: 2-3 sentences"
        )
    else:
        raise ValueError(f"Unknown prompt variant: {variant}")

    return system, user


def parse_response(text):
    """Parse an LLM response to extract pick, confidence, and reasoning.

    Returns:
        dict with keys: pick (str|None), confidence (float|None),
                        reasoning (str), parse_error (str|None)
    """
    result = {"pick": None, "confidence": None, "reasoning": "", "parse_error": None}

    if not text:
        result["parse_error"] = "Empty response"
        return result

    # Extract PICK
    pick_match = re.search(r"PICK:\s*([XYxy])", text)
    if pick_match:
        result["pick"] = pick_match.group(1).upper()
    else:
        # Fallback: look for "Stock X" or "Stock Y" or standalone X/Y near end
        fallback = re.search(r"(?:Stock|stock|choose|select|pick)\s+([XYxy])", text)
        if fallback:
            result["pick"] = fallback.group(1).upper()
        else:
            # Last resort: check if response ends with X or Y
            tail = text.strip()[-50:]
            last_xy = re.findall(r"\b([XY])\b", tail)
            if last_xy:
                result["pick"] = last_xy[-1]
            else:
                result["parse_error"] = "Could not extract pick (X or Y)"

    # Extract CONFIDENCE
    conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", text)
    if conf_match:
        try:
            conf = float(conf_match.group(1))
            if 0.0 <= conf <= 1.0:
                result["confidence"] = conf
            else:
                result["confidence"] = max(0.0, min(1.0, conf))
        except ValueError:
            pass

    # Extract REASONING
    reason_match = re.search(r"REASONING:\s*(.+)", text, re.DOTALL)
    if reason_match:
        result["reasoning"] = reason_match.group(1).strip()[:500]
    else:
        # Use last paragraph as reasoning
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if paragraphs:
            result["reasoning"] = paragraphs[-1][:500]

    return result
