# Security Policy

## Overview

The VoIP SIP Analyzer project takes security seriously. This document outlines our security policies, supported versions, and how to responsibly disclose security vulnerabilities.

We are committed to:
- Addressing security vulnerabilities promptly and responsibly
- Maintaining transparent communication with the security community
- Providing timely security updates and patches
- Following security best practices in our development process

## Supported Versions

We support the following versions with security updates and patches:

| Version | Supported          | Release Date | End of Support |
| ------- | ------------------ | ------------ | -------------- |
| 1.x     | :white_check_mark: | 2026-Q1      | 2027-Q1        |
| 0.x     | :x:                | Early Dev    | 2026-Q3        |

**Version Support:** We maintain security support for the latest major version and the previous major version. Users are encouraged to upgrade to the latest version to receive all security updates.

## Reporting a Vulnerability

### Confidential Disclosure

If you discover a security vulnerability in VoIP SIP Analyzer, **please do not open a public issue**. Instead, report it confidentially to the security team.

**Report vulnerabilities by:**
- Email: security@github.com
- Or use GitHub's private vulnerability reporting: [Security Advisories](https://github.com/eksalih/VoIP_SIP_Analyzer/security/advisories)

**Please include:**
- A clear description of the vulnerability
- Steps to reproduce the issue
- Potential impact and severity
- Any proof-of-concept or additional technical details
- Your contact information

### Response Timeline

- **Initial Response:** Within 48 hours of vulnerability report
- **Initial Assessment:** Within 1 week
- **Security Patch Release:** As soon as possible (target: 2-4 weeks for critical issues)
- **Public Disclosure:** After a patch is released or a reasonable grace period has elapsed

### Vulnerability Assessment

We will assess vulnerabilities based on:
- **Severity:** Critical, High, Medium, Low
- **Scope:** How many users/deployments are affected
- **Exploitability:** How easy is it to exploit
- **Impact:** Potential damage or data loss

## Security Best Practices

### For Users

- **Keep Updated:** Regularly update to the latest version to receive security patches
- **Secure Configuration:** Follow the [README.md](README.md) guidelines for secure deployment
- **Network Security:** Run the application in a secure, isolated network environment
- **Authentication:** Implement strong authentication mechanisms in your deployment
- **Monitoring:** Monitor logs and network traffic for suspicious activity
- **Backups:** Maintain regular backups of your data and configurations

### For Developers

- **Dependency Updates:** Regularly audit and update dependencies
- **Code Review:** All code changes undergo security review
- **Secrets Management:** Never commit secrets, API keys, or credentials
- **Input Validation:** Always validate and sanitize user inputs
- **Error Handling:** Avoid exposing sensitive information in error messages

## Known Security Considerations

### Data Privacy

- The application processes VoIP/SIP traffic. Ensure compliance with local privacy regulations when capturing and storing call data
- Implement proper access controls to limit who can view call information
- Consider encryption at rest and in transit for sensitive data

### Network Security

- Deploy behind a firewall in production
- Use HTTPS/TLS for all web communications
- Restrict access to the application to authorized networks
- Monitor for unusual network activity

### Dependency Vulnerabilities

This project depends on:
- **Backend:** Python with Flask and related packages
- **Frontend:** Node.js with React and TypeScript
- **Database:** SQLite/PostgreSQL

We regularly scan dependencies using:
- GitHub's Dependabot
- OWASP dependency checking
- Community security advisories

## Security Updates Process

1. **Vulnerability Discovery:** Issue reported privately
2. **Verification:** Security team confirms the vulnerability
3. **Fix Development:** Patch is developed and tested
4. **Internal Review:** Code review and security testing
5. **Release:** Patch is released to users
6. **Disclosure:** Public security advisory is published

## Compliance

This project aims to follow:
- OWASP Top 10 principles
- CWE/SANS Top 25 most dangerous software weaknesses
- Security best practices for web applications and APIs

## Acknowledgments

We appreciate the security community's efforts to identify and responsibly disclose vulnerabilities. We will acknowledge researchers (with permission) in our security advisories.

## Questions or Concerns?

If you have questions about this security policy or concerns about the security of this project, please contact the development team through [GitHub Issues](https://github.com/eksalih/VoIP_SIP_Analyzer/issues) (for non-sensitive topics) or through private security channels.
