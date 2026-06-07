<!--
Thank you for your contribution! Please fill out the sections below.
-->

**Description of Changes**
A clear and concise summary of what changes were made, and the rationale behind them.

**Related Issue**
Closes #[issue-number] (or links to related issues).

**Type of Change**
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

**Verification Checklist**
- [ ] All code changes follow the style conventions (Clean code, type hints where appropriate).
- [ ] Tested locally with target Ollama models.
- [ ] Ran verification tests (`python tests/test_identity.py` etc.) and they pass cleanly.
- [ ] No secrets, private paths, or personal credentials are committed (verified with `git diff`).
- [ ] Changes are drive-agnostic (using `PATHS` helper and relative paths).
- [ ] The `launch.py` bootstrapper has been tested and starts up without issues.
