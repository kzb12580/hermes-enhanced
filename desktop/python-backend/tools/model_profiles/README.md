# Model Profiles (Hot-Update)

Drop `.md` files here to override model-specific system prompts.

## File naming
- `{family}.md` — OVERRIDES the hardcoded profile for that family
- `{family}.extra.md` — APPENDS to the hardcoded profile (extend, not replace)

## Supported families
mimo, deepseek, claude, gpt, gemini, qwen, llama, mistral, glm, moonshot, yi, internlm, grok, default

## Example
To add custom rules for MIMO without replacing the hardcoded profile:
Create `mimo.extra.md` with your additional rules.
