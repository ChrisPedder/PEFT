import { parseSSELine, formatPayload } from "./lib";
import {
  initAuth,
  signIn,
  completeNewPassword,
  verifyTotp,
  associateSoftwareToken,
  verifySoftwareToken,
  getIdToken,
  isAuthenticated,
  signOut,
} from "./auth";
import type { CognitoUser } from "amazon-cognito-identity-js";

// --- Auth UI elements ---
const loginSection = document.getElementById("login-section")!;
const chatSection = document.getElementById("chat-section")!;
const loginForm = document.getElementById("login-form") as HTMLFormElement;
const loginEmail = document.getElementById("login-email") as HTMLInputElement;
const loginPassword = document.getElementById(
  "login-password"
) as HTMLInputElement;
const loginBtn = document.getElementById("login-btn") as HTMLButtonElement;
const loginError = document.getElementById("login-error")!;
const newPasswordForm = document.getElementById(
  "new-password-form"
) as HTMLFormElement;
const newPasswordInput = document.getElementById(
  "new-password-input"
) as HTMLInputElement;
const newPasswordBtn = document.getElementById(
  "new-password-btn"
) as HTMLButtonElement;
const totpForm = document.getElementById("totp-form") as HTMLFormElement;
const totpInput = document.getElementById("totp-input") as HTMLInputElement;
const totpBtn = document.getElementById("totp-btn") as HTMLButtonElement;
const mfaSetupForm = document.getElementById(
  "mfa-setup-form"
) as HTMLFormElement;
const mfaSetupSecret = document.getElementById("mfa-setup-secret")!;
const mfaSetupInput = document.getElementById(
  "mfa-setup-input"
) as HTMLInputElement;
const mfaSetupBtn = document.getElementById(
  "mfa-setup-btn"
) as HTMLButtonElement;
const signOutBtn = document.getElementById("sign-out-btn") as HTMLButtonElement;

// --- Chat UI elements ---
const messagesEl = document.getElementById("messages")!;
const form = document.getElementById("ask-form") as HTMLFormElement;
const input = document.getElementById("question-input") as HTMLInputElement;
const submitBtn = document.getElementById("submit-btn") as HTMLButtonElement;
const statusBar = document.getElementById("status-bar")!;

// Holds the CognitoUser during NEW_PASSWORD_REQUIRED flow
let pendingCognitoUser: CognitoUser | null = null;

// --- Section toggling ---

function showLogin() {
  loginSection.classList.remove("hidden");
  chatSection.classList.add("hidden");
  loginForm.classList.remove("hidden");
  newPasswordForm.classList.add("hidden");
  totpForm.classList.add("hidden");
  mfaSetupForm.classList.add("hidden");
  loginError.classList.add("hidden");
  loginEmail.value = "";
  loginPassword.value = "";
  loginBtn.disabled = false;
}

function showChat() {
  loginSection.classList.add("hidden");
  chatSection.classList.remove("hidden");
  input.focus();
}

function showLoginError(msg: string) {
  loginError.textContent = msg;
  loginError.classList.remove("hidden");
}

// --- Chat logic ---

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
    const token = await getIdToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch("/api/ask", {
      method: "POST",
      headers,
      body: formatPayload(question),
    });

    if (response.status === 401) {
      signOut();
      showLogin();
      assistantEl.remove();
      setLoading(false);
      return;
    }

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
        const tokenText = parseSSELine(line);
        if (tokenText === null) continue;
        if (tokenText === "[DONE]") break;

        fullText += tokenText;
        assistantEl.textContent = fullText;
        assistantEl.appendChild(cursor);
        assistantEl.scrollIntoView({ behavior: "smooth" });
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

// --- Event listeners ---

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.classList.add("hidden");
  loginBtn.disabled = true;

  const email = loginEmail.value.trim();
  const password = loginPassword.value;

  try {
    const result = await signIn(email, password);
    if ("session" in result) {
      showChat();
    } else if (result.challengeName === "NEW_PASSWORD_REQUIRED") {
      pendingCognitoUser = result.cognitoUser;
      loginForm.classList.add("hidden");
      newPasswordForm.classList.remove("hidden");
    } else if (result.challengeName === "SOFTWARE_TOKEN_MFA") {
      pendingCognitoUser = result.cognitoUser;
      loginForm.classList.add("hidden");
      totpForm.classList.remove("hidden");
    } else if (result.challengeName === "MFA_SETUP") {
      pendingCognitoUser = result.cognitoUser;
      loginForm.classList.add("hidden");
      try {
        const secret = await associateSoftwareToken(result.cognitoUser);
        mfaSetupSecret.textContent = secret;
        mfaSetupForm.classList.remove("hidden");
      } catch (setupErr) {
        const msg =
          setupErr instanceof Error ? setupErr.message : "MFA setup failed";
        showLoginError(msg);
      }
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Sign-in failed";
    showLoginError(msg);
    loginBtn.disabled = false;
  }
});

newPasswordForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.classList.add("hidden");
  newPasswordBtn.disabled = true;

  const newPassword = newPasswordInput.value;

  try {
    if (!pendingCognitoUser) throw new Error("No pending user");
    await completeNewPassword(pendingCognitoUser, newPassword);
    pendingCognitoUser = null;
    showChat();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Password change failed";
    showLoginError(msg);
    newPasswordBtn.disabled = false;
  }
});

totpForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.classList.add("hidden");
  totpBtn.disabled = true;

  const code = totpInput.value.trim();

  try {
    if (!pendingCognitoUser) throw new Error("No pending user");
    await verifyTotp(pendingCognitoUser, code);
    pendingCognitoUser = null;
    showChat();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "TOTP verification failed";
    showLoginError(msg);
    totpBtn.disabled = false;
  }
});

mfaSetupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.classList.add("hidden");
  mfaSetupBtn.disabled = true;

  const code = mfaSetupInput.value.trim();

  try {
    if (!pendingCognitoUser) throw new Error("No pending user");
    await verifySoftwareToken(pendingCognitoUser, code);
    pendingCognitoUser = null;
    showChat();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "MFA setup verification failed";
    showLoginError(msg);
    mfaSetupBtn.disabled = false;
  }
});

signOutBtn.addEventListener("click", () => {
  signOut();
  showLogin();
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  askQuestion(question);
});

// --- Init ---

async function init() {
  try {
    const resp = await fetch("/config.json");
    const config = await resp.json();
    initAuth({
      cognitoUserPoolId: config.cognitoUserPoolId,
      cognitoClientId: config.cognitoClientId,
    });

    if (await isAuthenticated()) {
      showChat();
    } else {
      showLogin();
    }
  } catch {
    // If config.json is unavailable (e.g. local dev), show login anyway
    showLogin();
  }
}

init();
