import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock amazon-cognito-identity-js before importing auth module
const mockAuthenticateUser = vi.fn();
const mockCompleteNewPasswordChallenge = vi.fn();
const mockGetSession = vi.fn();
const mockSignOut = vi.fn();
const mockGetCurrentUser = vi.fn();

vi.mock("amazon-cognito-identity-js", () => {
  return {
    CognitoUserPool: vi.fn().mockImplementation(() => ({
      getCurrentUser: mockGetCurrentUser,
    })),
    CognitoUser: vi.fn().mockImplementation(() => ({
      authenticateUser: mockAuthenticateUser,
      completeNewPasswordChallenge: mockCompleteNewPasswordChallenge,
      getSession: mockGetSession,
      signOut: mockSignOut,
    })),
    AuthenticationDetails: vi.fn(),
  };
});

// Import after mocking
import { initAuth, signIn, completeNewPassword, getIdToken, isAuthenticated, signOut } from "../auth";

describe("auth module", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Re-init for each test
    initAuth({ cognitoUserPoolId: "us-east-1_test", cognitoClientId: "test-client" });
  });

  describe("initAuth", () => {
    it("does not throw", () => {
      expect(() =>
        initAuth({ cognitoUserPoolId: "pool-id", cognitoClientId: "client-id" })
      ).not.toThrow();
    });
  });

  describe("signIn", () => {
    it("resolves with session on success", async () => {
      const mockSession = { getIdToken: () => ({ getJwtToken: () => "jwt-token" }) };
      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { onSuccess: (s: unknown) => void }) => {
        callbacks.onSuccess(mockSession);
      });

      const result = await signIn("user@test.com", "password123");
      expect(result).toHaveProperty("session", mockSession);
    });

    it("resolves with challengeName on NEW_PASSWORD_REQUIRED", async () => {
      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { newPasswordRequired: () => void }) => {
        callbacks.newPasswordRequired();
      });

      const result = await signIn("user@test.com", "password123");
      expect(result).toHaveProperty("challengeName", "NEW_PASSWORD_REQUIRED");
      expect(result).toHaveProperty("cognitoUser");
    });

    it("rejects on failure", async () => {
      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { onFailure: (e: Error) => void }) => {
        callbacks.onFailure(new Error("Incorrect credentials"));
      });

      await expect(signIn("user@test.com", "wrong")).rejects.toThrow("Incorrect credentials");
    });
  });

  describe("completeNewPassword", () => {
    it("resolves with session on success", async () => {
      const mockSession = { isValid: () => true };
      mockCompleteNewPasswordChallenge.mockImplementation(
        (_pw: string, _attrs: unknown, callbacks: { onSuccess: (s: unknown) => void }) => {
          callbacks.onSuccess(mockSession);
        }
      );

      // Get a cognitoUser from signIn challenge flow
      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { newPasswordRequired: () => void }) => {
        callbacks.newPasswordRequired();
      });
      const result = await signIn("user@test.com", "temp");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      const session = await completeNewPassword(result.cognitoUser, "NewPass123!");
      expect(session).toBe(mockSession);
    });
  });

  describe("getIdToken", () => {
    it("returns token when session is valid", async () => {
      const mockSession = {
        isValid: () => true,
        getIdToken: () => ({ getJwtToken: () => "my-jwt-token" }),
      };
      mockGetCurrentUser.mockReturnValue({
        getSession: (cb: (err: null, s: unknown) => void) => cb(null, mockSession),
        signOut: mockSignOut,
      });

      const token = await getIdToken();
      expect(token).toBe("my-jwt-token");
    });

    it("returns null when no current user", async () => {
      mockGetCurrentUser.mockReturnValue(null);

      const token = await getIdToken();
      expect(token).toBeNull();
    });

    it("returns null when session is invalid", async () => {
      mockGetCurrentUser.mockReturnValue({
        getSession: (cb: (err: Error) => void) => cb(new Error("expired")),
        signOut: mockSignOut,
      });

      const token = await getIdToken();
      expect(token).toBeNull();
    });
  });

  describe("isAuthenticated", () => {
    it("returns true when token is available", async () => {
      const mockSession = {
        isValid: () => true,
        getIdToken: () => ({ getJwtToken: () => "token" }),
      };
      mockGetCurrentUser.mockReturnValue({
        getSession: (cb: (err: null, s: unknown) => void) => cb(null, mockSession),
        signOut: mockSignOut,
      });

      expect(await isAuthenticated()).toBe(true);
    });

    it("returns false when no token", async () => {
      mockGetCurrentUser.mockReturnValue(null);

      expect(await isAuthenticated()).toBe(false);
    });
  });

  describe("signOut", () => {
    it("calls signOut on current user", () => {
      const mockUser = { signOut: vi.fn() };
      mockGetCurrentUser.mockReturnValue(mockUser);

      signOut();
      expect(mockUser.signOut).toHaveBeenCalled();
    });

    it("does not throw when no current user", () => {
      mockGetCurrentUser.mockReturnValue(null);

      expect(() => signOut()).not.toThrow();
    });
  });
});
