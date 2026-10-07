# AI 協作流程與文件

Status: active
Repos: CramSchool_Backend, CramSchool_IOS
Implementer: Claude

## Problem Statement

使用者有兩台開發機（Windows／WSL 與新買的 Mac），也會用不同的 AI（Claude Code、Codex、Xcode 內的 Claude Agent）。過去專案知識散在三個地方：程式註解、README，以及某一台電腦上 AI 的「自動記憶」。換電腦或換 AI 就得從頭解釋；做到一半的工作也沒有固定的地方交接。

## Solution

把專案知識和進度搬進 git，所有 AI、兩台電腦都讀同一份：

- 每個 repo 根目錄有 `AGENTS.md`，Claude Code、Codex、Cursor 都會自動讀。共同規範放在後端 repo 的那份。
- `CONTEXT.md` 定義用語，`docs/adr/` 記錄重要決策。
- `docs/progress.md` 是現況看板；`docs/changes/` 是每個變更的 spec、issue 和交接紀錄。
- 流程沿用已安裝的 mattpocock/skills（grill、spec、tickets、implement、code-review、wayfinder），設定在 `docs/agents/`。

## User Stories

1. 身為使用者，我在 Mac 上開一個新的 AI 對話，它讀完 `AGENTS.md` 和 `progress.md` 就知道現況，不必我重講。
2. 身為使用者，我想知道某件事做到哪、誰在做，打開 `progress.md` 就看得到。
3. 身為接手的 AI，我從 issue 的 `## Comments` 知道上一個 AI 做到哪、卡在哪。
4. 身為 AI，我在動手前就知道紅線：正式版要使用者同意、先上 QAT、密鑰不進 git、public repo 不寫敏感資訊。
5. 身為 Codex，我照 issue 實作、只 commit 不 push，驗證交給 Claude。

## Implementation Decisions

- 決策日期 2026-10-08。追蹤方式：`docs/changes/` 加 `progress.md`（不用 GitHub Issues，也不用 Beads）。
- 兩台電腦都做所有事；AI 由每個變更的 spec 指定實作者。
- 兩個 repo 暫時維持 public（比賽期間）。敏感的營運資訊留在使用者那邊，repo 改 private 後再搬進來。
- 共用的規範、進度、變更紀錄只放後端 repo 一份；iOS repo 的 `AGENTS.md` 指向 `../CramSchool_Backend`。

## Testing Decisions

- 文件裡不能出現敏感字串（老師姓名、主機 IP、租戶 ID、補習班名稱），提交前用 grep 檢查。
- `AGENTS.md` 控制在 150 行內（太長 AI 比較不會照做）。
- 用一個新的 AI 對話實際試讀，確認它能說出現況與紅線。

## Out of Scope

- 不改任何 App 或後端的行為。
- 不把 repo 改成 private（比賽結束後另外做）。

## Further Notes

調查的來源與比較見使用者在對話中確認過的結論：AGENTS.md 是跨工具標準（Claude Code 2.1.277 起支援）；Agent Skills 是跨工具的技能格式；自動記憶只存在單一台電腦。
