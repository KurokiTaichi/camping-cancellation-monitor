# キャンセル検知システム デプロイ手順

## 📋 前提条件

- `gcloud` CLI がインストールされている
- GCP プロジェクト: `camping-cancellation-monitor`
- 認証済み（`gcloud auth login`）

---

## 🚀 デプロイ手順

### 1. GCP プロジェクトを設定

```bash
gcloud config set project camping-cancellation-monitor
```

### 2. 必要な GCP API を有効化

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com
```

### 3. Secret Manager に認証情報を保存

以下のコマンドで、各秘密情報を登録します。

#### 3-1. キャンプアンドキャビンズのメールアドレス

```bash
echo -n "YOUR_EMAIL_ADDRESS" | gcloud secrets create cc-email --data-file=-
```

#### 3-2. キャンプアンドキャビンズのパスワード

```bash
echo -n "YOUR_PASSWORD" | gcloud secrets create cc-passwd --data-file=-
```

#### 3-3. LINE Channel Access Token

```bash
echo -n "YOUR_LINE_CHANNEL_ACCESS_TOKEN" | gcloud secrets create line-channel-access-token --data-file=-
```

#### 3-4. LINE User ID

```bash
echo -n "YOUR_LINE_USER_ID" | gcloud secrets create line-user-id --data-file=-
```

### 4. Cloud Run にデプロイ

```bash
gcloud run deploy camping-cancellation-monitor \
  --source . \
  --region asia-northeast1 \
  --platform managed \
  --memory 256Mi \
  --timeout 300 \
  --no-allow-unauthenticated
```

デプロイ後、**Service URL** が表示されます。コピーしておいてください（例: `https://camping-cancellation-monitor-xyz.run.app`）

### 5. Cloud Run サービスアカウントに Secret Manager アクセス権を付与

Cloud Run サービスが Secret Manager にアクセスできるようにします。

```bash
# サービスアカウント名を取得
SA_EMAIL=$(gcloud iam service-accounts list \
  --filter='displayName:Cloud Run' \
  --format='value(email)' | head -1)

# Secret Manager アクセス権を付与
gcloud secrets add-iam-policy-binding cc-email \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding cc-passwd \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding line-channel-access-token \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding line-user-id \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/secretmanager.secretAccessor
```

### 6. Cloud Scheduler で定期実行を設定

1分間隔で Cloud Run を実行するスケジューラーを作成します。

```bash
gcloud scheduler jobs create http camping-cancellation-monitor \
  --schedule="*/1 * * * *" \
  --uri="https://camping-cancellation-monitor-xyz.run.app" \
  --http-method=POST \
  --oidc-service-account-email=$SA_EMAIL \
  --oidc-token-audience="https://camping-cancellation-monitor-xyz.run.app" \
  --location=asia-northeast1 \
  --message-body='{}' || echo "Job already exists"
```

**注意**: `https://camping-cancellation-monitor-xyz.run.app` を、実際の Cloud Run Service URL に置き換えてください。

---

## ✅ 動作確認

### Cloud Run ログを確認

```bash
gcloud run logs read camping-cancellation-monitor \
  --region=asia-northeast1 \
  --limit 50
```

### 手動テスト（Cloud Run を1回実行）

```bash
gcloud run jobs execute camping-cancellation-monitor \
  --region=asia-northeast1
```

または、Cloud Scheduler で「今すぐ実行」ボタンをクリック。

---

## 📊 ログ監視

Cloud Logging で実行ログを監視できます：

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=camping-cancellation-monitor" \
  --limit 20 \
  --format=json
```

---

## 🛑 停止・削除

### Cloud Scheduler ジョブを停止

```bash
gcloud scheduler jobs pause camping-cancellation-monitor --location=asia-northeast1
```

### Cloud Run サービスを削除

```bash
gcloud run services delete camping-cancellation-monitor --region=asia-northeast1
```

### Secret Manager から秘密情報を削除

```bash
gcloud secrets delete cc-email
gcloud secrets delete cc-passwd
gcloud secrets delete line-channel-access-token
gcloud secrets delete line-user-id
```

---

## 💡 トラブルシューティング

### 「Permission denied」エラーが出る

→ Step 5 で Secret Manager アクセス権が正しく付与されているか確認してください。

### Cloud Run でタイムアウトする

→ `main.py` の timeout を増やしてください（デフォルト: 300秒）

### LINE 通知が来ない

→ Cloud Logging で詳細ログを確認。`LINE_CHANNEL_ACCESS_TOKEN` や `LINE_USER_ID` が正しいか確認。
