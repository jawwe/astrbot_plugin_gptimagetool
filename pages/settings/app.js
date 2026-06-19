const bridge = window.AstrBotPluginPage;
const fields = {
  primary: {
    baseUrl: document.querySelector("#primary-base-url"),
    apiKey: document.querySelector("#primary-api-key"),
    keyStatus: document.querySelector("#primary-key-status"),
    model: document.querySelector("#primary-model"),
    load: document.querySelector("#primary-load-models"),
  },
  auxiliary: {
    enabled: document.querySelector("#auxiliary-enabled"),
    baseUrl: document.querySelector("#auxiliary-base-url"),
    apiKey: document.querySelector("#auxiliary-api-key"),
    keyStatus: document.querySelector("#auxiliary-key-status"),
    model: document.querySelector("#auxiliary-model"),
    load: document.querySelector("#auxiliary-load-models"),
    systemPrompt: document.querySelector("#auxiliary-system-prompt"),
  },
};
const status = document.querySelector("#status");
const form = document.querySelector("#settings-form");
const auxiliaryFields = document.querySelector("#auxiliary-fields");

function setStatus(message, isError = false) {
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function setModels(select, models, selected) {
  select.replaceChildren();
  for (const model of models) {
    const option = new Option(model, model, false, model === selected);
    select.add(option);
  }
  if (!select.value && models.length) {
    select.value = models.includes("gpt-image-2") ? "gpt-image-2" : models[0];
  }
}

function toggleAuxiliary() {
  auxiliaryFields.hidden = !fields.auxiliary.enabled.checked;
}

function pagePayload() {
  return {
    primary: {
      base_url: fields.primary.baseUrl.value.trim(),
      api_key: fields.primary.apiKey.value,
      model: fields.primary.model.value,
    },
    auxiliary: {
      enabled: fields.auxiliary.enabled.checked,
      base_url: fields.auxiliary.baseUrl.value.trim(),
      api_key: fields.auxiliary.apiKey.value,
      model: fields.auxiliary.model.value,
      system_prompt: fields.auxiliary.systemPrompt.value.trim(),
    },
  };
}

async function loadModels(target) {
  const current = fields[target];
  const primary = fields.primary;
  const config = {
    base_url: current.baseUrl.value.trim(),
    api_key: current.apiKey.value.trim(),
  };
  if (target === "auxiliary") {
    config.base_url ||= primary.baseUrl.value.trim();
    config.api_key ||= primary.apiKey.value.trim();
  }
  if (!config.base_url || !config.api_key) {
    setStatus("请输入 API 地址和 Key 后再获取模型。", true);
    return;
  }

  current.load.disabled = true;
  setStatus("正在获取模型…");
  try {
    const result = await bridge.apiPost("models", { target, [target]: config });
    setModels(current.model, result.models, current.model.value);
    setStatus(`已获取 ${result.models.length} 个模型。`);
  } catch (error) {
    setStatus(`获取模型失败：${error.message}`, true);
  } finally {
    current.load.disabled = false;
  }
}

function render(settings) {
  const { primary, auxiliary } = settings;
  fields.primary.baseUrl.value = primary.base_url;
  fields.primary.keyStatus.textContent = primary.api_key_set ? "已保存" : "未设置";
  setModels(fields.primary.model, primary.model ? [primary.model] : [], primary.model);

  fields.auxiliary.enabled.checked = auxiliary.enabled;
  fields.auxiliary.baseUrl.value = auxiliary.base_url;
  fields.auxiliary.keyStatus.textContent = auxiliary.api_key_set
    ? "已保存"
    : auxiliary.inherits_primary
      ? "继承主接口"
      : "未设置";
  fields.auxiliary.systemPrompt.value = auxiliary.system_prompt;
  setModels(fields.auxiliary.model, auxiliary.model ? [auxiliary.model] : [], auxiliary.model);
  toggleAuxiliary();
}

fields.primary.load.addEventListener("click", () => loadModels("primary"));
fields.auxiliary.load.addEventListener("click", () => loadModels("auxiliary"));
fields.auxiliary.enabled.addEventListener("change", toggleAuxiliary);
for (const target of ["primary", "auxiliary"]) {
  const current = fields[target];
  current.baseUrl.addEventListener("change", () => loadModels(target));
  current.apiKey.addEventListener("change", () => loadModels(target));
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("正在保存…");
  try {
    const saved = await bridge.apiPost("settings", pagePayload());
    render(saved);
    fields.primary.apiKey.value = "";
    fields.auxiliary.apiKey.value = "";
    setStatus("配置已保存。");
  } catch (error) {
    setStatus(`保存失败：${error.message}`, true);
  }
});

await bridge.ready();
document.querySelector("#title").textContent = bridge.t(
  "pages.settings.title",
  "GPT Image Tool Settings",
);
document.querySelector("#description").textContent = bridge.t(
  "pages.settings.description",
  "Configure an OpenAI-compatible image-generation API.",
);
try {
  render(await bridge.apiGet("settings"));
} catch (error) {
  setStatus(`加载配置失败：${error.message}`, true);
}
