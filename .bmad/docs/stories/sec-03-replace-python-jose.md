# Replace python-jose with PyJWT

**Epic:** Security Hardening

**Points:** 3

## User Story

As a platform operator, I want to use an actively maintained JWT library so that known CVEs are patched and future vulnerabilities will be addressed.

## Acceptance Criteria

- [ ] `python-jose` is removed from `backend/inference/requirements.txt`
- [ ] `PyJWT[crypto]` (or `joserfc`) is added as a replacement
- [ ] JWT decoding in `app.py` works identically (RS256 verification, issuer check, audience check)
- [ ] All existing auth tests pass with the new library
- [ ] The Dockerfile builds successfully with the new dependency
- [ ] CVE-2024-33663 and CVE-2024-33664 are no longer present in the dependency tree

## Technical Notes

Migration from `python-jose` to `PyJWT`:
- Replace `from jose import JWTError, jwt` with `import jwt` and `from jwt.exceptions import PyJWTError`
- `jwt.decode(token, key, algorithms=["RS256"], issuer=issuer)` API is nearly identical
- `jwt.get_unverified_header(token)` exists in both libraries
- The `key` parameter in PyJWT takes an `RSAPublicKey` object from `cryptography` rather than a raw JWK dict — use `jwt.algorithms.RSAAlgorithm.from_jwk(key_dict)` to convert
- Update exception handling: catch `PyJWTError` instead of `JWTError`
- Pin exact version: `PyJWT[crypto]==2.10.1` (or latest stable)

References:
- [FastAPI recommendation to switch](https://github.com/fastapi/fastapi/discussions/11345)
- [PyJWT docs](https://pyjwt.readthedocs.io/)

## Implementation Subtasks

- [ ] Replace `python-jose[cryptography]` with `PyJWT[crypto]` in `requirements.txt`
- [ ] Update imports in `app.py`
- [ ] Update `jwt.decode` call to use PyJWT API (key conversion, exception types)
- [ ] Update `jwt.get_unverified_header` usage
- [ ] Update all tests in `test_inference_app.py` (mock paths, exception types)
- [ ] Rebuild and test Docker image locally

## Status

~~Todo~~ | ~~In Progress~~ | ~~In Review~~ | **Done**
