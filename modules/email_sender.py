#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 安全郵件發送核心模組 (Email Transmission Engine)
============================================================
支援 SSL/TLS 加密傳輸，自動讀取本機 .env 金鑰配置，提供純文字與響應式 HTML 雙模發信。
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import Optional, Dict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env_credentials() -> Dict[str, str]:
    """解析本機 .env 檔案獲取郵件配置，不硬編碼任何敏感金鑰"""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    creds = {
        "SMTP_SERVER": "smtp.gmail.com",
        "SMTP_PORT": "465",
        "SMTP_USER": "",
        "SMTP_APP_PASSWORD": "",
        "REPORT_RECEIVER": ""
    }
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k in creds:
                        creds[k] = v

    # 也支援系統環境變數覆蓋
    for k in creds.keys():
        env_val = os.getenv(k)
        if env_val:
            creds[k] = env_val

    # 去除密碼中可能包含的空格（Google 應用程式密碼常見每 4 碼一格）
    if creds["SMTP_APP_PASSWORD"]:
        creds["SMTP_APP_PASSWORD"] = creds["SMTP_APP_PASSWORD"].replace(" ", "")

    return creds


def send_email(subject: str, html_content: str, text_content: Optional[str] = None, to_email: Optional[str] = None) -> bool:
    """
    透過 Gmail SMTP 安全發送郵件
    :param subject: 郵件主旨
    :param html_content: HTML 格式郵件內容
    :param text_content: 純文字備用內容（選填）
    :param to_email: 收件者信箱（若無則讀取 REPORT_RECEIVER）
    :return: bool 是否發送成功
    """
    creds = load_env_credentials()
    smtp_user = creds.get("SMTP_USER", "")
    smtp_pass = creds.get("SMTP_APP_PASSWORD", "")
    receiver = to_email or creds.get("REPORT_RECEIVER", "") or smtp_user
    server_host = creds.get("SMTP_SERVER", "smtp.gmail.com")
    server_port = int(creds.get("SMTP_PORT", 465))

    if not smtp_user or not smtp_pass:
        print("❌ [Email Error] 未能於 .env 偵測到有效的 SMTP_USER 或 SMTP_APP_PASSWORD！")
        return False

    if not receiver:
        receiver = smtp_user

    # 構建 MIME 複合訊息
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = f"Personal Quant Firm <{smtp_user}>"
    msg["To"] = receiver

    if text_content:
        part_text = MIMEText(text_content, "plain", "utf-8")
        msg.attach(part_text)

    part_html = MIMEText(html_content, "html", "utf-8")
    msg.attach(part_html)

    try:
        if server_port == 465:
            with smtplib.SMTP_SSL(server_host, server_port, timeout=15) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [receiver], msg.as_string())
        else:
            with smtplib.SMTP(server_host, server_port, timeout=15) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [receiver], msg.as_string())

        print(f"✅ [Email Success] 成功寄送郵件至: {receiver} | 主旨: {subject}")
        return True
    except smtplib.SMTPAuthenticationError as auth_err:
        print(f"❌ [Email Auth Error] Gmail 身份驗證失敗: 請確認 16 位應用程式密碼是否正確，且已開啟 Google 兩步驟驗證。詳情: {auth_err}")
        return False
    except Exception as e:
        print(f"❌ [Email Transmission Error] 發送郵件時發生未預期例外: {e}")
        return False


if __name__ == "__main__":
    print("正在測試本地郵件發送連線...")
    test_subj = "Personal Quant Firm 系統連線測試"
    test_html = """
    <div style='font-family: Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;'>
        <h2 style='color: #0f172a;'>🚀 Personal Quant Firm 通訊測試</h2>
        <p>這是一封來自本地量化戰情室的自動化測試郵件。</p>
        <p>若您看見此信件，代表 <strong>Gmail SMTP 安全傳輸管道配置成功</strong>！</p>
    </div>
    """
    success = send_email(test_subj, test_html, "Personal Quant Firm 系統連線測試成功")
    print(f"測試結果: {'通過 (PASSED)' if success else '失敗 (FAILED)'}")
