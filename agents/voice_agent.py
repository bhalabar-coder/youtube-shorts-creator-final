import asyncio
import os

import edge_tts

# en-US-AriaNeural (the old default) reads news-style — energetic and a
# bit clipped. en-US-JennyNeural is Microsoft's warm/friendly assistant
# voice, which reads noticeably softer and more conversational.
#
# Other good "soft" options if you want to try alternatives:
#   en-US-AnaNeural      — gentle, slightly younger-sounding
#   en-GB-SoniaNeural    — calm, warm British accent
#   en-AU-NatashaNeural  — warm, relaxed Australian accent
VOICE = "en-US-JennyNeural"

# Dropped the old "+10%" / "+2Hz" boost (faster + higher pitch reads as
# more hyper/newsy) in favor of a neutral, calmer pace.
RATE = "+0%"
PITCH = "+0Hz"

MAX_RETRIES = 3


async def generate_voice(script, output):

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            communicate = edge_tts.Communicate(
                script,
                VOICE,
                rate=RATE,
                pitch=PITCH
            )

            await communicate.save(output)

            return output

        except Exception as exc:

            last_error = exc

            print(f"Voice generation attempt {attempt} failed: {exc}")

            if attempt < MAX_RETRIES:
                await asyncio.sleep(attempt * 2)

    raise RuntimeError(
        f"Unable to generate narration after {MAX_RETRIES} attempts: {last_error}"
    )