# 補習班批改系統 API

考卷模板、批改結果、影像儲存與教師帳號。取代原本的
[`CramSchool_Storing`](https://github.com/KevinLin0919/CramSchool_Storing)
（Flask + SQLite、單一 JSON blob 欄位、無認證、無 migration）。

供 [`CramSchool_IOS`](https://github.com/KevinLin0919/CramSchool_IOS) 使用。
**API 文件**：服務啟動後開 `/docs`（OpenAPI 自動產生）。

> 這不是系統的全部後端。YOLO 版面偵測與 OCR 辨識是另外的服務，
> 目前仍在 `cram_school_docker`。這個 repo 負責的是**擁有資料的那一層**。

---

## 為什麼重寫而不是修補

| | 舊服務 | 現在 |
|---|---|---|
| 認證 | 無——連得到就能刪光所有模板 | 每台裝置一組可撤銷的 token |
| 題目識別 | 陣列位置（刪一格，後面全錯位） | 穩定 `question_no` |
| 座標 | 800×600 畫布空間，含黑邊偏移 | 相對母卷的 0..1，自我描述 |
| 年級科目 | 由客戶端比對名稱字串猜 | 真正的欄位 |
| 批改結果 | **完全沒存** | `grading_sessions` + `graded_answers` |
| 影像 | base64 塞在 JSON 裡 | multipart + sha256 去重 |
| Schema 演進 | `CREATE TABLE IF NOT EXISTS` | Alembic migration |
| 併發寫入 | 靠 `-w 1` 單 worker 迴避鎖 | Postgres，多 worker |

---

## 本機開發

```bash
uv venv .venv && uv pip install --python .venv -e ".[dev]"
.venv/bin/python -m pytest              # 53 項
.venv/bin/uvicorn app.main:app --reload --port 8085
```

預設連 SQLite（`dev.db`），不需要任何外部服務。正式環境走 Postgres——
所有查詢都經過 SQLAlchemy，就是為了讓這個選擇維持一行設定的成本。

```bash
.venv/bin/cramctl teachers add "林老師" --admin
.venv/bin/cramctl teachers invite 1     # 邀請碼只顯示一次
```

---

## 部署

```bash
cp .env.example .env      # 填 POSTGRES_PASSWORD
docker compose up -d --build
docker compose exec api cramctl teachers add "王老師"
docker compose exec api cramctl teachers invite 1
```

Migration 在容器啟動時自動套用。跑不過就不啟動——不會讓服務對著看不懂的
schema 提供服務。

### 綁在哪個介面

`API_BIND` 決定 API 回應哪個網路介面，預設 `127.0.0.1`——安全的選擇是
什麼都不做就會得到的那個。

| 值 | 誰連得到 | 適用 |
|---|---|---|
| `127.0.0.1` | 只有本機 | 搭配 `tailscale serve` |
| `100.x.x.x` | tailnet 內的裝置 | 老師裝 Tailscale |
| `192.168.x.x` | 補習班 WiFi | **老師只在補習班批改** |

⚠️ 不要填 `0.0.0.0`——那會同時開放所有介面，包含你沒想到的那些。

### 選配：Tailscale Serve（好記的網址 + 合法憑證）

```bash
tailscale serve --bg 8085     # → https://<主機名>.<tailnet>.ts.net
```

Tailscale 用 DNS-01 申請 Let's Encrypt **正式憑證**並自動續期，
所以 iOS 端可以拿掉 `NSAllowsArbitraryLoads`——App Store 審核會追問那一條。

⚠️ **Serve 只在 tailnet 內有效，不會讓服務對公開網路開放。** 老師仍需裝
Tailscale。要對外開放是另一個功能（Funnel），那會讓 API 上公開網路，
屆時 token 認證就是唯一防線。

需要在 tailnet 管理端啟用兩個開關（Owner/Admin 權限）：
**HTTPS Certificates**（Admin → DNS）與 **Serve**。

> 憑證透明度日誌會**公開**主機名與 tailnet 名稱。
> 不要把機器取名成 `補習班-學生資料`。

### 老師的裝置怎麼連

每台 iPad／iPhone 裝 Tailscale App 並登入同一個 tailnet。免費方案是
6 個使用者、裝置數不限。

多台裝置掛同一個 Tailscale 帳號是可以的，因為
**Tailscale 不是身分層**——本服務自己有 per-teacher token，
每台裝置一組、可個別撤銷，所以 App 這邊照樣分得出誰是誰。

---

## 從舊服務搬資料

先試跑：

```bash
docker compose exec api python -m scripts.import_legacy \
    --legacy-db /legacy/templates.db \
    --legacy-uploads /legacy/uploads/templates \
    --dry-run
```

沒問題再拿掉 `--dry-run`。可以**重複執行**——以原本的 id 比對，
第二次是更新而不是複製。原始 id 會保留。

`tests/test_import_legacy.py` 是這條路徑的回歸測試：用一份與
`CramSchool_Storing/main.py` 完全相同的 schema 建假資料，
驗證 bbox 位置、題號、年級科目分類與重跑行為。

座標轉換（`app/coords.py`）是**完全可逆**的仿射映射，搬過來不會有位移。
舊的 `/api/exam-templates` 介面本身已經移除——網頁前端不再開發——但這段
轉換邏輯保留給匯入用。

---

## 備份

資料庫與影像是分開的兩件事，兩個都要備。

```bash
docker compose exec -T db pg_dump -U cram cramschool | gzip > backups/db-$(date +%F).sql.gz

# volume 名稱由 compose 從「目錄名」推導，不是 repo 名 —— 先問出來再用，
# 免得目錄改名之後備份到一個不存在的 volume 而毫無錯誤訊息。
VOL=$(docker volume ls --format '{{.Name}}' | grep api_data$)
docker run --rm -v "$VOL":/data -v "$PWD/backups:/b" \
    alpine tar czf /b/blobs-$(date +%F).tar.gz -C /data blobs
```

`derivatives/` 不用備份——那是快取，刪掉只會重算。

---

## 設計說明

### 認證用不透明 token，不是 JWT

真正需要的動作是「老師的 iPad 掉了，現在就要停掉」。JWT 沒辦法撤銷，
除非再建一張查詢表——那就等於這裡的 token 表了。

存的是 SHA-256 而非 bcrypt，是刻意的：token 是 256 bit 的 `secrets` 輸出，
沒有字典可以猜，慢雜湊要防的攻擊在這裡不存在。

### 時間戳由 Python 產生，不用資料庫

SQLite 的 `CURRENT_TIMESTAMP` 只有**秒**的精度，同一秒內的兩次修改看起來
完全一樣，增量同步的游標會直接跨過其中一次。Postgres 有微秒，但 `now()`
是**交易開始時間**，同一交易內每一列都相同——規模較小但性質一樣的問題。

`UTCDateTime` 處理另一半：SQLite 沒有帶時區的型別，會默默把 offset 丟掉。
統一在寫入時正規化、讀出時補回 UTC，兩個後端行為才會一致。

### 冪等上傳

批改結果走 `PUT /api/v1/grading-sessions/{client_uuid}`，UUID 由手機產生。
補習班的 Wi-Fi 一定會在某次上傳到一半斷掉；用 POST 的話重送就多一筆
重複的批改紀錄。

### 只有內容定址的網址可以說 `immutable`

`/api/v1/images/{id}/content` 可以，而且說了：`images` 的 sha256 一旦寫下就不會變，
那個網址背後的 bytes 永遠是同一份。

`/api/v1/templates/{id}/master` **不可以**。它是經由 `template_pages` 解析的，
而那張表可以被指向另一張影像——換掉模板的頁，同一個網址就給出不同的考卷。
它一度也宣告了一年的 `immutable`，於是路徑上每一層快取都相信了：
一台在模板重建前抓過母卷的裝置，之後一直從自己的儲存交出舊考卷，
再也沒有問過伺服器。App 顯示一份考卷，資料庫裡是另一份，兩邊的日誌都看不出來。

現在是 `private, no-cache`，ETag 保留，所以之後要做條件請求還是便宜的。

### `teacher_value` + `cell_image_id`

老師每修正一次判定，就產生一筆「這格手寫圖 → 正確答案」的標註，
而且是在正常批改中順手完成的。
`GET /api/v1/grading-sessions/exports/corrections` 匯出成訓練資料。

辨識模型目前是用 6 格真實手寫樣本調的。上線一學期，這裡會有幾千格。
**準確度的長期解在這裡，不在換模型。**
