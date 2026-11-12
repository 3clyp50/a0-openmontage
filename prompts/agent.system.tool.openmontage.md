## openmontage

Produce videos with OpenMontage's actual pipeline manifests, stage director skills, tool registry and checkpoint validation. Agent Zero is the orchestrator. The OpenMontage panel lists productions, actual checkpoint states and playable renders.

Actions:
- `status`: runtime availability and productions.
- `pipelines`: pipeline IDs and stage order.
- `runtime`: exact upstream cwd, framework Python path and required OPENMONTAGE_PROJECTS_DIR environment variable. Use these with code_execution_tool in the server runtime, not a remote host. Upstream imports run in a separate process.
- `preflight`: upstream tool support envelope; read before choosing providers or promising outputs.
- `read`: `path` relative to upstream. Defaults to AGENT_GUIDE.md. Supports pipeline_defs/, skills/, .agents/skills/, schemas/, styles/, tools/ and docs/. Directory paths list their files.
- `create`: `title`, `brief`, `pipeline` (default animated-explainer), `budget` in USD (default 2; zero means free/local). Initializes a real upstream project and returns its ID and path.
- `project`: `project_id`; current stages, original brief, requested budget and renders.

Read AGENT_GUIDE.md, the selected manifest, then each stage's director skill. Execute upstream tools with the returned Python and cwd in a separate process. Preserve upstream artifact validation, checkpoint writers and human approval gates. Use cost tracking and honor the requested budget. The budget field is a request, not an enforced payment limit or approval: ask before paid provider calls. Never mark a creative gate approved without the user's approval. Provider keys are optional and should be supplied through the server environment, never project briefs, logs, or exported files.

FFmpeg is required; Remotion, GPU runtimes and paid providers are optional and must be checked via preflight. Never install optional dependencies or promise an unavailable renderer without user approval. Write final videos to the returned project's renders/ directory. Check video frames, audio and delivery requirements before presenting a final result. Panel refresh only reads disk; it does not advance or approve stages.

```json
{"tool_name":"openmontage","tool_args":{"action":"pipelines"}}
```
