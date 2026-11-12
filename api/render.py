from flask import send_file

from helpers.api import ApiHandler, Request, Response
from usr.plugins.openmontage.helpers.production import PROJECTS, get_project, inside


class Render(ApiHandler):
    @classmethod
    def get_methods(cls):
        return ["GET"]

    @classmethod
    def requires_csrf(cls):
        return False

    async def process(self, input: dict, request: Request):
        try:
            project = get_project(request.args.get("id", ""))
            filename = request.args.get("file", "")
            if filename not in {item["name"] for item in project["renders"]}:
                raise ValueError("Unknown render.")
            target = inside(inside(PROJECTS, project["id"]), f"renders/{filename}")
            response = send_file(target, conditional=True, as_attachment=request.args.get("download") == "1", download_name=target.name)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Cache-Control"] = "private, no-store"
            return response
        except (ValueError, OSError, KeyError):
            return Response("Render not found.", status=404)
