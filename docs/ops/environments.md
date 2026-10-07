# 環境

主機位址與登入帳號**不寫在這裡**（repo 是 public）。各台開發機用自己的 ssh 設定連線；新電腦的設定方式問使用者。

| | 正式版 | QAT |
|---|---|---|
| iOS App | 浮島（`com.cramschool.autogradescanner`） | 浮島 QAT（`com.cramschool.autogradescanner.dev`） |
| TestFlight | 「浮島」群組，老師自動收到 | 「QAT」群組，只有使用者 |
| 分支（兩個 repo） | `main` | `develop` |
| 後端位置（伺服器上） | `~/CramSchool_Backend`，compose 預設專案 | `~/CramSchool_Backend_qat`（worktree，detached 在 `origin/develop`），compose 專案 `cramqat` |
| API 容器 | `cram_api` | `cramqat_api` |
| 對外網址 | Funnel 的 443 埠 | 同一個網址的 8443 埠 |
| 資料庫 | 正式資料，有備份 | 可丟棄的測試資料；模板從正式版複製，有一個模擬班級 |

App 端的預設網址在 iOS repo 的 `APIClient.swift`（`ServerConfig.defaultAPI`），QAT App 會自動連 8443。

## 規則

- 正式環境的任何寫入（部署、改資料、`cramctl` 寫入指令）都要使用者當次明確同意。
- 唯讀查詢可以直接做：在容器裡用 `docker exec -i cram_api python -` 跑只讀的 SQLAlchemy 查詢，或 `cramctl teachers list`、`cramctl tokens list`。
- QAT 的 AI 服務金鑰放在伺服器上的 `.env.qat`，由使用者自己填，不要讀出來或貼進對話。
