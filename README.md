# 🏕️ キャンセル検知システム

キャンプアンドキャビンズ山中湖の予約キャンセルを自動検知し、LINE で通知するシステムです。

## ✨ 特徴

- **自動監視**: 1分間隔で予約ページをチェック
- **即座通知**: キャンセルが出たら LINE で即座に通知
- **セキュア**: Secret Manager で認証情報を安全に管理
- **スケーラブル**: Cloud Run でサーバーレス実行
- **低コスト**: 月額 $2-3 程度の運用費用

## 🎯 監視対象

- **予約日**: 2026年7月17日（金）
- **施設**: プレミアムカントリーキャビン
- **場所**: キャンプアンドキャビンズ山中湖

## 🚀 クイックスタート

### 1. 環境構築

```bash
# リポジトリをクローン
git clone https://github.com/KurokiTaichi/camping-cancellation-monitor.git
cd camping-cancellation-monitor

# Google Cloud SDK をインストール
brew install google-cloud-sdk
gcloud auth login
gcloud auth application-default login
```

### 2. GCP セットアップ

```bash
# プロジェクト設定
gcloud config set project YOUR_PROJECT_ID

# API 有効化
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com
```

### 3. 秘密情報を登録

```bash
# キャンプアンドキャビンズのメールアドレス
echo -n "YOUR_EMAIL" | gcloud secrets create cc-email --data-file=-

# キャンプアンドキャビンズのパスワード
echo -n "YOUR_PASSWORD" | gcloud secrets create cc-passwd --data-file=-

# LINE Channel Access Token
echo -n "YOUR_LINE_TOKEN" | gcloud secrets create line-channel-access-token --data-file=-

# LINE User ID
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

**出力される Service URL をメモ**（例: `https://camping-cancellation-monitor-xyz.run.app`）

### 5. Secret Manager のアクセス権を設定

```bash
SA_EMAIL=$(gcloud run services describe camping-cancellation-monitor \
  --region asia-northeast1 \
  --format='value(spec.template.spec.serviceAccountName)')

for SECRET in cc-email cc-passwd line-channel-access-token line-user-id; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member=serviceAccount:$SA_EMAIL \
    --role=roles/secretmanager.secretAccessor
done
```

### 6. Cloud Scheduler で定期実行を設定

```bash
SERVICE_URL="https://camping-cancellation-monitor-xyz.run.app"

gcloud scheduler jobs create http camping-cancellation-monitor \
  --schedule="*/1 * * * *" \
  --uri="$SERVICE_URL" \
  --http-method=POST \
  --oidc-service-account-email=$SA_EMAIL \
  --oidc-token-audience="$SERVICE_URL" \
  --location=asia-northeast1 \
  --message-body='{}'
```

## 📊 システムアーキテクチャ

```
┌────────────────────────────────────────┐
│ Cloud Scheduler (毎分)                  │
│ cron: */1 * * * *                      │
└──────────────┬─────────────────────────┘
               │
               ▼
┌────────────────────────────────────────┐
│ Cloud Run (Flask HTTP Server)           │
│                                        │
│ ├─ Secret Manager から認証情報取得    │
│ ├─ 予約ページにログイン                │
│ ├─ ページ取得（最新情報）              │
│ ├─ HTML 解析                           │
│ │  ├─ 7月17日セル検出                  │
│ │  └─ プレミアムカントリーキャビン行  │
│ ├─ 「×」の有無判定                    │
│ └─ キャンセル検知 → LINE 通知          │
└────────────────────────────────────────┘
```

## 📁 ファイル構成

```
camping-cancellation-monitor/
├── main.py              # メインアプリケーション
├── requirements.txt    # Python 依存パッケージ
├── Dockerfile          # Cloud Run コンテナイメージ
├── README.md           # このファイル
├── QUICKSTART.md       # クイックスタート手順
├── DEPLOY.md           # 詳細なデプロイ手順
└── .gitignore          # Git 除外ファイル
```

## 🔐 セキュリティ

- **認証情報**: すべて Google Cloud Secret Manager で管理
- **ソースコード**: 秘密情報をハードコードしていない
- **通信**: HTTPS のみ使用
- **アクセス制御**: IAM で最小権限の原則に従う

## 💰 コスト見立て

| サービス | 月額 |
|--------|------|
| Cloud Run | ~$2-3 |
| Secret Manager | $0.24 |
| Cloud Scheduler | $0.10 |
| **合計** | **約 $2-3/月** |

※ Cloud Run は月間90,000秒無料

## 📝 ログ確認

```bash
# Cloud Logging でログを確認
gcloud logging read "resource.type=cloud_run_revision" \
  --limit 50 \
  --format='table(timestamp,jsonPayload.message)'
```

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

## 🔧 トラブルシューティング

### LINE 通知が来ない

1. Cloud Logging でエラーを確認
   ```bash
   gcloud logging read "resource.type=cloud_run_revision" --limit 50
   ```

2. Secret Manager の値が正しいか確認
   ```bash
   gcloud secrets versions access latest --secret=line-channel-access-token
   ```

### Cloud Run がエラーで起動しない

```bash
# Cloud Build のログを確認
gcloud builds log [BUILD_ID]
```

### ページ取得に失敗

- ログイン情報（email, password）が正しいか確認
- キャンプアンドキャビンズのログインページが正常に動作しているか確認

## 📞 サポート

問題が発生した場合は、GitHub Issues で報告してください。

## 📄 ライセンス

MIT

---

🏕️ Happy Camping! 予約キャンセルを逃さずゲット！
