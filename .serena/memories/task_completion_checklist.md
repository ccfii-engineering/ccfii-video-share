# Task Completion Checklist

When finishing a code change:

1. **Run tests** for affected areas (at minimum the three listed in README):
   ```bash
   python -m pytest tests/test_frame_parser.py -q
   python -m pytest tests/test_startup.py -q
   python -m pytest tests/test_desktop_app.py -q
   ```
2. **Smoke test** the launcher if UI or startup changed:
   ```bash
   python launcher.py
   ```
3. **Manual verification matrix** (per README) — choose items relevant to the change:
   - Windows display capture / window capture / portable build / installer build
   - macOS display capture / Screen Recording permission onboarding
   - Diagnostics copy/paste workflow
4. **No linter/formatter is configured** in the repo — no auto-format step required. Match surrounding style.
5. Only commit when the user explicitly asks.
