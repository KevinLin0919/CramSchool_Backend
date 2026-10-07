# 部署

## 後端：QAT（可以直接做）

在伺服器上：

```bash
cd ~/CramSchool_Backend_qat
git fetch origin && git checkout --detach origin/develop
docker compose -p cramqat -f docker-compose.qat.yml --env-file .env.qat up -d --build
```

Migration 會在容器啟動時自動套用，跑不過容器就不會起來。部署後打一次 `/api/v1/auth/me`（未登入應回 401）確認服務有回應。

## 後端：正式版（每次都要使用者同意）

```bash
cd ~/CramSchool_Backend
git pull origin main
docker compose up -d --build
```

部署前確認 `main` 上的內容是要上的那些，並確認 iOS 正式版會用到的 API 都已經在正式後端上（App 不能比後端先上新 API）。

## iOS

不需要手動打包。推到 `develop` → 浮島 QAT 的 TestFlight；推到 `main` → 浮島的 TestFlight。流程與檢查見 `docs/agents/workflow.md` 的「出貨」。

## 帳號與角色

```bash
docker exec cram_api cramctl teachers list                      # 唯讀
docker exec cram_api cramctl teachers set-role <id> <teacher|template_manager|admin>
docker exec cram_api cramctl teachers invite <id> --days 7       # 邀請碼只顯示一次
docker exec cram_api cramctl tokens list                        # 唯讀
docker exec cram_api cramctl tokens revoke <token id>
```

除了 `list` 以外都是寫入，正式版要先問使用者。角色改了之後，App 在下次同步（重開或下拉重新整理）時更新畫面。

## 備份

`deploy/backup.sh`。自動排程目前沒有成功執行過（狀態見 `docs/progress.md`），只有手動執行的備份是完整的。
