import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// Mock the auth module
const mockInitAuth = vi.fn();
const mockSignIn = vi.fn();
const mockCompleteNewPassword = vi.fn();
const mockGetIdToken = vi.fn();
const mockIsAuthenticated = vi.fn();
const mockSignOut = vi.fn();

vi.mock("../auth", () => ({
  initAuth: (...args: unknown[]) => mockInitAuth(...args),
  signIn: (...args: unknown[]) => mockSignIn(...args),
  completeNewPassword: (...args: unknown[]) => mockCompleteNewPassword(...args),
  getIdToken: () => mockGetIdToken(),
  isAuthenticated: () => mockIsAuthenticated(),
  signOut: () => mockSignOut(),
}));

/**
 * Helper: create a ReadableStream from an array of SSE strings,
 * each chunk encoded as Uint8Array.
 */
function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]));
        index++;
      } else {
        controller.close();
      }
    },
  });
}

/**
 * Helper: build a mock Response object with the given status and body stream.
 */
function mockSSEResponse(
  status: number,
  body: ReadableStream<Uint8Array>
): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: new Headers({ "content-type": "text/event-stream" }),
    body,
    json: () => Promise.resolve({}),
  } as unknown as Response;
}

/**
 * Set up the full HTML fixture needed by app.ts (login + chat sections).
 */
function setupDOM() {
  document.body.innerHTML = `
    <section id="login-section">
      <form id="login-form">
        <input type="email" id="login-email" />
        <input type="password" id="login-password" />
        <button type="submit" id="login-btn">Sign In</button>
      </form>
      <form id="new-password-form" class="hidden">
        <input type="password" id="new-password-input" />
        <button type="submit" id="new-password-btn">Set Password</button>
      </form>
      <div id="login-error" class="hidden"></div>
    </section>
    <section id="chat-section" class="hidden">
      <button id="sign-out-btn">Sign Out</button>
      <div id="messages"></div>
      <form id="ask-form">
        <input type="text" id="question-input" />
        <button type="submit" id="submit-btn">Ask</button>
      </form>
      <div id="status-bar" class="hidden"></div>
    </section>
  `;
}

describe("app.ts integration", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setupDOM();
    fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    // Stub scrollIntoView since jsdom doesn't implement it
    Element.prototype.scrollIntoView = vi.fn();
    // Default: config.json fetch succeeds, user is authenticated
    mockIsAuthenticated.mockResolvedValue(true);
    mockGetIdToken.mockResolvedValue("mock-jwt-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function loadApp() {
    // Mock the config.json fetch, then let other fetches through
    fetchSpy.mockImplementation((url: string, ...args: unknown[]) => {
      if (url === "/config.json") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              cognitoUserPoolId: "us-east-1_test",
              cognitoClientId: "test-client-id",
              cognitoRegion: "us-east-1",
            }),
        });
      }
      // Return a default for any other URL — tests should override for /api/ask
      return Promise.resolve({
        status: 200,
        ok: true,
        headers: new Headers(),
        json: () => Promise.resolve({}),
        body: sseStream([]),
      });
    });

    await import("../app");
    // Allow init() to complete
    await new Promise((r) => setTimeout(r, 50));
  }

  function getMessages(): HTMLDivElement {
    return document.getElementById("messages") as HTMLDivElement;
  }

  function getStatusBar(): HTMLDivElement {
    return document.getElementById("status-bar") as HTMLDivElement;
  }

  function getSubmitBtn(): HTMLButtonElement {
    return document.getElementById("submit-btn") as HTMLButtonElement;
  }

  // --- Auth / login tests ---

  it("shows login section when user is not authenticated", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    await loadApp();

    const loginSection = document.getElementById("login-section")!;
    const chatSection = document.getElementById("chat-section")!;
    expect(loginSection.classList.contains("hidden")).toBe(false);
    expect(chatSection.classList.contains("hidden")).toBe(true);
  });

  it("shows chat section when user is already authenticated", async () => {
    mockIsAuthenticated.mockResolvedValue(true);
    await loadApp();

    const loginSection = document.getElementById("login-section")!;
    const chatSection = document.getElementById("chat-section")!;
    expect(loginSection.classList.contains("hidden")).toBe(true);
    expect(chatSection.classList.contains("hidden")).toBe(false);
  });

  it("login form submission calls signIn and shows chat on success", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    mockSignIn.mockResolvedValue({ session: {} });
    await loadApp();

    const emailInput = document.getElementById("login-email") as HTMLInputElement;
    const passwordInput = document.getElementById("login-password") as HTMLInputElement;
    const loginForm = document.getElementById("login-form") as HTMLFormElement;

    emailInput.value = "user@test.com";
    passwordInput.value = "password123";
    loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      expect(mockSignIn).toHaveBeenCalledWith("user@test.com", "password123");
      const chatSection = document.getElementById("chat-section")!;
      expect(chatSection.classList.contains("hidden")).toBe(false);
    });
  });

  it("shows login error on sign-in failure", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    mockSignIn.mockRejectedValue(new Error("Incorrect username or password."));
    await loadApp();

    const emailInput = document.getElementById("login-email") as HTMLInputElement;
    const passwordInput = document.getElementById("login-password") as HTMLInputElement;
    const loginForm = document.getElementById("login-form") as HTMLFormElement;

    emailInput.value = "user@test.com";
    passwordInput.value = "wrong";
    loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const loginError = document.getElementById("login-error")!;
      expect(loginError.classList.contains("hidden")).toBe(false);
      expect(loginError.textContent).toContain("Incorrect username or password.");
    });
  });

  it("shows new password form on NEW_PASSWORD_REQUIRED challenge", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    mockSignIn.mockResolvedValue({
      challengeName: "NEW_PASSWORD_REQUIRED",
      cognitoUser: {},
    });
    await loadApp();

    const emailInput = document.getElementById("login-email") as HTMLInputElement;
    const passwordInput = document.getElementById("login-password") as HTMLInputElement;
    const loginForm = document.getElementById("login-form") as HTMLFormElement;

    emailInput.value = "user@test.com";
    passwordInput.value = "temp";
    loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const newPasswordForm = document.getElementById("new-password-form")!;
      expect(newPasswordForm.classList.contains("hidden")).toBe(false);
      expect(loginForm.classList.contains("hidden")).toBe(true);
    });
  });

  it("sign-out button returns to login", async () => {
    mockIsAuthenticated.mockResolvedValue(true);
    await loadApp();

    const signOutBtn = document.getElementById("sign-out-btn")!;
    signOutBtn.click();

    await vi.waitFor(() => {
      expect(mockSignOut).toHaveBeenCalled();
      const loginSection = document.getElementById("login-section")!;
      expect(loginSection.classList.contains("hidden")).toBe(false);
    });
  });

  // --- Chat tests (with auth mocked) ---

  it("form submission triggers fetch with auth header", async () => {
    const stream = sseStream(['data: {"token": "Hi"}\n', "data: [DONE]\n"]);
    await loadApp();

    // Override fetch for /api/ask specifically
    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve(mockSSEResponse(200, stream));
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "What is democracy?";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const askCalls = fetchSpy.mock.calls.filter(
        (c: unknown[]) => c[0] === "/api/ask"
      );
      expect(askCalls.length).toBe(1);
      const [, options] = askCalls[0];
      expect(options.headers["Authorization"]).toBe("Bearer mock-jwt-token");
    });
  });

  it("SSE streaming updates the DOM with tokens", async () => {
    const stream = sseStream([
      'data: {"token": "Hello"}\n',
      'data: {"token": " world"}\n',
      "data: [DONE]\n",
    ]);
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve(mockSSEResponse(200, stream));
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test question";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const messages = getMessages();
      const assistantMsgs = messages.querySelectorAll(".message.assistant");
      expect(assistantMsgs.length).toBe(1);
      expect(assistantMsgs[0].textContent).toBe("Hello world");
    });
  });

  it("503 response shows warming status", async () => {
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve({
          status: 503,
          ok: false,
          headers: new Headers(),
          json: () => Promise.resolve({ detail: "Model is loading, please wait..." }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test question";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const sb = getStatusBar();
      expect(sb.textContent).toBe("Model is loading, please wait...");
      expect(sb.classList.contains("hidden")).toBe(false);
      expect(sb.className).toContain("warming");
    });

    const assistantMsgs = getMessages().querySelectorAll(".message.assistant");
    expect(assistantMsgs.length).toBe(0);
  });

  it("401 response triggers sign-out and shows login", async () => {
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve({
          status: 401,
          ok: false,
          headers: new Headers(),
          json: () => Promise.resolve({ detail: "Unauthorized" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test question";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      expect(mockSignOut).toHaveBeenCalled();
      const loginSection = document.getElementById("login-section")!;
      expect(loginSection.classList.contains("hidden")).toBe(false);
    });
  });

  it("network error shows error status", async () => {
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.reject(new Error("Network failure"));
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test question";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const sb = getStatusBar();
      expect(sb.textContent).toContain("Network failure");
      expect(sb.className).toContain("error");
    });
  });

  it("empty input does not trigger fetch", async () => {
    await loadApp();

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "   ";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await new Promise((r) => setTimeout(r, 50));

    const askCalls = fetchSpy.mock.calls.filter(
      (c: unknown[]) => c[0] === "/api/ask"
    );
    expect(askCalls.length).toBe(0);
  });

  it("new password form submission completes and shows chat", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    mockSignIn.mockResolvedValue({
      challengeName: "NEW_PASSWORD_REQUIRED",
      cognitoUser: { username: "testuser" },
    });
    mockCompleteNewPassword.mockResolvedValue({});
    await loadApp();

    // Trigger login to get to new password form
    const emailInput = document.getElementById("login-email") as HTMLInputElement;
    const passwordInput = document.getElementById("login-password") as HTMLInputElement;
    const loginForm = document.getElementById("login-form") as HTMLFormElement;

    emailInput.value = "user@test.com";
    passwordInput.value = "temp";
    loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const newPasswordForm = document.getElementById("new-password-form")!;
      expect(newPasswordForm.classList.contains("hidden")).toBe(false);
    });

    // Now submit the new password form
    const newPasswordInput = document.getElementById("new-password-input") as HTMLInputElement;
    const newPasswordForm = document.getElementById("new-password-form") as HTMLFormElement;

    newPasswordInput.value = "NewSecurePass123!";
    newPasswordForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      expect(mockCompleteNewPassword).toHaveBeenCalled();
      const chatSection = document.getElementById("chat-section")!;
      expect(chatSection.classList.contains("hidden")).toBe(false);
    });
  });

  it("new password form shows error on failure", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    mockSignIn.mockResolvedValue({
      challengeName: "NEW_PASSWORD_REQUIRED",
      cognitoUser: { username: "testuser" },
    });
    mockCompleteNewPassword.mockRejectedValue(new Error("Password too weak"));
    await loadApp();

    // Trigger login to get to new password form
    const emailInput = document.getElementById("login-email") as HTMLInputElement;
    const passwordInput = document.getElementById("login-password") as HTMLInputElement;
    const loginForm = document.getElementById("login-form") as HTMLFormElement;

    emailInput.value = "user@test.com";
    passwordInput.value = "temp";
    loginForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const npForm = document.getElementById("new-password-form")!;
      expect(npForm.classList.contains("hidden")).toBe(false);
    });

    // Submit new password form with weak password
    const newPasswordInput = document.getElementById("new-password-input") as HTMLInputElement;
    const newPasswordForm = document.getElementById("new-password-form") as HTMLFormElement;

    newPasswordInput.value = "weak";
    newPasswordForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const loginError = document.getElementById("login-error")!;
      expect(loginError.classList.contains("hidden")).toBe(false);
      expect(loginError.textContent).toContain("Password too weak");
    });
  });

  it("generic HTTP error (not 401/503) shows error status", async () => {
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve({
          status: 500,
          ok: false,
          headers: new Headers(),
          json: () => Promise.resolve({ detail: "Internal server error" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test question";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const sb = getStatusBar();
      expect(sb.textContent).toContain("HTTP 500");
      expect(sb.className).toContain("error");
    });
  });

  it("falls back to login when config.json fetch fails", async () => {
    mockIsAuthenticated.mockResolvedValue(false);

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/config.json") {
        return Promise.reject(new Error("Not found"));
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await import("../app");
    await new Promise((r) => setTimeout(r, 50));

    const loginSection = document.getElementById("login-section")!;
    expect(loginSection.classList.contains("hidden")).toBe(false);
  });

  it("submit button is disabled during loading and re-enabled after", async () => {
    const stream = sseStream(['data: {"token": "ok"}\n', "data: [DONE]\n"]);
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve(mockSSEResponse(200, stream));
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;
    const btn = getSubmitBtn();

    inputEl.value = "Hello";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      expect(btn.disabled).toBe(false);
      expect(btn.textContent).toBe("Ask");
    });
  });

  it("handles response with null body", async () => {
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve({
          status: 200,
          ok: true,
          headers: new Headers({ "content-type": "text/event-stream" }),
          body: null,
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test question";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const sb = getStatusBar();
      expect(sb.textContent).toContain("No response body");
      expect(sb.className).toContain("error");
    });
  });

  it("handles non-Error throw in askQuestion", async () => {
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.reject("string-error");
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test question";
    askForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    await vi.waitFor(() => {
      const sb = getStatusBar();
      expect(sb.textContent).toContain("Unknown error");
      expect(sb.className).toContain("error");
    });
  });

  it("handles non-Error rejection in signIn", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    mockSignIn.mockRejectedValue("not-an-error-object");
    await loadApp();

    const emailInput = document.getElementById("login-email") as HTMLInputElement;
    const passwordInput = document.getElementById(
      "login-password"
    ) as HTMLInputElement;
    const loginForm = document.getElementById("login-form") as HTMLFormElement;

    emailInput.value = "user@test.com";
    passwordInput.value = "password";
    loginForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );

    await vi.waitFor(() => {
      const loginError = document.getElementById("login-error")!;
      expect(loginError.classList.contains("hidden")).toBe(false);
      expect(loginError.textContent).toBe("Sign-in failed");
    });
  });

  it("new password form submit without pending user shows error", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    await loadApp();

    // Directly show the new password form without going through signIn challenge
    const loginForm = document.getElementById("login-form") as HTMLFormElement;
    const newPasswordForm = document.getElementById(
      "new-password-form"
    ) as HTMLFormElement;
    loginForm.classList.add("hidden");
    newPasswordForm.classList.remove("hidden");

    const newPasswordInput = document.getElementById(
      "new-password-input"
    ) as HTMLInputElement;
    newPasswordInput.value = "NewPass123!";
    newPasswordForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );

    await vi.waitFor(() => {
      const loginError = document.getElementById("login-error")!;
      expect(loginError.classList.contains("hidden")).toBe(false);
      expect(loginError.textContent).toContain("No pending user");
    });
  });

  it("new password form shows generic error on non-Error rejection", async () => {
    mockIsAuthenticated.mockResolvedValue(false);
    mockSignIn.mockResolvedValue({
      challengeName: "NEW_PASSWORD_REQUIRED",
      cognitoUser: { username: "testuser" },
    });
    mockCompleteNewPassword.mockRejectedValue("not-an-error");
    await loadApp();

    // Go through sign-in to set pendingCognitoUser
    const emailInput = document.getElementById("login-email") as HTMLInputElement;
    const passwordInput = document.getElementById(
      "login-password"
    ) as HTMLInputElement;
    const loginForm = document.getElementById("login-form") as HTMLFormElement;

    emailInput.value = "user@test.com";
    passwordInput.value = "temp";
    loginForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );

    await vi.waitFor(() => {
      const npForm = document.getElementById("new-password-form")!;
      expect(npForm.classList.contains("hidden")).toBe(false);
    });

    const newPasswordInput = document.getElementById(
      "new-password-input"
    ) as HTMLInputElement;
    const newPasswordForm = document.getElementById(
      "new-password-form"
    ) as HTMLFormElement;

    newPasswordInput.value = "NewPass123!";
    newPasswordForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );

    await vi.waitFor(() => {
      const loginError = document.getElementById("login-error")!;
      expect(loginError.classList.contains("hidden")).toBe(false);
      expect(loginError.textContent).toBe("Password change failed");
    });
  });

  it("handles getIdToken returning null (no auth header sent)", async () => {
    mockGetIdToken.mockResolvedValue(null);
    const stream = sseStream(['data: {"token": "ok"}\n', "data: [DONE]\n"]);
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve(mockSSEResponse(200, stream));
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Hello";
    askForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );

    await vi.waitFor(() => {
      const askCalls = fetchSpy.mock.calls.filter(
        (c: unknown[]) => c[0] === "/api/ask"
      );
      expect(askCalls.length).toBe(1);
      const [, options] = askCalls[0];
      expect(options.headers["Authorization"]).toBeUndefined();
    });
  });

  it("503 response without detail shows default warming message", async () => {
    await loadApp();

    fetchSpy.mockImplementation((url: string) => {
      if (url === "/api/ask") {
        return Promise.resolve({
          status: 503,
          ok: false,
          headers: new Headers(),
          json: () => Promise.resolve({}),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ cognitoUserPoolId: "x", cognitoClientId: "y" }),
      });
    });

    const inputEl = document.getElementById("question-input") as HTMLInputElement;
    const askForm = document.getElementById("ask-form") as HTMLFormElement;

    inputEl.value = "Test";
    askForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true })
    );

    await vi.waitFor(() => {
      const sb = getStatusBar();
      expect(sb.textContent).toBe("Model is warming up...");
    });
  });
});
