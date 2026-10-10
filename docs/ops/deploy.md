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

`deploy/backup.sh` 從開發機用 cron 每天凌晨把資料庫和影像拉回來。cron 碰不到 ssh-agent，所以用一把**沒有密碼、
只給備份用**的金鑰；主機只讓這把金鑰執行 `deploy/backup-gate.sh` 列出的兩個匯出指令，其他一律拒絕。

開發機（每台要跑備份的機器各做一次）：

```bash
ssh-keygen -t ed25519 -N "" -C cramschool-backup -f ~/.ssh/cram_backup
mkdir -p ~/.config/cramschool
echo 'BACKUP_HOST=<使用者>@<主機>' > ~/.config/cramschool/backup.env   # 不進 git
```

主機（要使用者同意）：

```bash
mkdir -p ~/bin && cp CramSchool_Backend/deploy/backup-gate.sh ~/bin/cram-backup-gate
# 加到 ~/.ssh/authorized_keys，一行：
restrict,from="100.64.0.0/10",command="bin/cram-backup-gate" <cram_backup.pub 的內容>
```

`from` 限定只能從 Tailscale 內網連進來。改了 `backup.sh` 送出的指令，就要同步改 `backup-gate.sh` 並重新複製到主機。
裝好後手動跑一次 `deploy/backup.sh`，再照 `docs/design.md` 的方式做一次還原測試。
