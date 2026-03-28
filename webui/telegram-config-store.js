import { createStore } from "/js/AlpineStore.js";
import {
  toastFrontendError,
  toastFrontendSuccess,
} from "/components/notifications/notification-store.js";

const API_BASE = "/plugins/telegram_integration_voice";
const PLUGIN_INSTALLER = "plugins/_plugin_installer/plugin_install";
const PLUGIN_NAME = "telegram_integration_voice";

export const store = createStore("telegramConfig", {
  projects: [],
  expandedIdx: null,
  testing: null,
  testResults: null,
  updating: false,
  _loaded: false,

  onOpen() {
    this.init();
  },

  cleanup() {
    this.testing = null;
    this.testResults = null;
    this.updating = false;
  },

  async init() {
    if (this._loaded) return;
    try {
      const { callJsonApi } = await import("/js/api.js");
      const res = await callJsonApi("projects", { action: "list" });
      this.projects = res.data || [];
    } catch (_) {
      this.projects = [];
    }
    this._loaded = true;
  },

  defaultBot() {
    return {
      name: "",
      enabled: true,
      notify_messages: false,
      token: "",
      mode: "polling",
      webhook_url: "",
      webhook_secret: "",
      allowed_users: [],
      group_mode: "mention",
      welcome_enabled: false,
      welcome_message: "",
      user_projects: {},
      default_project: "",
      agent_instructions: "",
      attachment_max_age_hours: 0,
      speech: {
        stt: {
          enabled: false,
          provider: "openai_compatible",
          base_url: "",
          endpoint: "",
          api_key: "",
          model: "whisper-1",
          language: "",
          timeout_sec: 60,
        },
        tts: {
          enabled: false,
          provider: "openai_compatible",
          base_url: "",
          endpoint: "",
          api_key: "",
          model: "gpt-4o-mini-tts",
          voice: "alloy",
          format: "opus",
          timeout_sec: 60,
        },
        reply: {
          voice_mode: "auto",
          also_send_text: true,
          max_chars: 700,
        },
      },
    };
  },

  ensureSpeech(bot) {
    if (!bot.speech) bot.speech = {};
    if (!bot.speech.stt) bot.speech.stt = {};
    if (!bot.speech.tts) bot.speech.tts = {};
    if (!bot.speech.reply) bot.speech.reply = {};

    const d = this.defaultBot().speech;
    bot.speech.stt = { ...d.stt, ...(bot.speech.stt || {}) };
    bot.speech.tts = { ...d.tts, ...(bot.speech.tts || {}) };
    bot.speech.reply = { ...d.reply, ...(bot.speech.reply || {}) };
  },

  addBot(config) {
    if (!config.bots) config.bots = [];
    const bot = this.defaultBot();
    bot.name = "bot_" + (config.bots.length + 1);
    this.ensureSpeech(bot);
    config.bots.push(bot);
    this.expandedIdx = config.bots.length - 1;
  },

  removeBot(config, idx) {
    config.bots.splice(idx, 1);
    this.expandedIdx = null;
  },

  toggle(idx) {
    this.expandedIdx = this.expandedIdx === idx ? null : idx;
    this.testResults = null;
  },

  whitelistText(bot) {
    return (bot.allowed_users || []).join(", ");
  },

  setWhitelist(bot, val) {
    bot.allowed_users = val
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s);
  },

  userProjectsText(bot) {
    const up = bot.user_projects || {};
    return Object.entries(up)
      .map(([k, v]) => k + "=" + v)
      .join(", ");
  },

  setUserProjects(bot, val) {
    const obj = {};
    val
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s)
      .forEach((item) => {
        const parts = item.split("=").map((p) => p.trim());
        const k = parts[0];
        if (k) obj[k] = parts[1] || "";
      });
    bot.user_projects = obj;
  },

  async updatePluginFromGit() {
    if (
      !window.confirm(
        "Update this plugin from Git? You may need to reload this page afterward.",
      )
    ) {
      return;
    }
    this.updating = true;
    try {
      const { callJsonApi } = await import("/js/api.js");
      const res = await callJsonApi(PLUGIN_INSTALLER, {
        action: "update_plugin",
        plugin_name: PLUGIN_NAME,
      });
      const ok = res && (res.success === true || res.ok === true);
      if (ok) {
        const sha = res.current_commit
          ? String(res.current_commit).slice(0, 7)
          : "";
        toastFrontendSuccess(
          sha
            ? `Plugin updated (${sha}). Consider reloading the page.`
            : "Plugin updated. Consider reloading the page.",
          "Telegram Integration (Voice)",
        );
      } else {
        toastFrontendError(
          (res && (res.error || res.message)) || "Update failed.",
          "Telegram Integration (Voice)",
        );
      }
    } catch (e) {
      toastFrontendError(String(e), "Telegram Integration (Voice)");
    } finally {
      this.updating = false;
    }
  },

  async testConnection(config, idx) {
    this.testing = idx;
    this.testResults = null;
    try {
      const { callJsonApi } = await import("/js/api.js");
      const res = await callJsonApi(`${API_BASE}/test_connection`, {
        bot: config.bots[idx],
      });
      this.testResults = res;
      if (res && res.success) {
        toastFrontendSuccess("Connection test succeeded.", "Telegram Integration (Voice)");
      } else {
        toastFrontendError(
          (res && res.message) || "Connection test failed.",
          "Telegram Integration (Voice)",
        );
      }
    } catch (e) {
      this.testResults = {
        success: false,
        results: [{ test: "Connection", ok: false, message: String(e) }],
      };
      toastFrontendError(String(e), "Telegram Integration (Voice)");
    }
    this.testing = null;
  },
});
