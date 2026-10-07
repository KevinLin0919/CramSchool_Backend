# Issue tracker：本機 Markdown

兩個 repo 的 spec 與 issue 都放在**後端 repo** 的 `docs/changes/`，跟著 git 在兩台電腦間同步。
在 iOS repo 工作時，路徑是 `../CramSchool_Backend/docs/changes/`。

## Conventions

- 一個變更一個資料夾：`docs/changes/<slug>/`，slug 用英文小寫加連字號，例如 `choice-options-alphabet`
- spec（也就是 PRD）是 `docs/changes/<slug>/spec.md`，開頭寫 `Status:`（`draft`／`active`／`done`）、
  `Repos:`（影響哪些 repo）、`Implementer:`（Claude／Codex／Xcode Claude Agent／使用者）
- 實作用的 issue 一張一個檔案：`docs/changes/<slug>/issues/<NN>-<slug>.md`，從 `01` 開始編號，不要把所有 ticket 寫進同一個檔案
- 每張 issue 開頭有 `Status:` 一行（字串見 `triage-labels.md`，另外可用 `claimed`／`resolved`），
  認領時加一行 `Claimed-by: <mac|wsl> <AI 名稱> <日期>`
- 討論與工作紀錄一律附加在檔案最後的 `## Comments` 底下，一筆一段，開頭寫日期、機器、誰
- 變更完成時把 spec 的 `Status:` 改成 `done`，資料夾保留不刪，當作歷史紀錄

## When a skill says "publish to the issue tracker"

在 `docs/changes/<slug>/` 底下建立新檔案（資料夾不存在就建立），並在 `docs/progress.md` 的「進行中」加一行指向它。

## When a skill says "fetch the relevant ticket"

讀使用者給的路徑或編號對應的檔案。

## Wayfinding operations

給 `/wayfinder` 用。**map** 是一個檔案，每張 ticket 一個 child 檔案。

- **Map**：`docs/changes/<effort>/map.md`，內容是 Notes／Decisions-so-far／Fog
- **Child ticket**：`docs/changes/<effort>/issues/NN-<slug>.md`，從 `01` 編號；`Type:` 一行記 ticket 類型（`research`／`prototype`／`grilling`／`task`），`Status:` 一行記 `claimed`／`resolved`
- **Blocking**：開頭附近一行 `Blocked by: NN, NN`；列出的檔案都 `resolved` 才算解除封鎖
- **Frontier**：掃 `issues/` 找出未結、未封鎖、未認領的檔案，編號小的先做
- **Claim**：先把 `Status: claimed` 存檔並 push，再開始做事（避免兩台電腦同時認領）
- **Resolve**：在 `## Answer` 底下寫答案，設 `Status: resolved`，再把一行摘要加上連結補進 `map.md` 的 Decisions-so-far
