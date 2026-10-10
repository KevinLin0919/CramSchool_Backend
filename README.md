# 浮島 後端

補習班考卷批改系統「浮島」的伺服器。老師用 iPhone／iPad 上的
[浮島 App](https://github.com/KevinLin0919/CramSchool_IOS) 掃描考卷，批改在手機上完成；
這個伺服器負責**保存與同步**：

- **考卷模板**：每份考卷的格子位置、標準答案、母卷圖片。全校共用同一份。
- **批改結果**：每位學生每一題的判定，以及老師的修正。
- **帳號**：老師登入、每台裝置可以個別停用。

App 同步過一次模板後，沒有網路也能批改；連上網時再把結果傳回來。

## 網頁版（測試中）

除了 App，也有網頁可以用：

- 看班級的批改報告。
- 上傳標準答案卷（圖片或 PDF）建立模板，或修改已儲存的模板。

## 誰能做什麼

| 角色 | 能做的事 |
|---|---|
| 老師 | 用模板批改，看自己的批改紀錄 |
| 模板管理者 | 再加上新增、修改、刪除模板 |
| 管理員 | 再加上全校層級的操作，例如匯出資料、刪除學生 |

模板只有模板管理者能改，因為改一份正解會影響所有老師的成績。

## 給開發者

- 開工先讀 [`AGENTS.md`](AGENTS.md)，再讀 [`docs/progress.md`](docs/progress.md)。
- 設計細節、登入、部署與備份：[`docs/design.md`](docs/design.md)、[`docs/ops/`](docs/ops/)。
- 用語：[`CONTEXT.md`](CONTEXT.md)。

```bash
uv sync --extra dev
.venv/bin/python -m pytest
.venv/bin/uvicorn app.main:app --reload --port 8085   # API 文件在 /docs
```
