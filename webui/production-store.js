import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import { store as chats } from "/components/sidebar/chats/chats-store.js";
import { toastFrontendError } from "/components/notifications/notification-store.js";

export const store = createStore("openMontage", {
  tab: "new", busy: false, ready: false, ffmpeg: false, projects: [], pipelines: [],
  title: "", brief: "", pipeline: "animated-explainer", budget: 2, current: null, selectedRender: "",
  init() {},
  async api(action, values = {}) {
    return callJsonApi("/plugins/openmontage/production", { action, ...values });
  },
  async refresh() {
    this.busy = true;
    try {
      const status = await this.api("status");
      this.ready = status.ready;
      this.ffmpeg = status.ffmpeg;
      this.projects = status.projects;
      if (this.current) {
        this.current = this.projects.find(project => project.id === this.current.id) || null;
        this.selectRender();
      }
      if (this.ready && !this.pipelines.length) this.pipelines = (await this.api("pipelines")).items;
    } catch (error) { toastFrontendError(error.message, "OpenMontage"); }
    finally { this.busy = false; }
  },
  get canCreate() { return this.ready && this.ffmpeg && !this.busy && this.title.trim() && this.brief.trim(); },
  view(project) { this.current = project; this.tab = "production"; this.selectedRender = ""; this.selectRender(); },
  selectRender() {
    if (!this.current?.renders.some(render => render.name === this.selectedRender)) this.selectedRender = this.current?.renders[0]?.name || "";
  },
  url(download = false) {
    if (!this.current || !this.selectedRender) return "";
    return `/api/plugins/openmontage/render?id=${encodeURIComponent(this.current.id)}&file=${encodeURIComponent(this.selectedRender)}${download ? "&download=1" : ""}`;
  },
  stageIcon(status) {
    return ({ completed: "check_circle", failed: "error", awaiting_human: "pause_circle", in_progress: "pending" })[status] || "radio_button_unchecked";
  },
  async create() {
    if (!this.canCreate) return;
    this.busy = true;
    try {
      const result = await this.api("create", { title: this.title, brief: this.brief, pipeline: this.pipeline, budget: Number(this.budget) });
      this.projects.unshift(result.project);
      this.view(result.project);
      this.title = "";
      this.brief = "";
      await this.start();
    } catch (error) { toastFrontendError(error.message, "OpenMontage"); }
    finally { this.busy = false; }
  },
  async start() {
    if (!this.current) return;
    this.busy = true;
    try {
      const { message, context_id } = await this.api("handoff", { project_id: this.current.id });
      if (context_id) {
        await chats.selectChat(context_id);
        return;
      }
      const context = await chats.newChat();
      if (!context) throw new Error("Could not create the production chat.");
      const result = await callJsonApi("/message_async", { text: message, context, message_id: crypto.randomUUID() });
      if (result.model_not_configured) throw new Error("Select a model in Agent Zero, then choose Continue in chat.");
      await this.api("attach_chat", { project_id: this.current.id, context_id: context });
    } catch (error) { toastFrontendError(error.message, "OpenMontage"); }
    finally { this.busy = false; }
  },
  cleanup() {},
});
