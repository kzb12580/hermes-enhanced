---
name: ecc-security-review
description: "Security checklist for auth, input validation, injection, CSRF, rate limiting, secrets management. Use before deployment or when adding auth/payment features."
category: ecc
origin: everything-claude-code
---

# Security Review Checklist

Comprehensive security review for web applications and APIs.

## Authentication & Authorization
- [ ] Passwords hashed with bcrypt/argon2 (never MD5/SHA1)
- [ ] JWT tokens have expiry and are validated
- [ ] Session management secure (httpOnly, secure, sameSite cookies)
- [ ] Role-based access control implemented
- [ ] OAuth flows validate state parameter
- [ ] API keys rotated regularly

## Input Validation
- [ ] All user input validated at service boundaries
- [ ] SQL queries use parameterized statements
- [ ] NoSQL queries validate input types
- [ ] File uploads validated (type, size, content)
- [ ] Email/phone/address validated with proper libraries

## XSS Prevention
- [ ] Output encoding for all dynamic content
- [ ] Content Security Policy (CSP) headers set
- [ ] No innerHTML with user content
- [ ] HTTPOnly cookies for session tokens

## CSRF Protection
- [ ] CSRF tokens on all state-changing forms
- [ ] SameSite cookie attribute set
- [ ] Origin/Referer header validation

## Rate Limiting
- [ ] Login endpoint rate limited
- [ ] API endpoints rate limited
- [ ] Password reset rate limited
- [ ] Account lockout after failed attempts

## Secrets Management
- [ ] No secrets in code or config files
- [ ] Environment variables for sensitive config
- [ ] Secrets rotated regularly
- [ ] Access to secrets audited

## Dependencies
- [ ] Known vulnerabilities checked (npm audit, pip audit)
- [ ] Dependencies pinned to specific versions
- [ ] Lock files committed
- [ ] Unused dependencies removed

## Logging & Monitoring
- [ ] Security events logged (login, logout, failed auth)
- [ ] Logs don't contain passwords or tokens
- [ ] Alerting on suspicious patterns
- [ ] Error messages don't leak internals

## HTTPS & Transport
- [ ] TLS enforced everywhere
- [ ] HSTS header set
- [ ] Certificate pinning for mobile apps
- [ ] Secure redirect from HTTP to HTTPS
