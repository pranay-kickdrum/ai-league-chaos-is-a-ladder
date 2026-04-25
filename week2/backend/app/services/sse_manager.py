"""SSE event manager for streaming progress to the frontend."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SSEManager:
    """Manages SSE event streams per trip_id."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[str]]] = {}

    def subscribe(self, trip_id: str) -> asyncio.Queue[str]:
        """Create a new event queue for a subscriber."""
        if trip_id not in self._queues:
            self._queues[trip_id] = []
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._queues[trip_id].append(queue)
        logger.debug("SSE subscriber added for trip %s (total: %d)", trip_id, len(self._queues[trip_id]))
        return queue

    def unsubscribe(self, trip_id: str, queue: asyncio.Queue[str]) -> None:
        """Remove a subscriber's queue."""
        if trip_id in self._queues:
            self._queues[trip_id] = [q for q in self._queues[trip_id] if q is not queue]
            if not self._queues[trip_id]:
                del self._queues[trip_id]

    async def emit(self, trip_id: str, event_type: str, data: Any) -> None:
        """Broadcast an event to all subscribers of a trip."""
        if trip_id in self._queues:
            msg = {"type": event_type, "data": data}
            for queue in self._queues[trip_id]:
                await queue.put(msg)

    async def emit_phase_update(self, trip_id: str, phase: str, step: str, detail: str = "") -> None:
        await self.emit(trip_id, "phase_update", {"phase": phase, "step": step, "detail": detail})

    async def emit_agent_thinking(self, trip_id: str, agent: str, thought: str) -> None:
        await self.emit(trip_id, "agent_thinking", {"agent": agent, "thought": thought})

    async def emit_agent_step(
        self,
        trip_id: str,
        agent: str,
        step: str,
        detail: str = "",
        status: str = "running",
        substeps: list[str] | None = None,
    ) -> None:
        """Emit a structured live-status step for the agent activity panel.

        *status* can be: running | done | warning | waiting
        *substeps* is an optional list of completed sub-items for this agent.
        """
        await self.emit(
            trip_id,
            "agent_step",
            {
                "agent": agent,
                "step": step,
                "detail": detail,
                "status": status,
                "substeps": substeps or [],
            },
        )

    async def emit_research_partial(self, trip_id: str, source: str, data: Any) -> None:
        await self.emit(trip_id, "research_partial", {"source": source, "data": data})

    async def emit_api_degraded(self, trip_id: str, source: str, fallback: str, reason: str = "") -> None:
        await self.emit(trip_id, "api_degraded", {"source": source, "fallback_used": fallback, "reason": reason})

    async def emit_checkpoint(self, trip_id: str, data: Any) -> None:
        await self.emit(trip_id, "checkpoint", data)

    async def emit_plan_ready(self, trip_id: str, options: list[dict]) -> None:
        await self.emit(trip_id, "plan_ready", {"options": options})

    async def emit_itinerary_ready(self, trip_id: str, itinerary: dict) -> None:
        await self.emit(trip_id, "itinerary_ready", {"itinerary": itinerary})

    async def emit_map_update(self, trip_id: str, markers: list, routes: list) -> None:
        await self.emit(trip_id, "map_update", {"markers": markers, "routes": routes})

    async def emit_budget_update(self, trip_id: str, breakdown: dict) -> None:
        await self.emit(trip_id, "budget_update", {"breakdown": breakdown})

    async def emit_price_changed(self, trip_id: str, item: str, old_price: float, new_price: float) -> None:
        await self.emit(trip_id, "price_changed", {"item": item, "old_price": old_price, "new_price": new_price})

    async def emit_error(self, trip_id: str, message: str, recovery_options: list[str] | None = None) -> None:
        await self.emit(trip_id, "error", {"message": message, "recovery_options": recovery_options or []})

    async def emit_complete(self, trip_id: str, package: dict) -> None:
        await self.emit(trip_id, "complete", {"trip_package": package})


# Singleton
sse_manager = SSEManager()
