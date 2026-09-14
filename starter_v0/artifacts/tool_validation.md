# Tool Interface Validation Evidence

- Date: 2026-09-14 19:31 +07:00
- Working directory: `starter_v0/`
- Artifact: `v4+p96bf45bdccad+t57fbc19aa3bb`
- Scope: environment, declaration/registry/docs sync, deterministic local smoke,
  external-tool no-key/privacy preflight, and live provider structured-call
  preflight.

## Environment

Command interpreter: `.venv/Scripts/python.exe`.

```text
Python 3.13.15
PyYAML 6.0.3
requests 2.34.2
openai 3.13.0
anthropic 1.5.0
google-genai 2.23.0
.venv present: yes (gitignored)
.env present: yes (gitignored)
OPENROUTER_API_KEY present: yes
OPENAI_API_KEY present: no
ANTHROPIC_API_KEY present: no
GEMINI_API_KEY present: no
TAVILY_API_KEY present: no
```

Only key presence was printed; no key value was logged. `python-dotenv` is not a
dependency: this repository intentionally loads `.env` through `env_loader.py`.

Compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall -q .
```

Result: PASS, exit code 0.

## Interface and local smoke

Reproducible command:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_tools.py
```

Before the declaration change, 14/16 checks passed. The two failures were:

```text
FAIL clarify requires question and response_type - required was [question]
FAIL create_ticket requires executable confirmation - required was [summary], confirmed enum absent
```

After the declaration change:

```text
PASS declaration names are unique (9 declarations)
PASS tools.yaml matches runtime registry
PASS tools.yaml matches TOOL.md folders
PASS schema arguments match implementation signatures
PASS clarify requires question and response_type
PASS create_ticket requires executable confirmation
PASS clarify local smoke
PASS search_kb local smoke (1 result plus trust boundary)
PASS check_service_status local smoke
PASS inspect_device local smoke
PASS lookup_user local smoke
PASS format_incident_report local smoke
PASS policy local smoke (2 results plus trust boundary)
PASS create_ticket defensive dry-run (0 existing files; 0 new files)
PASS create_ticket confirmed path in temporary directory
PASS search_device_info privacy and no-key preflight
ALL PASS (16/16)
```

The confirmed ticket branch was redirected to a temporary directory that was
automatically removed. The project `tickets/` directory was not created and no
submission artifact was written.

The external search was not called live because `TAVILY_API_KEY` is absent.
The deterministic preflight still verified that an internal ID is rejected as
`restricted_internal_identifier` and a safe public query without a key returns
`missing_api_key` before any network call.

## Provider preflight

Command:

```powershell
.\.venv\Scripts\python.exe scripts\preflight_provider.py --provider openrouter
```

Observed result:

```text
OK provider=openrouter model=openai/gpt-4o-mini
tool=check_service_status
args={'service': 'vpn', 'environment': 'production'}
```

Conclusion: the selected provider accepted the v4 declaration and returned a
structured tool call with the intended shared-service arguments. This preflight
does not measure full routing accuracy; group/base/adversarial reruns remain
necessary to validate the interface hypothesis.

## Implementation decision

No `tools/*/tool.py` implementation was changed. Deterministic behavior passed,
including the defensive `confirmed is True` check, sensitive-data rejection,
trust-boundary output for retrieved content, and no-write behavior before
confirmation. The verified defects were model-facing contract defects, so the
change is limited to `artifacts/tools.yaml`, relevant `TOOL.md` files, the smoke
harness, version log, and report.
