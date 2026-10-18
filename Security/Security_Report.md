# Security Testing Report: Transflow-NiHao-Cash

## Purpose

We ran the project’s existing automated tests to check key security-related behavior in the backend. The project uses synthetic demo financial data and simulated remittance calculations.

## Method

From the project’s `backend` folder, we ran:

```bash
python -m pytest -q tests/test_agent.py tests/test_actions_and_limits.py tests/test_sanitize.py tests/test_remittance_sim.py
```

## Result

**74 tests passed in 34.32 seconds.** No test failures were reported.

The selected test files cover areas including:

- The AI’s allowed backend tools and validation of tool arguments
- Scoping data access to the selected demo user
- Confirmation requirements for proposed actions
- Masking of some common sensitive patterns in data sent to the AI
- Ensuring remittance calculations are simulations and do not execute transfers

## Security limitations

Passing tests shows that the tested behaviors worked in this run; it does not prove the application is free from security vulnerabilities.

The project identifies users with an `X-Demo-User` header. This supports switching between demo personas, but it is not real authentication: a caller could change the header to select another demo user. The PII masking is pattern-based and may miss sensitive information. The remittance feature provides simulated quotes; it does not send money.

This test run did not use a live bank connection or verify real financial transfers. It also did not include a separate penetration test or a test against a live OpenAI model.

## Conclusion

The selected automated tests passed, providing evidence that several existing safeguards behave as expected with the project’s demo setup. Real authentication, more complete PII protection, and broader security testing would be needed before using real user or financial data.
