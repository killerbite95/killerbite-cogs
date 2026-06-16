"""Data models for RustMaps Vote COG. By Killerbite95"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

# Constraints on a vote session
MAX_MAPS = 5
MIN_MAPS = 2
# How many maps a single user may vote for, by default. Configurable per guild.
DEFAULT_MAX_VOTES_PER_USER = 1


@dataclass
class MapInfo:
    """A single rustmaps.com map entered into a vote session."""

    map_id: int  # position index within the session (1, 2, 3...)
    size: int
    seed: int
    url: str
    thumbnail_url: Optional[str] = None
    map_type: Optional[str] = None
    vote_count: int = 0

    @classmethod
    def from_api_response(cls, data: Dict[str, Any], position: int, url: str) -> "MapInfo":
        """Create a MapInfo from a RustMaps API v4 response."""
        resp = data.get("response", data)  # unwrap ServiceResponse if present
        params = resp.get("mapParameters", {})
        thumbnail = (
            resp.get("thumbnailUrl")
            or resp.get("imageUrl")
            or resp.get("imageIconUrl")
        )
        return cls(
            map_id=position,
            size=params.get("size", 0),
            seed=params.get("seed", 0),
            url=url,
            thumbnail_url=thumbnail,
            map_type=params.get("type"),
            vote_count=0,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "map_id": self.map_id,
            "size": self.size,
            "seed": self.seed,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
            "map_type": self.map_type,
            "vote_count": self.vote_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MapInfo":
        return cls(
            map_id=data["map_id"],
            size=data.get("size", 0),
            seed=data.get("seed", 0),
            url=data.get("url", ""),
            thumbnail_url=data.get("thumbnail_url"),
            map_type=data.get("map_type"),
            vote_count=data.get("vote_count", 0),
        )


@dataclass
class VoteSession:
    """An active or in-progress map vote within a guild."""

    session_id: int
    maps: List[MapInfo] = field(default_factory=list)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    channel_id: Optional[int] = None
    voting_message_id: Optional[int] = None
    max_votes_per_user: int = DEFAULT_MAX_VOTES_PER_USER
    # user_id (as str, since Config/JSON keys are strings) -> list of map_ids they voted for
    votes: Dict[str, List[int]] = field(default_factory=dict)

    # --- Map management (used before voting starts) ---

    def get_map(self, map_id: int) -> Optional[MapInfo]:
        for m in self.maps:
            if m.map_id == map_id:
                return m
        return None

    def has_duplicate(self, size: int, seed: int) -> bool:
        return any(m.size == size and m.seed == seed for m in self.maps)

    def add_map(self, map_info: MapInfo) -> bool:
        """Append a map, respecting MAX_MAPS. Reassigns its position index."""
        if len(self.maps) >= MAX_MAPS:
            return False
        map_info.map_id = len(self.maps) + 1
        self.maps.append(map_info)
        return True

    def remove_map(self, map_id: int) -> bool:
        """Remove a map by position and renumber the rest to stay contiguous."""
        for i, m in enumerate(self.maps):
            if m.map_id == map_id:
                self.maps.pop(i)
                self._renumber()
                # Positions shifted, so any existing votes are no longer valid.
                self.votes = {}
                self._apply_counts()
                return True
        return False

    def _renumber(self) -> None:
        for index, m in enumerate(self.maps, start=1):
            m.map_id = index

    # --- Voting (used after voting starts) ---

    def get_user_votes(self, user_id: int) -> List[int]:
        return list(self.votes.get(str(user_id), []))

    def toggle_vote(self, user_id: int, map_id: int) -> str:
        """Register or undo a user's vote for a map.

        Returns one of:
          - "invalid": map_id is not part of this session
          - "removed": the user had already voted this map; vote withdrawn
          - "limit":   the user has no votes left and clicked a new map
          - "added":   the vote was registered
        """
        if self.get_map(map_id) is None:
            return "invalid"

        key = str(user_id)
        user_votes = self.votes.setdefault(key, [])

        if map_id in user_votes:
            user_votes.remove(map_id)
            if not user_votes:
                del self.votes[key]
            self._apply_counts()
            return "removed"

        if len(user_votes) >= self.max_votes_per_user:
            return "limit"

        user_votes.append(map_id)
        self._apply_counts()
        return "added"

    def _apply_counts(self) -> None:
        """Recompute each map's vote_count from the authoritative votes dict."""
        counts: Dict[int, int] = {m.map_id: 0 for m in self.maps}
        for map_ids in self.votes.values():
            for mid in map_ids:
                if mid in counts:
                    counts[mid] += 1
        for m in self.maps:
            m.vote_count = counts.get(m.map_id, 0)

    @property
    def total_voters(self) -> int:
        return len(self.votes)

    @property
    def total_votes(self) -> int:
        return sum(len(v) for v in self.votes.values())

    def get_ranking(self) -> List[MapInfo]:
        """Maps sorted by vote_count, highest first."""
        return sorted(self.maps, key=lambda m: m.vote_count, reverse=True)

    def get_winner(self) -> Optional[MapInfo]:
        if not self.maps:
            return None
        return self.get_ranking()[0]

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "maps": [m.to_dict() for m in self.maps],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "channel_id": self.channel_id,
            "voting_message_id": self.voting_message_id,
            "max_votes_per_user": self.max_votes_per_user,
            "votes": {k: list(v) for k, v in self.votes.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoteSession":
        maps = [MapInfo.from_dict(m) for m in data.get("maps", [])]
        started = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        ended = datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None
        votes = {str(k): [int(x) for x in v] for k, v in data.get("votes", {}).items()}
        session = cls(
            session_id=data["session_id"],
            maps=maps,
            started_at=started,
            ended_at=ended,
            channel_id=data.get("channel_id"),
            voting_message_id=data.get("voting_message_id"),
            max_votes_per_user=data.get("max_votes_per_user", DEFAULT_MAX_VOTES_PER_USER),
            votes=votes,
        )
        session._apply_counts()
        return session
