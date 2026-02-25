/**
 * Cognito authentication module using amazon-cognito-identity-js.
 * Handles sign-in, token management, forced password change, and sign-out.
 */

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
} from "amazon-cognito-identity-js";

let userPool: CognitoUserPool | null = null;

export interface AuthConfig {
  cognitoUserPoolId: string;
  cognitoClientId: string;
}

export function initAuth(config: AuthConfig): void {
  userPool = new CognitoUserPool({
    UserPoolId: config.cognitoUserPoolId,
    ClientId: config.cognitoClientId,
  });
}

/**
 * Sign in with email and password using SRP auth.
 * Resolves with { session } on success, or { challengeName, cognitoUser }
 * if a challenge (e.g. NEW_PASSWORD_REQUIRED) is returned.
 */
export function signIn(
  email: string,
  password: string
): Promise<
  | { session: CognitoUserSession }
  | { challengeName: string; cognitoUser: CognitoUser }
> {
  if (!userPool) throw new Error("Auth not initialized");

  const cognitoUser = new CognitoUser({
    Username: email,
    Pool: userPool,
  });

  const authDetails = new AuthenticationDetails({
    Username: email,
    Password: password,
  });

  return new Promise((resolve, reject) => {
    cognitoUser.authenticateUser(authDetails, {
      onSuccess(session: CognitoUserSession) {
        resolve({ session });
      },
      onFailure(err: Error) {
        reject(err);
      },
      newPasswordRequired() {
        resolve({ challengeName: "NEW_PASSWORD_REQUIRED", cognitoUser });
      },
    });
  });
}

/**
 * Complete the NEW_PASSWORD_REQUIRED challenge.
 */
export function completeNewPassword(
  cognitoUser: CognitoUser,
  newPassword: string
): Promise<CognitoUserSession> {
  return new Promise((resolve, reject) => {
    cognitoUser.completeNewPasswordChallenge(newPassword, {}, {
      onSuccess(session: CognitoUserSession) {
        resolve(session);
      },
      onFailure(err: Error) {
        reject(err);
      },
    });
  });
}

/**
 * Get the current ID token JWT string, or null if not authenticated.
 * The SDK handles token refresh automatically via the refresh token.
 */
export function getIdToken(): Promise<string | null> {
  if (!userPool) return Promise.resolve(null);

  const currentUser = userPool.getCurrentUser();
  if (!currentUser) return Promise.resolve(null);

  return new Promise((resolve) => {
    currentUser.getSession(
      (err: Error | null, session: CognitoUserSession | null) => {
        if (err || !session || !session.isValid()) {
          resolve(null);
        } else {
          resolve(session.getIdToken().getJwtToken());
        }
      }
    );
  });
}

/**
 * Check if a user is currently authenticated with a valid session.
 */
export async function isAuthenticated(): Promise<boolean> {
  const token = await getIdToken();
  return token !== null;
}

/**
 * Sign out the current user (local sign-out — clears tokens from storage).
 */
export function signOut(): void {
  if (!userPool) return;
  const currentUser = userPool.getCurrentUser();
  if (currentUser) {
    currentUser.signOut();
  }
}
