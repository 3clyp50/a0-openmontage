import asyncio
import json
import subprocess

from helpers.tool import Tool, Response
from usr.plugins.openmontage.helpers.production import dispatch


class OpenMontage(Tool):
    async def execute(self, action="status", **kwargs):
        try:
            result = await asyncio.to_thread(dispatch, action=action, **kwargs)
            return Response(message=json.dumps(result, ensure_ascii=False), break_loop=False)
        except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            return Response(message=f"OpenMontage: {error}", break_loop=False)
