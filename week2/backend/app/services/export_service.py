"""PDF and HTML export service."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_jinja_env() -> Environment:
    """Get Jinja2 environment, creating templates dir if needed."""
    TEMPLATES_DIR.mkdir(exist_ok=True)

    # Write default template if missing
    template_path = TEMPLATES_DIR / "itinerary.html"
    if not template_path.exists():
        template_path.write_text(_DEFAULT_TEMPLATE)

    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )


def render_itinerary_html(
    itinerary_json: str,
    budget_json: str,
    request_json: str,
) -> str:
    """Render itinerary as HTML string."""
    env = _get_jinja_env()
    template = env.get_template("itinerary.html")

    itinerary = json.loads(itinerary_json) if itinerary_json else {}
    budget = json.loads(budget_json) if budget_json else {}
    request = json.loads(request_json) if request_json else {}

    return template.render(
        itinerary=itinerary,
        budget=budget,
        request=request,
    )


def render_itinerary_pdf(
    itinerary_json: str,
    budget_json: str,
    request_json: str,
) -> bytes:
    """Render itinerary as PDF bytes."""
    html = render_itinerary_html(itinerary_json, budget_json, request_json)
    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except ImportError:
        logger.warning("WeasyPrint not installed — returning HTML as fallback")
        return html.encode("utf-8")


# ---------------------------------------------------------------------------
# Default HTML template
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ itinerary.get('destination', 'Trip') }} – TripCraft Itinerary</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', -apple-system, sans-serif; color: #1a1a2e; background: #fefcf3; padding: 2rem; max-width: 800px; margin: auto; }
        h1 { font-family: 'Playfair Display', serif; color: #0891B2; margin-bottom: 0.5rem; }
        h2 { color: #F97316; margin: 1.5rem 0 0.5rem; border-bottom: 2px solid #FEF3C7; padding-bottom: 0.3rem; }
        h3 { color: #16A34A; margin: 1rem 0 0.3rem; }
        .summary { background: #f0f9ff; padding: 1rem; border-radius: 8px; margin: 1rem 0; }
        .day { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
        .activity { padding: 0.5rem 0; border-bottom: 1px dashed #e5e7eb; }
        .activity:last-child { border-bottom: none; }
        .cost { color: #F97316; font-weight: 600; }
        .budget-table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
        .budget-table td, .budget-table th { padding: 0.5rem; border: 1px solid #e5e7eb; text-align: left; }
        .budget-table th { background: #0891B2; color: white; }
        .total-row { font-weight: 700; background: #FEF3C7; }
        a { color: #0891B2; }
        .footer { margin-top: 2rem; text-align: center; color: #9ca3af; font-size: 0.875rem; }
    </style>
</head>
<body>
    <h1>🧳 {{ itinerary.get('destination', 'Trip') }}</h1>
    <p>{{ itinerary.get('duration_days', '?') }}-day {{ request.get('traveler_type', '') }} trip
       {% if request.get('styles') %} • {{ request.get('styles', [])|join(', ') }}{% endif %}</p>

    <div class="summary">
        <p>{{ itinerary.get('summary', '') }}</p>
        <p><strong>Budget:</strong> <span class="cost">{{ request.get('currency', '₹') }} {{ request.get('budget', 0) | int }}</span></p>
    </div>

    {% for day in itinerary.get('days', []) %}
    <div class="day">
        <h2>{{ day.get('title', 'Day ' ~ day.get('day_number', '')) }}</h2>
        <p>{{ day.get('description', '') }}</p>
        {% for act in day.get('activities', []) %}
        <div class="activity">
            <strong>{{ act.get('name', '') }}</strong>
            {% if act.get('cost', 0) > 0 %} — <span class="cost">₹{{ act.get('cost', 0) | int }}</span>{% endif %}
            {% if act.get('booking_url') %} | <a href="{{ act.get('booking_url') }}">Book</a>{% endif %}
            {% if act.get('maps_url') %} | <a href="{{ act.get('maps_url') }}">Map</a>{% endif %}
        </div>
        {% endfor %}
        <p class="cost" style="margin-top:0.5rem">Day total: ₹{{ day.get('day_cost', 0) | int }}</p>
    </div>
    {% endfor %}

    <h2>💰 Budget Breakdown</h2>
    <table class="budget-table">
        <tr><th>Category</th><th>Amount</th></tr>
        {% for key in ['travel','stay','food','activities','local_transport','entry_fees','buffer','misc'] %}
        {% if budget.get(key, 0) > 0 %}
        <tr><td>{{ key | replace('_',' ') | capitalize }}</td><td>₹{{ budget.get(key, 0) | int }}</td></tr>
        {% endif %}
        {% endfor %}
        <tr class="total-row"><td>Estimated Total</td><td>₹{{ itinerary.get('total_cost', 0) | int }}</td></tr>
    </table>

    <div class="footer">
        <p>Generated by TripCraft AI • {{ itinerary.get('destination', '') }}</p>
    </div>
</body>
</html>
"""
