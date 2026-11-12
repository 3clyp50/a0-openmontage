import asyncio
import subprocess

from helpers.api import ApiHandler, Request, Response
from usr.plugins.openmontage.helpers.production import dispatch


class Production(ApiHandler):
    async def process(self, input: dict, request: Request):
        try:
            return {"ok": True, **await asyncio.to_thread(dispatch, **input)}
        except (ValueError, FileNotFoundError) as error:
            return Response(str(error), status=400)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            return Response("OpenMontage runtime is unavailable." if isinstance(error, subprocess.TimeoutExpired) else str(error), status=503)
