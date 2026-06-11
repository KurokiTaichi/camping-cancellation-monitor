# 🚀 クイックスタート

## 📦 ファイル構成

```
camping-cancellation-monitor/
├── main.py           # メインスクリプト
├── requirements.txt  # 依存パッケージ
├── Dockerfile        # Cloud Run 用
├── DEPLOY.md         # 詳細なデプロイ手順
└── QUICKSTART.md     # このファイル
```

---

## ⚡ 3ステップで開始

### ステップ 1: gcloud CLI をインストール

```bash
# macOS
brew install google-cloud-sdk

# その後、認証
gcloud auth login
gcloud auth application-default login
```

### ステップ 2: Secret Manager に認証情報を登録（コピペで実行）

```bash
gcloud config set project camping-cancellation-monitor

# API を有効化
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com

# 秘密情報を登録（値は自分のものに置き換えてください）
echo -n "YOUR_EMAIL_ADDRESS" | gcloud secrets create cc-email --data-file=-
echo -n "YOUR_PASSWORD" | gcloud secrets create cc-passwd --data-file=-
echo -n "YOUR_LINE_CHANNEL_ACCESS_TOKEN" | gcloud secrets create line-channel-access-token --data-file=-
echo -n "YOUR_LINE_USER_ID" | gcloud secrets create line-user-id --data-file=-
```

### ステップ 3: Cloud Run にデプロイ

```bash
cd ~/camping-cancellation-monitor

# デプロイ
gcloud run deploy camping-cancellation-monitor \
  --source . \
  --region asia-northeast1 \
  --platform managed \
  --memory 256Mi \
  --timeout 300 \
  --no-allow-unauthenticated
```

**出力されるサービスURL をコピー** （例: `https://camping-cancellation-monitor-xyz.run.app`）

### ステップ 4: Secret Manager アクセス権を付与

```bash
# サービスアカウント名を取得
SA_EMAIL=$(gcloud iam service-accounts list \
  --filter='displayName:Cloud Run' \
  --format='value(email)' | head -1)

# 権限を付与
for SECRET in cc-email cc-passwd line-channel-access-token line-user-id; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member=serviceAccount:$SA_EMAIL \
    --role=roles/secretmanager.secretAccessor
done
```

### ステップ 5: Cloud Scheduler で定期実行を設定

```bash
# SERVICE_URL を置き換え （例: https://camping-cancellation-monitor-xyz.run.app）
SERVICE_URL="https://camping-cancellation-monitor-xyz.run.app"

gcloud scheduler jobs create http camping-cancellation-monitor \
  --schedule="*/15 * * * *" \
  --uri="$SERVICE_URL" \
  --http-method=POST \
  --oidc-service-account-email=$SA_EMAIL \
  --oidc-token-audience="$SERVICE_URL" \
  --location=asia-northeast1 \
  --message-body='{}'
```

---

## ✅ 動作確認

### ログを確認

```bash
gcloud run logs read camping-cancellation-monitor --region=asia-northeast1 --limit 20
```

### 手動テスト

```bash
gcloud scheduler jobs describe camping-cancellation-monitor --location=asia-northeast1
# 上記で "schedule: */1 * * * *" が表示されたら成功

# 1回実行してテスト
gcloud scheduler jobs run camping-cancellation-monitor --location=asia-northeast1
```

---

## 📝 トラブルシューティング

| 問題 | 解決策 |
|-----|-------|
| `gcloud: command not found` | Google Cloud SDK をインストール |
| `Permission denied` | `gcloud auth login` で認証し直す |
| `Resource already exists` | 既に存在する場合、無視して OK |
| LINE 通知が来ない | ログを確認: `gcloud run logs read camping-cancellation-monitor --limit 50` |

---

## 📚 詳細情報

詳しくは [DEPLOY.md](DEPLOY.md) を参照してください。

---

## 🛑 停止・削除

```bash
# Cloud Scheduler ジョブを削除
gcloud scheduler jobs delete camping-cancellation-monitor --location=asia-northeast1

# Cloud Run サービスを削除
gcloud run services delete camping-cancellation-monitor --region=asia-northeast1

# Secret Manager から削除
for SECRET in cc-email cc-passwd line-channel-access-token line-user-id; do
  gcloud secrets delete $SECRET
done
```
