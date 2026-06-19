---
description: Start/stop/status of OCVoice voice control
agent: build
---

!`ocv status`

Based on the output above, the user wants to manage OCVoice voice control.
Available actions:
- If voice control is not running: suggest starting it with `!ocv start`
- If voice control is running: offer to stop with `!ocv stop`
- To enroll voice: suggest `!ocv enroll`
- To install auto-start on login (macOS): suggest `!ocv autostart install`

Execute the command the user requests regarding voice control.
