"""In-memory session store."""

from __future__ import annotations

from intersection_agent.models.domain import Session


class SessionStore:
    """Thread-safe in-memory session repository."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        """Create and persist a new session."""
        session = Session()
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        """Fetch session by id."""
        return self._sessions.get(session_id)

    def save(self, session: Session) -> None:
        """Update session in store."""
        session.touch()
        self._sessions[session.session_id] = session
