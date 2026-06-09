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
    def check_july_17(cls, email: str, passwd: str) -> bool:
        """
        7月17日のプレミアムカントリーキャビン枠をチェック

        Returns:
            True: キャンセル可能（「×」がない）
            False: 予約済み（「×」がある）
        """
        try:
            # ページ取得
            page_html = cls.get_page()

            if page_html is None:
                logger.warning("ログイン状態が切れた可能性があります。再ログイン中...")
                if not cls.login(email, passwd):
                    return False
                page_html = cls.get_page()
                if page_html is None:
                    logger.error("再ログイン後もページ取得に失敗")
                    return False

            # HTML解析
            soup = BeautifulSoup(page_html, 'html.parser')

            # 1. 7月17日の列位置を見つける（bgcolor="#FBD964" かつテキスト="17"）
            july_17_column_index = None
            all_tds = soup.find_all('td')

            for idx, td in enumerate(all_tds):
                if td.get('bgcolor') == '#FBD964':
                    text = td.get_text(strip=True)
                    if text == '17':
                        july_17_column_index = idx
                        logger.info(f"7月17日を見つけました（列インデックス: {july_17_column_index}）")
                        break

            if july_17_column_index is None:
                logger.error("7月17日が見つかりません")
                return False

            # 2. 「プレミアムカントリーキャビン」の行を見つける
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
                return False

            # 3. プレミアムカントリーキャビン行から7月17日に対応するセルを取得
            row_tds = target_row.find_all('td')

            if july_17_column_index >= len(row_tds):
                logger.error("列インデックスが範囲外です")
                return False

            july_17_cell = row_tds[july_17_column_index]
            logger.info(f"プレミアムカントリーキャビン 7月17日のセルを特定しました")

            # 4. 「×」の有無を判定
            cell_text = july_17_cell.get_text(strip=True)
            has_x = '×' in cell_text

            if has_x:
                logger.info("7月17日プレミアムカントリーキャビン: 予約済み（×あり）")
            else:
                logger.info("7月17日プレミアムカントリーキャビン: キャンセル可能（×なし）")

            return not has_x

        except Exception as e:
            logger.error(f"チェック処理エラー: {e}")
            return False


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

        # 予約ページをチェック
        is_available = ReservationChecker.check_july_17(cc_email, cc_passwd)

        # キャンセル可能なら通知
        if is_available:
            message = """🎉 キャンセル検知！

【予約内容】
📅 日付: 2026年7月17日（金）
🏕️ 施設: プレミアムカントリーキャビン
📍 場所: キャンプアンドキャビンズ山中湖

予約可能になりました！"""

            logger.info("LINE 通知を送信中...")
            send_line_notification(line_token, line_user_id, message)
            logger.info("処理完了（キャンセル検知）")
        else:
            logger.info("処理完了（予約済み）")

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
