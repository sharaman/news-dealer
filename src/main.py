"""CLI entry point for the News Agent."""
import uuid
import sys
from src.monitoring.callbacks import configure_logging

configure_logging()

import structlog
from src.data_plane.executor import run_agent

logger = structlog.get_logger()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="AI News Agent — generates Telegram posts from news")
    parser.add_argument("--message", "-m", type=str, help="User message / topic request")
    parser.add_argument("--session-id", type=str, default=None, help="Session ID (auto-generated if omitted)")
    parser.add_argument("--user-id", type=str, default="demo_user", help="User ID")
    parser.add_argument("--role", type=str, default="reader", choices=["reader", "viewer", "admin"])
    parser.add_argument("--publish", action="store_true", help="Опубликовать пост в Telegram-канал")
    args = parser.parse_args()

    session_id = args.session_id or str(uuid.uuid4())
    message = args.message

    if not message:
        print("Введите запрос (например: 'дай новости по AI и Python'):")
        message = input("> ").strip()
        if not message:
            print("Запрос пуст. Выход.")
            sys.exit(0)

    print(f"\n🤖 Агент запущен (session={session_id})\n{'='*60}")
    response = run_agent(
        message,
        session_id=session_id,
        user_id=args.user_id,
        role=args.role,
        publish=args.publish,
    )
    print(f"\n{response}\n{'='*60}")


if __name__ == "__main__":
    main()
