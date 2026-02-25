const messagesEl = document.getElementById("messages")!;
const form = document.getElementById("ask-form") as HTMLFormElement;
const input = document.getElementById("question-input") as HTMLInputElement;
const submitBtn = document.getElementById("submit-btn") as HTMLButtonElement;
const statusBar = document.getElementById("status-bar")!;

function addMessage(role: "user" | "assistant", text: string): HTMLDivElement {
  const el = document.createElement("div");
  el.classList.add("message", role);
  el.textContent = text;
  messagesEl.appendChild(el);
  el.scrollIntoView({ behavior: "smooth" });
  return el;
}

function showStatus(msg: string, type: "info" | "error" | "warming" = "info") {
  statusBar.textContent = msg;
  statusBar.className = type;
  statusBar.classList.remove("hidden");
}

function hideStatus() {
  statusBar.classList.add("hidden");
}

function setLoading(loading: boolean) {
  submitBtn.disabled = loading;
  input.disabled = loading;
  submitBtn.textContent = loading ? "..." : "Ask";
}

async function askQuestion(question: string) {
  addMessage("user", question);
  setLoading(true);
  hideStatus();

  const assistantEl = addMessage("assistant", "");
  // Add blinking cursor
  const cursor = document.createElement("span");
  cursor.classList.add("cursor");
  assistantEl.appendChild(cursor);

  let fullText = "";

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, max_tokens: 512, temperature: 0.7 }),
    });

    if (response.status === 503) {
      const data = await response.json();
      showStatus(data.detail || "Model is warming up...", "warming");
      assistantEl.remove();
      setLoading(false);
      return;
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process SSE events in buffer
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line in buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;

        const data = trimmed.slice(5).trim();
        if (data === "[DONE]") break;

        try {
          const parsed = JSON.parse(data);
          if (parsed.token) {
            fullText += parsed.token;
            assistantEl.textContent = fullText;
            assistantEl.appendChild(cursor);
            assistantEl.scrollIntoView({ behavior: "smooth" });
          }
        } catch {
          // Skip malformed JSON chunks
        }
      }
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    showStatus(`Failed to get response: ${msg}`, "error");
    if (!fullText) {
      assistantEl.remove();
    }
  } finally {
    // Remove cursor
    cursor.remove();
    if (fullText) {
      assistantEl.textContent = fullText;
    }
    setLoading(false);
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  askQuestion(question);
});

// Focus input on load
input.focus();
