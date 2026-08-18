import time

import requests

from config import (
    OLLAMA_URL,
    MODEL_NAME,
    OLLAMA_TIMEOUT,
    OLLAMA_MAX_RETRIES,
    AUDIENCE,
)


def generate_script(topic):

    prompt = f"""
        Create a YouTube Shorts narration.

        Audience:
        {AUDIENCE}

        Topic:
        {topic}

        Requirements:

        - Length: approximately 100-120 words.
        - Fun, exciting and educational.
        - Simple English.
        - The FIRST sentence must be a powerful hook.
        - The hook must immediately create curiosity.
        - Prefer a surprising question, shocking fact, mystery,
        or "Can you believe...?" style opening.
        - Do not waste the first few seconds introducing the topic.
        - Reveal the interesting fact quickly.
        - Keep the narration fast and engaging.
        - End with a memorable fact or conclusion.

        IMPORTANT:

        Return ONLY spoken narration.

        DO NOT include:
        - Title
        - Topic heading
        - Sound suggestions
        - Sound effects
        - Music suggestions
        - Visual suggestions
        - Scene descriptions
        - Animation instructions
        - Production notes
        - Markdown
        - Bullet points
        - Labels such as "Narration:", "Sound:", "Topic:",
        "Scene:", etc.
        - Anything inside brackets or braces

        Example of a GOOD opening:

        "Did you know a tiny bee can tell its friends where
        to find food?"

        Example of a BAD opening:

        "Today we are going to learn about bees."

        Return ONLY the narration.
        """

    unwanted_prefixes = [
        "narration:",
        "script:",
        "sound suggestion:",
        "sound:",
        "music suggestion:",
        "music:",
        "topic:",
    ]

    last_error = None

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):

        try:

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=OLLAMA_TIMEOUT
            )

            response.raise_for_status()

            result = response.json()["response"].strip()

            # ------------------------------------------------
            # Defensive cleanup
            # ------------------------------------------------

            lines = result.splitlines()

            cleaned_lines = []

            for line in lines:

                clean = line.strip()

                if not clean:
                    continue

                lower = clean.lower()

                if any(
                    lower.startswith(prefix)
                    for prefix in unwanted_prefixes
                ):
                    continue

                if clean.startswith("#"):
                    continue

                cleaned_lines.append(clean)

            result = " ".join(cleaned_lines).strip()

            if len(result.split()) < 20:
                raise ValueError(
                    "Generated script looks too short "
                    f"({len(result.split())} words)."
                )

            return result

        except Exception as exc:

            last_error = exc

            print(f"Script generation attempt {attempt} failed: {exc}")

            if attempt < OLLAMA_MAX_RETRIES:
                time.sleep(attempt * 2)

    raise RuntimeError(
        f"Unable to generate a script after {OLLAMA_MAX_RETRIES} "
        f"attempts: {last_error}"
    )
