"""RBAC and source policy enforcement (Control Plane)."""
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()

# Role definitions — deterministic, not user-configurable
ROLES: dict[str, dict] = {
    "reader": {
        "can_fetch_medium": True,
        "can_fetch_telegram": True,
        "can_generate_post": True,
        "max_articles_per_request": 10,
    },
    "viewer": {
        "can_fetch_medium": True,
        "can_fetch_telegram": False,
        "can_generate_post": False,
        "max_articles_per_request": 5,
    },
    "admin": {
        "can_fetch_medium": True,
        "can_fetch_telegram": True,
        "can_generate_post": True,
        "max_articles_per_request": 20,
    },
}


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""
    allowed_medium_topics: list[str] = field(default_factory=list)
    allowed_telegram_channels: list[str] = field(default_factory=list)
    max_articles: int = 10


def check_permissions(
    user_id: str,
    role: str,
    allowed_medium_topics: list[str],
    allowed_telegram_channels: list[str],
) -> PolicyDecision:
    """Determine if the user/role is allowed to proceed and which sources are accessible."""
    if role not in ROLES:
        logger.warning("unknown_role", user_id=user_id, role=role)
        return PolicyDecision(allowed=False, reason=f"Неизвестная роль: {role}")

    permissions = ROLES[role]

    accessible_medium = allowed_medium_topics if permissions["can_fetch_medium"] else []
    accessible_telegram = allowed_telegram_channels if permissions["can_fetch_telegram"] else []

    if not accessible_medium and not accessible_telegram:
        return PolicyDecision(
            allowed=False,
            reason="Для вашей роли не доступны источники данных.",
        )

    logger.info("policy_allowed", user_id=user_id, role=role)
    return PolicyDecision(
        allowed=True,
        allowed_medium_topics=accessible_medium,
        allowed_telegram_channels=accessible_telegram,
        max_articles=permissions["max_articles_per_request"],
    )
