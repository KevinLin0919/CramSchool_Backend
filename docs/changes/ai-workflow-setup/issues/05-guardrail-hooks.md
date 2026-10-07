# 用 hook 強制紅線

Status: needs-triage
Blocked by: 01

`AGENTS.md` 只是參考，AI 不一定照做。把最重要的紅線寫成 Claude Code 的 PreToolUse hook，設定檔放進 repo，兩台電腦一起生效：推 `main`、部署正式後端、對正式資料庫寫入時，先擋下來要求確認。可參考 mattpocock/skills 的 `git-guardrails-claude-code`。
