| Agent | Variant | Expected | Observed (x3) | Disk | Reproduced |
|---|---|---|---|---|---|
| tool_calling_agent | `chat-length` | not-executed | not-executed, not-executed, not-executed | — | yes |
| tool_calling_agent | `chat-drop` | executed 16/40 866B f88cc9ab | executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab | 16 lines / 866B | yes |
| tool_calling_agent | `responses-incomplete` | executed 16/40 866B f88cc9ab | executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab | 16 lines / 866B | yes |
| tool_calling_agent | `responses-drop` | executed 16/40 866B f88cc9ab | executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab | 16 lines / 866B | yes |
| react_agent | `chat-length` | executed 16/40 866B f88cc9ab | executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab | 16 lines / 866B | yes |
| react_agent | `chat-drop` | executed 16/40 866B f88cc9ab | executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab | 16 lines / 866B | yes |
| react_agent | `responses-incomplete` | executed 16/40 866B f88cc9ab | executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab | 16 lines / 866B | yes |
| react_agent | `responses-drop` | executed 16/40 866B f88cc9ab | executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab, executed 16/40 866B f88cc9ab | 16 lines / 866B | yes |
