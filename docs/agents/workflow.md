# 工作流程細節

`AGENTS.md` 的「工作流程」是摘要，這份是細節。

## 每一步用哪個 skill

已安裝 [mattpocock/skills](https://github.com/mattpocock/skills)（Claude Code plugin；Codex 也能用同一套）。

| 情況 | 用法 |
|---|---|
| 需求或設計還模糊 | `/grill-with-docs`：一題一題問，每題附建議答案，邊問邊更新 `CONTEXT.md` 和 ADR |
| 工作大到一次對話做不完 | `/wayfinder`：在 `docs/changes/<effort>/map.md` 列出要先決定的事，逐一解決 |
| 規劃定案 | `/to-spec` 寫 `spec.md`，`/to-tickets` 拆成可以各自驗證的 issue |
| 實作 | `/implement`；後端能寫測試的地方用 `/tdd` |
| 難搞的 bug | `/diagnosing-bugs`：重現 → 縮小 → 假設 → 加觀測 → 修 → 加回歸測試 |
| 做完要審查 | `/code-review`（對照規範和 spec 兩個方向） |
| 查資料 | `/research`：結果寫成有出處的 markdown |

使用者要求的「規劃 → review → 分階段 → 驗證 → 回報」不因為用了 skill 就省略：
review 時要回報找到的問題，每一階段都要有驗證結果。

## 跨電腦與跨 AI 的交接

- **一個變更一條分支。** 同一時間只有一台電腦在同一條分支上工作；開工前 `git pull`，收工一定 push。
- **先認領再動手。** 把 issue 改成 `Status: claimed`、加上 `Claimed-by:`，push 之後才開始做。
- **交接寫進檔案，不靠對話。** 換對話、換電腦、換 AI 時，把進度、卡住的地方、下一步寫進該 issue 的 `## Comments`。
  注意：`/handoff` 預設寫到作業系統的暫存資料夾，**不會跨電腦**；要跨電腦就寫進 issue。
- **各台電腦上 AI 的「自動記憶」不會同步。** 專案相關的事實與決定一律寫進 repo（`docs/`、ADR、`CONTEXT.md`）；
  記憶只放個人偏好。

## 出貨

### 上 QAT（可以直接做）

1. 功能分支推上去，等 CI 全綠。iOS 分支名要用 `scan-*` 或 `client-*` 才會觸發 CI。
2. 合併進 `develop`（`git merge --no-ff`），push。iOS 會自動簽章並上傳到浮島 QAT 的 TestFlight。
3. 後端改動另外部署到 QAT，指令見 `docs/ops/deploy.md`。
4. 回報 build 號碼，不必傳 .ipa。

### 上正式版（每次都要使用者明確同意）

1. 從 `origin/main` 開分支。要搬的東西如果在 `develop` 上，就用 cherry-pick 一個一個搬過來。
2. **確認沒有多帶東西**：比對兩份 diff，`git diff <工作起點> origin/main` 和 `git diff develop <新分支>`
   要完全一樣，也就是新分支剛好等於「正式版加上要搬的那些改動」。
3. 分支 CI 全綠之後，用 `git merge --no-ff` 合併進 `main`，訊息寫成 `Merge: <這次做了什麼>`；
   合併後確認 main 的 tree 和 CI 測過的 commit 一樣，再 push。iOS 會上傳到浮島的 TestFlight，老師會自動收到。
4. 同一份修正也要合併回 `develop`，避免兩邊分岔。

## CI 常見狀況

- 工作顯示失敗、但一個步驟都沒跑，annotation 寫「failed to be acquired」：這是 GitHub 的 macOS 機器不夠，
  跟程式無關，重跑失敗的工作即可（`gh run rerun <id> --failed`；偶爾會回 500，隔一段時間再試）。
- iOS 的辨識自我測試會印出 `RECOGNITION SELFTEST: n/n passed`；新增檢查時，在 `ios.yml` 也加一行指名的 grep。

## 改到辨識時

改辨識前後都要跑辨識基準，並和上一次的數字比較。基準集與工具見 iOS repo 的 `docs/benchmarks/`。
