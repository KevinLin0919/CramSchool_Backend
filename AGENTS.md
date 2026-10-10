# AGENTS.md — 浮島（補習班批改系統）

寫給所有 AI 助理（Claude Code、Codex、Cursor、Xcode 內的 Claude Agent…）與新加入的人。
開工前讀完這份，再讀 `docs/progress.md`。

## 系統是什麼

老師用 iPhone／iPad 對著學生考卷掃描，App 在手機上即時對位、辨識、批改；
伺服器保存模板、批改結果、影像與帳號。

| Repo | 內容 |
|---|---|
| `CramSchool_Backend`（本 repo） | FastAPI 後端、`web/` 網頁版、部署腳本。**兩個 repo 共用的規範、進度、變更紀錄都放這裡** |
| `CramSchool_IOS` | SwiftUI App「浮島」，裝置端辨識（XFeat 對位、MNIST CNN、○✕ 決策森林） |

YOLO 版面偵測與 OCR 是另外的服務，只在建立模板時用到，不在這兩個 repo。

兩台開發機（Windows／WSL 與 Mac）都可能做任何工作。兩個 repo 請 clone 在**同一個上層資料夾**，
彼此用 `../CramSchool_IOS`、`../CramSchool_Backend` 參照。

## 開工與收工

開工：
1. 兩個 repo 都 `git pull`。
2. 讀 `docs/progress.md`：正式版與 QAT 各是什麼版本、進行中的變更、哪台機器認領了哪件事。
3. 要動哪一塊，就先讀 `CONTEXT.md` 的用語和相關的 `docs/adr/`（iOS 內部的決策在 iOS repo 的 `docs/adr/`）。
4. 接手進行中的工作：讀 `docs/changes/<slug>/` 的 `spec.md` 和 `issues/`，特別是每個 issue 最後的 `## Comments`。

收工或換手：更新 issue 的 `Status:` 與 `## Comments`、更新 `docs/progress.md`、commit 並 push。
**沒 push 的東西，另一台電腦和其他 AI 都看不到。**

## 紅線

- 對使用者的回覆、文件、總結一律**繁體中文**（commit message 沿用現有的英文風格）。
- **不能影響正式版**：合併到 `main`、部署正式後端、寫入正式資料庫（包括 `cramctl` 的寫入指令）
  都要使用者明確同意，而且同意只對那一次有效。唯讀查詢可以直接做。
- 新功能與實驗一律先上 **QAT**（`develop` 分支、浮島 QAT App、QAT 後端）。QAT 可以常推 TestFlight。
- 不直接在 `main` 或 `develop` 上開發：短分支合併進 `develop`；正式版修正從 `main` 開分支，再合併回兩邊。
  iOS 的分支要用 `scan-*` 或 `client-*` 開頭才會跑 CI。
- 密鑰不進 git、不貼進對話：App Store Connect 的 `.p8`、`.env`、AI 服務金鑰、伺服器連線資訊。
- 兩個 repo 目前是 **public**：文件裡不寫老師姓名、帳號、補習班名稱、主機 IP、租戶 ID。
  比賽期間提到合作單位一律寫「合作機構」。這類資訊等 repo 改成 private 後再搬進來。
- 不用傳 .ipa 給使用者：他從 TestFlight 安裝，回報上到哪個 App、build 幾號即可。
- 評估使用者的想法要客觀，不要附和；有更好的做法就直接說。

## 工作流程

比一行修正大的改動，一律照這個順序，並在過程中說明現在在哪一步：

1. **規劃**：目標、設計、明確不做的事。需求不清楚就用 `/grill-with-docs`（或 `/grilling`）
   一題一題問清楚，每題附建議答案。
2. **Review**：自己挑規劃的毛病，並**回報找到了哪些問題**。使用者每次都要求這一步。
3. **分階段實作**：每階段小到能單獨驗證。大的工作用 `/to-spec`、`/to-tickets` 寫進 `docs/changes/`。
4. **驗證**：每階段先說好怎麼驗，驗過才往下一步。沒有 Mac 時 iOS 靠 CI；改到辨識要跑辨識基準。
5. **回報**：附實際量到的數字。

交接、分工、出貨流程的細節見 `docs/agents/workflow.md`。

## AI 分工

每個變更的 `spec.md` 寫明由誰實作：Claude、Codex，或 Mac 上 Xcode 內建的 Claude Agent。
- Codex 只在分支上 commit，**不 push、不部署、不 ssh**；驗證與出貨由 Claude 或使用者負責。
- AI 之間只透過 `docs/changes/` 的檔案與 git 交接，不依賴對話紀錄或某台電腦上的記憶。

## 後端指令

```bash
uv sync --extra dev
.venv/bin/python -m pytest                              # 全部測試
.venv/bin/uvicorn app.main:app --reload --port 8085     # 本機開發，預設 SQLite
cd web && npm ci && npm run dev                         # 網頁版
```

部署、環境、帳號與角色的操作見 `docs/ops/`。

## 文件地圖

| 位置 | 用途 |
|---|---|
| `README.md` | 給使用者的簡介：這個專案在做什麼 |
| `docs/design.md` | 後端的設計說明（為什麼這樣做）、登入、角色、部署、備份 |
| `CONTEXT.md` | 領域用語：模板、母卷、格、待確認… |
| `docs/adr/` | 系統層級的決策紀錄 |
| `docs/progress.md` | 現況看板 |
| `docs/changes/` | 進行中與已完成的變更（spec 與 issues） |
| `docs/ops/` | 環境、部署、帳號角色操作 |
| `docs/agents/` | AI 工作規則與 skills 設定 |

## Agent skills

### Issue tracker

本機 markdown，放在本 repo 的 `docs/changes/<slug>/`，兩個 repo 共用這一份。See `docs/agents/issue-tracker.md`.

### Triage labels

使用預設的五個角色字串。See `docs/agents/triage-labels.md`.

### Domain docs

多 repo：系統層級的用語與決策在本 repo（`CONTEXT.md`、`docs/adr/`），iOS 內部的決策在 iOS repo 的 `docs/adr/`。See `docs/agents/domain.md`.
