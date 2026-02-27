import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock amazon-cognito-identity-js before importing auth module
const mockAuthenticateUser = vi.fn();
const mockCompleteNewPasswordChallenge = vi.fn();
const mockSendMFACode = vi.fn();
const mockAssociateSoftwareToken = vi.fn();
const mockVerifySoftwareToken = vi.fn();
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
      sendMFACode: mockSendMFACode,
      associateSoftwareToken: mockAssociateSoftwareToken,
      verifySoftwareToken: mockVerifySoftwareToken,
      getSession: mockGetSession,
      signOut: mockSignOut,
    })),
    AuthenticationDetails: vi.fn(),
  };
});

// Import after mocking
import { initAuth, signIn, completeNewPassword, verifyTotp, associateSoftwareToken, verifySoftwareToken, getIdToken, isAuthenticated, signOut } from "../auth";

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

    it("passes sessionStorage to CognitoUserPool", async () => {
      const { CognitoUserPool } = await import("amazon-cognito-identity-js");
      initAuth({ cognitoUserPoolId: "pool-id", cognitoClientId: "client-id" });
      expect(CognitoUserPool).toHaveBeenCalledWith(
        expect.objectContaining({ Storage: window.sessionStorage })
      );
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

    it("rejects on failure", async () => {
      mockCompleteNewPasswordChallenge.mockImplementation(
        (_pw: string, _attrs: unknown, callbacks: { onFailure: (e: Error) => void }) => {
          callbacks.onFailure(new Error("Password does not meet requirements"));
        }
      );

      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { newPasswordRequired: () => void }) => {
        callbacks.newPasswordRequired();
      });
      const result = await signIn("user@test.com", "temp");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      await expect(completeNewPassword(result.cognitoUser, "weak")).rejects.toThrow(
        "Password does not meet requirements"
      );
    });
  });

  describe("signIn — MFA challenges", () => {
    it("resolves with SOFTWARE_TOKEN_MFA challenge", async () => {
      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { totpRequired: () => void }) => {
        callbacks.totpRequired();
      });

      const result = await signIn("user@test.com", "password123");
      expect(result).toHaveProperty("challengeName", "SOFTWARE_TOKEN_MFA");
      expect(result).toHaveProperty("cognitoUser");
    });

    it("resolves with MFA_SETUP challenge", async () => {
      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { mfaSetup: () => void }) => {
        callbacks.mfaSetup();
      });

      const result = await signIn("user@test.com", "password123");
      expect(result).toHaveProperty("challengeName", "MFA_SETUP");
      expect(result).toHaveProperty("cognitoUser");
    });
  });

  describe("verifyTotp", () => {
    it("resolves with session on success", async () => {
      const mockSession = { isValid: () => true };
      mockSendMFACode.mockImplementation(
        (_code: string, callbacks: { onSuccess: (s: unknown) => void }, _type: string) => {
          callbacks.onSuccess(mockSession);
        }
      );

      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { totpRequired: () => void }) => {
        callbacks.totpRequired();
      });
      const result = await signIn("user@test.com", "pass");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      const session = await verifyTotp(result.cognitoUser, "123456");
      expect(session).toBe(mockSession);
      expect(mockSendMFACode).toHaveBeenCalledWith("123456", expect.any(Object), "SOFTWARE_TOKEN_MFA");
    });

    it("rejects on failure", async () => {
      mockSendMFACode.mockImplementation(
        (_code: string, callbacks: { onFailure: (e: Error) => void }, _type: string) => {
          callbacks.onFailure(new Error("Invalid code"));
        }
      );

      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { totpRequired: () => void }) => {
        callbacks.totpRequired();
      });
      const result = await signIn("user@test.com", "pass");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      await expect(verifyTotp(result.cognitoUser, "000000")).rejects.toThrow("Invalid code");
    });
  });

  describe("associateSoftwareToken", () => {
    it("resolves with secret code", async () => {
      mockAssociateSoftwareToken.mockImplementation(
        (callbacks: { associateSecretCode: (s: string) => void }) => {
          callbacks.associateSecretCode("JBSWY3DPEHPK3PXP");
        }
      );

      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { mfaSetup: () => void }) => {
        callbacks.mfaSetup();
      });
      const result = await signIn("user@test.com", "pass");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      const secret = await associateSoftwareToken(result.cognitoUser);
      expect(secret).toBe("JBSWY3DPEHPK3PXP");
    });

    it("rejects on failure", async () => {
      mockAssociateSoftwareToken.mockImplementation(
        (callbacks: { onFailure: (e: Error) => void }) => {
          callbacks.onFailure(new Error("Association failed"));
        }
      );

      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { mfaSetup: () => void }) => {
        callbacks.mfaSetup();
      });
      const result = await signIn("user@test.com", "pass");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      await expect(associateSoftwareToken(result.cognitoUser)).rejects.toThrow("Association failed");
    });
  });

  describe("verifySoftwareToken", () => {
    it("resolves with session on success", async () => {
      const mockSession = { isValid: () => true };
      mockVerifySoftwareToken.mockImplementation(
        (_code: string, _name: string, callbacks: { onSuccess: (s: unknown) => void }) => {
          callbacks.onSuccess(mockSession);
        }
      );

      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { mfaSetup: () => void }) => {
        callbacks.mfaSetup();
      });
      const result = await signIn("user@test.com", "pass");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      const session = await verifySoftwareToken(result.cognitoUser, "123456");
      expect(session).toBe(mockSession);
    });

    it("rejects on failure", async () => {
      mockVerifySoftwareToken.mockImplementation(
        (_code: string, _name: string, callbacks: { onFailure: (e: Error) => void }) => {
          callbacks.onFailure(new Error("Verification failed"));
        }
      );

      mockAuthenticateUser.mockImplementation((_details: unknown, callbacks: { mfaSetup: () => void }) => {
        callbacks.mfaSetup();
      });
      const result = await signIn("user@test.com", "pass");
      if (!("cognitoUser" in result)) throw new Error("Expected challenge");

      await expect(verifySoftwareToken(result.cognitoUser, "000000")).rejects.toThrow("Verification failed");
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

describe("auth module — before initAuth", () => {
  it("signIn throws when auth not initialized", async () => {
    // Re-import a fresh module without calling initAuth
    vi.resetModules();
    const freshAuth = await import("../auth");
    expect(() => freshAuth.signIn("user@test.com", "pass")).toThrow(
      "Auth not initialized"
    );
  });

  it("getIdToken returns null when auth not initialized", async () => {
    vi.resetModules();
    const freshAuth = await import("../auth");
    const token = await freshAuth.getIdToken();
    expect(token).toBeNull();
  });

  it("signOut does not throw when auth not initialized", async () => {
    vi.resetModules();
    const freshAuth = await import("../auth");
    expect(() => freshAuth.signOut()).not.toThrow();
  });
});
