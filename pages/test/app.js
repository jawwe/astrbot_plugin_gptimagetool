const bridge = window.AstrBotPluginPage;
const imagePrompt = document.querySelector("#image-prompt");
const chatPrompt = document.querySelector("#chat-prompt");
const imageButton = document.querySelector("#generate-image");
const chatButton = document.querySelector("#send-chat");
const imageResult = document.querySelector("#image-result");
const chatResult = document.querySelector("#chat-result");
const status = document.querySelector("#status");

function setStatus(message, isError = false) {
  status.textContent = message;
  status.classList.toggle("error", isError);
}

imageButton.addEventListener("click", async () => {
  const prompt = imagePrompt.value.trim();
  if (!prompt) {
    setStatus("请输入图片描述。", true);
    return;
  }

  imageButton.disabled = true;
  imageResult.hidden = true;
  setStatus("正在生成测试图片…");
  try {
    const result = await bridge.apiPost("test/image", { prompt });
    imageResult.src = result.image.url || `data:image/png;base64,${result.image.b64_json}`;
    imageResult.hidden = false;
    setStatus("测试图片生成完成。");
  } catch (error) {
    setStatus(`生成失败：${error.message}`, true);
  } finally {
    imageButton.disabled = false;
  }
});

chatButton.addEventListener("click", async () => {
  const prompt = chatPrompt.value.trim();
  if (!prompt) {
    setStatus("请输入对话内容。", true);
    return;
  }

  chatButton.disabled = true;
  chatResult.hidden = true;
  setStatus("正在请求辅助模型…");
  try {
    const result = await bridge.apiPost("test/chat", { prompt });
    chatResult.textContent = result.content;
    chatResult.hidden = false;
    setStatus("辅助模型响应完成。");
  } catch (error) {
    setStatus(`对话失败：${error.message}`, true);
  } finally {
    chatButton.disabled = false;
  }
});

await bridge.ready();
document.querySelector("#title").textContent = bridge.t(
  "pages.test.title",
  "GPT Image Tool Test",
);
document.querySelector("#description").textContent = bridge.t(
  "pages.test.description",
  "Test image generation and the auxiliary model with saved settings.",
);
