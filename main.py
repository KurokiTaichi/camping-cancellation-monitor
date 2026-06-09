import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
from google.cloud import secretmanager
from datetime import datetime
from flask import Flask, jsonify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ID = "camping-cancellation-monitor"
RESERVE_URL = "https://reser.yagai-kikaku.com/cc_reserve/sv_open?site=1"
LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def get_secret(secret_id: str) -> str:
    """Secret Manager から秘密情報を取得"""
    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(f"Failed to get secret '{secret_id}': {e}")
        raise


class ReservationChecker:
    """セッションを保持して予約ページを監視"""
    session = None

    @classmethod
    def init_session(cls):
        """セッションを初期化"""
        cls.session = requests.Session()
        logger.info("新しいセッションを作成しました")

    @classmethod
    def login(cls, email: str, passwd: str) -> bool:
        """ログイン処理（セッションを保持）"""
        try:
            logger.info("ログイン中...")
            response = cls.session.post(
                RESERVE_URL,
                data={"email": email, "passwd": passwd},
                timeout=10
            )

            if response.status_code == 200:
                logger.info("ログイン成功")
                return True
            else:
                logger.error(f"ログイン失敗: Status {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"ログインエラー: {e}")
            return False

    @classmethod
    def get_page(cls) -> str:
        """ページを取得（セッションを使用）"""
        try:
            logger.info("ページ取得中...")
            response = cls.session.get(RESERVE_URL, timeout=10)

            if response.status_code == 200:
                logger.info("ページ取得成功")
                return response.text
            else:
                logger.error(f"ページ取得失敗: Status {response.status_code}")
                # ログイン状態が切れた可能性
                return None

        except requests.RequestException as e:
            logger.error(f"ページ取得エラー: {e}")
            return None

    @classmethod
    def check_multiple_dates(cls, email: str, passwd: str) -> list:
        """
        複数日付のプレミアムカントリーキャビン枠をチェック
        7月17日、7月18-31日、8月1-30日

        Returns:
            キャンセル可能な日付のリスト [('7月', 17), ('7月', 18), ...]
        """
        try:
            # ページ取得
            page_html = cls.get_page()

            if page_html is None:
                logger.warning("ログイン状態が切れた可能性があります。再ログイン中...")
                if not cls.login(email, passwd):
                    return []
                page_html = cls.get_page()
                if page_html is None:
                    logger.error("再ログイン後もページ取得に失敗")
                    return []

            # HTML解析
            soup = BeautifulSoup(page_html, 'html.parser')

            # 監視対象日付（日付, 月, 背景色）
            target_dates = [
                (17, '7月', '#FBD964'),
                *[(d, '7月', '#FFA093') for d in range(18, 32)],  # 7/18-31
                *[(d, '8月', '#FFA093') for d in range(1, 31)],   # 8/1-30
            ]

            # 「プレミアムカントリーキャビン」の行を見つける
            rows = soup.find_all('tr')
            target_row = None

            for row in rows:
                tds = row.find_all('td')
                if tds:
                    for td in tds:
                        if 'プレミアムカントリーキャビン' in td.get_text():
                            target_row = row
                            logger.info("プレミアムカントリーキャビンの行を見つけました")
                            break
                    if target_row:
                        break

            if not target_row:
                logger.error("プレミアムカントリーキャビンの行が見つかりません")
                return []

            row_tds = target_row.find_all('td')

            # 各日付をチェック
            available_dates = []
            all_tds = soup.find_all('td')

            for day, month, bgcolor in target_dates:
                # 該当する日付のセルを見つける
                column_index = None

                for idx, td in enumerate(all_tds):
                    if td.get('bgcolor') == bgcolor:
                        text = td.get_text(strip=True)
                        if text == str(day):
                            column_index = idx
                            break

                if column_index is None:
                    logger.warning(f"{month}{day}日のセルが見つかりません")
                    continue

                # 該当セルを取得
                if column_index >= len(row_tds):
                    logger.warning(f"{month}{day}日: 列インデックスが範囲外")
                    continue

                cell = row_tds[column_index]
                cell_text = cell.get_text(strip=True)
                has_x = '×' in cell_text

                if not has_x:
                    available_dates.append((month, day))
                    logger.info(f"✅ {month}{day}日: キャンセル可能（×なし）")
                else:
                    logger.info(f"❌ {month}{day}日: 予約済み（×あり）")

            return available_dates

        except Exception as e:
            logger.error(f"チェック処理エラー: {e}")
            return []


def send_line_notification(line_token: str, line_user_id: str, message: str) -> bool:
    """
    LINE で通知を送信

    Args:
        line_token: LINE Channel Access Token
        line_user_id: LINE User ID
        message: 送信メッセージ

    Returns:
        True: 送信成功
        False: 送信失敗
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }

        payload = {
            "to": line_user_id,
            "messages": [{"type": "text", "text": message}]
        }

        response = requests.post(
            LINE_API_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            logger.info("LINE 通知送信成功")
            return True
        else:
            logger.error(f"LINE 通知送信失敗: Status {response.status_code}, Response: {response.text}")
            return False

    except requests.RequestException as e:
        logger.error(f"LINE 通知送信エラー: {e}")
        return False


def main():
    """メイン処理"""
    try:
        logger.info("=" * 60)
        logger.info("キャンセル検知システム起動")
        logger.info(f"実行時刻: {datetime.now().isoformat()}")
        logger.info("=" * 60)

        # Secret Manager から認証情報を取得
        logger.info("認証情報を取得中...")
        cc_email = get_secret("cc-email")
        cc_passwd = get_secret("cc-passwd")
        line_token = get_secret("line-channel-access-token")
        line_user_id = get_secret("line-user-id")

        # セッションを初期化してログイン
        ReservationChecker.init_session()

        if not ReservationChecker.login(cc_email, cc_passwd):
            logger.error("初回ログインに失敗しました")
            return 1

        # 複数日付をチェック
        available_dates = ReservationChecker.check_multiple_dates(cc_email, cc_passwd)

        # キャンセル可能な日付があれば通知
        if available_dates:
            # 日付をフォーマット
            date_str = "、".join([f"{month}{day}日" for month, day in available_dates])

            message = f"""🎉 キャンセル検知！

【予約内容】
📅 日付: {date_str}
🏕️ 施設: プレミアムカントリーキャビン
📍 場所: キャンプアンドキャビンズ山中湖

予約可能になりました！"""

            logger.info(f"LINE 通知を送信中... ({len(available_dates)}件)")
            send_line_notification(line_token, line_user_id, message)
            logger.info("処理完了（キャンセル検知）")
        else:
            logger.info("処理完了（該当するキャンセルなし）")

        return 0

    except Exception as e:
        logger.error(f"致命的エラー: {e}")

        # エラー通知を送信（Secret Manager へのアクセスに成功した場合のみ）
        try:
            line_token = get_secret("line-channel-access-token")
            line_user_id = get_secret("line-user-id")
            error_message = f"⚠️ キャンセル検知システムエラー\n\n{str(e)}"
            send_line_notification(line_token, line_user_id, error_message)
        except:
            pass

        return 1


app = Flask(__name__)


@app.route("/", methods=["POST"])
def run_check():
    """Cloud Scheduler から HTTP POST で呼ばれるエンドポイント"""
    try:
        exit_code = main()
        if exit_code == 0:
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "error"}), 500
    except Exception as e:
        logger.error(f"Handler error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
