# 🏆 AI League #2: Agentic Workflow Building

## Problem Statement: AI Travel Planning & Booking Agent

---

## 📌 Background

Planning a trip is overwhelming. Between researching destinations, comparing flights, finding hotels, booking activities, checking weather, managing budgets, and coordinating logistics—travelers spend hours (sometimes days) piecing together their perfect itinerary.

What if an AI agent system could handle this entire workflow autonomously? Research destinations, find the best deals, create day-by-day itineraries, coordinate bookings, and adapt to your preferences—all while keeping you in the loop for approvals.

This hackathon focuses on building multi-agent systems that can autonomously plan, research, optimize, and coordinate complex real-world tasks. You'll explore how agents can collaborate, make trade-off decisions, handle external APIs, and produce actionable outputs.

---

## 🎯 Challenge

Build an **AI Travel Planning & Booking Agent System** that takes a traveller's preferences and produces a complete, actionable travel plan through intelligent agent collaboration.

**Example Input:**
> "Plan a 4-day solo backpacking trip to Rishikesh under ₹15,000. I love adventure sports and spiritual experiences. Traveling from Delhi next weekend."

**Expected Output:**

A complete, reviewable, and actionable **Trip Execution Package** containing:

- Day-by-day itinerary (with timings + travel duration)
- Budget breakdown (transport, stay, food, activities)
- Booking-ready options (flights, hotels, activities)
- Review checkpoints with alternative choices

---

## Your System Must:

1. **Understand Traveler Intent:** Parse preferences (budget, travel style, interests, constraints)
2. **Multi-Agent Workflow:** Design agents that collaborate to research, plan, optimize, and coordinate (you decide the architecture!)
3. **Real-World Data:** Fetch live data from multiple sources (flights, hotels, weather, activities, reviews)
4. **Smart Decision-Making:** Balance trade-offs (budget vs comfort, distance vs experience, time vs cost)
5. **Transparency:** Show agent reasoning, research process, and decision logs
6. **Human-in-the-Loop:** Get approvals at key stages (destination selection, budget allocation, bookings)
7. **Actionable Outputs:** Provide booking links, maps, contact info—not just suggestions
8. **Dynamic Re-planning:** *"My flight got delayed by 4 hours, adjust my Day 1 plan"*

**You decide:**

- How many agents? (Research? Budget Optimizer? Booking Coordinator? Route Planner? Your call!)
- What tools/APIs? (Google Places, Weather APIs, Flight/Hotel scrapers, Maps)
- What orchestration? (Sequential? Parallel? Conditional?)
- What travel niches? (Solo backpacking? Family trips? Day trips? Luxury? Adventure? Cultural?)

---

## 🖥 Deployment Requirement

The solution can be deployed through any interface:

- Streamlit/Gradio web app *(recommended for visual itineraries)*
- CLI tool with rich formatted outputs
- Web app (Flask/Next.js)
- Chat interface (conversational planning experience)
- API endpoint with structured responses

The output must be:

- **Downloadable** (PDF/JSON/HTML itinerary)
- **Actionable** (direct booking links, maps, contact info)

---

## 🎁 Bonus Goals

1. **Visual Itinerary:** Interactive map showing route, hotels, activities with day-wise color coding
2. **Local Insider Tips:** Scrape Reddit/travel blogs for hidden gems and local recommendations

---

## ⚠️ Constraints & Rules

- Plans must be realistic (travel times, opening hours, feasibility)
- All suggestions must include pricing and booking links
- Must show reasoning transparency (why this hotel? why this route?)
- Must handle edge cases (no direct flights, budget too low, activities fully booked)
- If data is unavailable, agents must find alternatives or notify user clearly
- Must include human approval checkpoints (destination shortlist, budget allocation, final itinerary)
- No hallucinated hotels/activities—all suggestions must be verifiable

---

## 📦 Expected Deliverables

Each team must submit:

1. **Working demo application** (your agent system interface)

2. **2–3 sample travel plans** showcasing different travel styles:
   - Solo backpacking trip (adventure/budget)
   - Family vacation (comfort/activities)
   - Weekend getaway / Day trip (quick planning)

3. **Architecture diagram** showing:
   - Agent roles and responsibilities
   - Data sources and APIs used
   - Workflow orchestration logic
   - Decision-making process
   - Human-in-the-loop integration points

4. **Technical explanation** covering:
   - Framework/tools used (LangGraph/CrewAI/AutoGen/Google ADK/Deep Agents/custom)
   - How agents collaborate and share context
   - Handling real-time data (flights, weather, availability)
   - Budget optimization strategy
   - Why you chose this architecture