"""CLI entry point for qobuz auth."""

from __future__ import annotations

import asyncio
import argparse
import sys

from .auth import login, load_credentials, CREDENTIALS_FILE


def main():
    parser = argparse.ArgumentParser(prog="qobuz", description="Qobuz API client CLI")
    sub = parser.add_subparsers(dest="command")

    # auth login
    login_parser = sub.add_parser("login", help="Authenticate with Qobuz")
    login_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser (for headless/remote machines)",
    )
    login_parser.add_argument(
        "--port",
        type=int,
        default=11111,
        help="Local callback port (default: 11111)",
    )

    # auth status
    sub.add_parser("status", help="Show authentication status")

    # auth token
    sub.add_parser("token", help="Print the saved auth token")

    args = parser.parse_args()

    if args.command == "login":
        asyncio.run(login(port=args.port, no_browser=args.no_browser))
    elif args.command == "status":
        creds = load_credentials()
        if creds:
            print(f"Logged in as: {creds.get('display_name', 'unknown')}")
            print(f"User ID: {creds.get('user_id', 'unknown')}")
            print(f"Credentials: {CREDENTIALS_FILE}")
        else:
            print("Not authenticated. Run: qobuz login")
    elif args.command == "token":
        creds = load_credentials()
        if creds:
            print(creds["user_auth_token"])
        else:
            print("Not authenticated. Run: qobuz login", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
