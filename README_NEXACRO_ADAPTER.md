# Nexacro Adapter

This stage adds a Nexacro-specific planning layer on top of the common analysis/backend engine.

Included:
- app/adapters/nexacro/*
- app/ui/nexacro_bridge.py
- Prompt injection block: [NEXACRO GENERATION PLAN - SOURCE OF TRUTH]
- Validation and auto-repair integration for Nexacro plans
- Smoke tests for engine / integration / validation

Core fixed rules:
- Nexacro root: frontend/nexacro
- Forms: .xfdl
- Transaction wrappers: .xjs
- Dataset metadata: .json
- Auth domains may generate only login/auth flow artifacts
