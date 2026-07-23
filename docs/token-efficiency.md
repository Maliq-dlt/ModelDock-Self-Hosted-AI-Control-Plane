# Token Efficiency

ModelDock TokenPress reduces request overhead while preserving model capability. Default mode is `off`; clients opt in per request using `modeldock.token_mode`. Project admins can set inherited policy; explicit request mode wins.

## Modes

| Mode | Input action | Output action | Capability contract |
| --- | --- | --- | --- |
| `off` | none | none | exact compatibility |
| `safe` | compact tool JSON, strip ANSI, normalize line endings | none | lossless tool-data representation |
| `caveman` | `safe` | concise response guidance | preserve technical detail and requested content |
| `ponytail` | `safe` | smallest-sufficient-code guidance | preserve validation, security, accessibility, and behavior |
| `stacked` | `safe` | Caveman + Ponytail guidance | same contract |

## Capability Contract

TokenPress never: compresses user/system messages, truncates model output, changes `max_tokens`, removes tools, changes tool schemas, or summarizes code. Provider adapter receives full optimized messages. Output post-processing is `none`.

`caveman` and `ponytail` reduce verbosity through explicit instruction, not output deletion. Model can still return full code, warnings, commands, errors, and explanations when requested.

## Trace

Each optimized request stores non-sensitive stats under `metadata.token_efficiency`:

- mode;
- input token estimate before/after;
- input tokens saved/delta;
- compacted tool message count;
- lossless input flag;
- output transform.

Payload content remains governed by `LOG_PAYLOADS`.

## CLI

```powershell
Get-Content request.json | python scripts/tokenpress.py --mode stacked
python scripts/tokenpress.py request.json --mode safe
```

CLI emits `{request, stats}` JSON. It makes no provider request.

## Ceiling

Current compression ceiling is safe formatting and JSON compaction. Retrieval-backed chunking needs a context store, stable chunk IDs, and a provider/tool contract; add only as a separate stage with recall tests.
