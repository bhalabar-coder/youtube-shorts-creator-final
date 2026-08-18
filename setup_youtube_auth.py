"""
Run this once to authenticate with YouTube and cache a refresh token
at credentials/token.json. After that, main.py can upload videos
without opening a browser every time (needed for cron/automation).
"""

from agents.youtube_agent import get_credentials


def main():

    get_credentials()

    print("Authentication successful. Token cached at credentials/token.json")


if __name__ == "__main__":
    main()
