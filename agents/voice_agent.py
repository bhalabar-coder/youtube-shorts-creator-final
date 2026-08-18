import asyncio
import os

import edge_tts

VOICE = "en-US-AriaNeural"

MAX_RETRIES = 3


async def generate_voice(script, output):

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            communicate = edge_tts.Communicate(
                script,
                VOICE,
                rate="+10%",
                pitch="+2Hz"
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
