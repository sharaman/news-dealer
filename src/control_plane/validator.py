"""Anti-injection and request validation (Control Plane)."""
import re
import structlog

logger = structlog.get_logger()

# Prompt injection patterns
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|prior|above|all)\s+(instructions?|prompts?|rules?|constraints?)",
    r"forget\s+(everything|all|previous|prior)",
    r"you\s+are\s+now\s+(a|an)\s+\w+",
    r"act\s+as\s+(if\s+you\s+are|a|an)\s+",
    r"new\s+(instructions?|system\s+prompt|role|persona)",
    r"disregard\s+(your|the|all)\s+",
    r"override\s+(your|the|all)\s+",
    r"do\s+not\s+follow\s+(your|the)\s+",
    r"jailbreak",
    r"prompt\s+injection",
    r"</?(system|instruction|prompt)>",
    r"\[INST\]",
    r"<\|im_start\|>",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Patterns that suggest user is trying to change sources (EN + RU)
_SOURCE_MANIPULATION_PATTERNS = [
    r"(add|use|include|fetch|read|subscribe)\s+(from\s+)?(reddit|twitter|x\.com|hackernews|hn|youtube|instagram|tiktok|rss|url|https?://)",
    r"(change|modify|update|set)\s+(the\s+)?(source|sources|feed|feeds|channel|channels)",
    r"instead\s+of\s+(medium|telegram)",
    r"(new|different|another)\s+(source|feed|channel)",
    # Russian patterns
    r"(используй|добавь|включи|читай|подключи|возьми)\s+.*(reddit|twitter|hackernews|youtube|instagram|tiktok|https?://)",
    r"(вместо|замени|поменяй)\s+.*(medium|telegram|источник)",
    r"(измени|добавь|удали|поменяй)\s+(источник|источники|канал|каналы|фид)",
]

_SOURCE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SOURCE_MANIPULATION_PATTERNS]


def check_injection(text: str) -> tuple[bool, str]:
    """Returns (is_safe, reason). is_safe=True means no injection detected."""
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            logger.warning("injection_detected", pattern=pattern.pattern, text_snippet=text[:100])
            return False, f"Запрос содержит потенциально опасный паттерн: '{pattern.pattern}'"
    return True, ""


def check_source_manipulation(text: str) -> tuple[bool, str]:
    """Returns (is_safe, reason). is_safe=True means user is not trying to change sources."""
    for pattern in _SOURCE_PATTERNS:
        if pattern.search(text):
            logger.warning("source_manipulation_detected", pattern=pattern.pattern)
            return False, "Изменение состава источников не разрешено. Используйте только предустановленные источники."
    return True, ""


def validate_request(text: str, max_length: int = 1000) -> tuple[bool, str]:
    """Full validation pipeline. Returns (valid, error_message)."""
    if not text or not text.strip():
        return False, "Запрос не может быть пустым."

    if len(text) > max_length:
        return False, f"Запрос слишком длинный. Максимум {max_length} символов."

    safe, reason = check_injection(text)
    if not safe:
        return False, reason

    safe, reason = check_source_manipulation(text)
    if not safe:
        return False, reason

    return True, ""
