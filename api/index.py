from http.server import BaseHTTPRequestHandler
import json
import os
import smtplib
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
DEFAULT_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def call_gemini_api(prompt: str) -> str:
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return ""


def send_smtp_otp(recipient_email: str, otp_code: str, sender_email: str = "", app_password: str = ""):
    sender = (sender_email or DEFAULT_SMTP_EMAIL).strip()
    pw = (app_password or DEFAULT_SMTP_PASSWORD).strip().replace(" ", "")
    if not sender or not pw:
        return False, "SMTP 발신 계정이 설정되지 않았습니다."

    domain = sender.split("@")[-1].lower()
    if "naver.com" in domain:
        smtp_host, smtp_port = "smtp.naver.com", 465
    elif "daum.net" in domain or "hanmail.net" in domain:
        smtp_host, smtp_port = "smtp.daum.net", 465
    else:
        smtp_host, smtp_port = "smtp.gmail.com", 465

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[울대모] 이메일 본인 확인 인증번호 [{otp_code}]"
    msg["From"] = sender
    msg["To"] = recipient_email

    html_body = f"""
    <div style="font-family: 'Pretendard', -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 28px 24px; border: 1px solid #E5E8EB; border-radius: 16px; background-color: #FFFFFF;">
        <div style="font-size: 20px; font-weight: 800; color: #287D62; margin-bottom: 8px;">🌱 울대모 이메일 인증 안내</div>
        <p style="font-size: 14px; color: #4E5968; line-height: 1.6; margin-bottom: 20px;">
            안녕하세요! 캠퍼스 안심 번개 매칭 플랫폼 <b>울대모</b> 회원가입을 위한 본인 확인 인증번호입니다.<br>
            아래 6자리 인증번호를 가입 화면에 입력해 주세요.
        </p>
        <div style="background-color: #EEF8F3; border: 1px solid #C5E6D6; border-radius: 12px; padding: 18px; text-align: center; margin-bottom: 20px;">
            <span style="font-size: 28px; font-weight: 800; letter-spacing: 6px; color: #1E634C;">{otp_code}</span>
        </div>
        <p style="font-size: 12px; color: #8B95A1;">본 메일은 발신 전용이며, 타인에게 인증번호를 공유하지 마세요.</p>
    </div>
    """
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=8) as server:
            server.login(sender, pw)
            server.sendmail(sender, [recipient_email], msg.as_string())
        return True, "실제 메일함으로 6자리 인증번호가 발송되었습니다!"
    except Exception as e:
        return False, f"SMTP 발송 오류: {str(e)[:80]}"


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        self._send_json(200, {"status": "ok", "service": "uldaemo-vercel-api"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw)
        except Exception:
            data = {}

        action = data.get("action", "")
        if action == "send_otp":
            recipient = str(data.get("email", "")).strip()
            otp_code = str(data.get("otp", "")).strip()
            sender_email = str(data.get("sender_email", "")).strip()
            app_password = str(data.get("app_password", "")).strip()
            ok, msg = send_smtp_otp(recipient, otp_code, sender_email, app_password)
            self._send_json(200, {"ok": ok, "message": msg})
            return

        if action == "ai_police":
            text = str(data.get("text", "")).strip()
            prompt = (
                "다음 메시지에 심한 욕설, 성적 발언, 또는 '카톡', '전번', '번호', '라인', '인스타' 등 "
                f"사적인 연락처를 요구하는 내용이 있다면 '경고', 평범한 대화라면 '통과'라고만 대답해. 메시지: {text}"
            )
            reply = call_gemini_api(prompt)
            blocked = "경고" in reply
            self._send_json(200, {"ok": True, "blocked": blocked, "reply": reply})
            return

        if action == "ai_icebreaker":
            location = str(data.get("location", "울산대학교"))
            category = str(data.get("category", "🍚 밥약"))
            style = str(data.get("meeting_style", "간단한 스몰토크 환영"))
            prompt = (
                f"대학생 두 명이 현재 '{location}'에서 '{category}' 목적으로 만나는 중이야. "
                f"둘의 만남 성향은 '{style}'이야. 어색함을 깰 수 있는 재미있는 대화 소재 1가지와, "
                "근처 맛집이나 놀거리 1가지를 3줄로 발랄하게 추천해줘."
            )
            reply = call_gemini_api(prompt)
            if not reply:
                reply = (
                    f"💡 <b>{location}</b> 근처에서 만나는군요! 오늘 수업이나 공강 루틴 이야기로 "
                    "가볍게 대화를 시작해 보세요. 모임 후 근처 학생식당이나 북카페 코스를 추천해요!"
                )
            self._send_json(200, {"ok": True, "reply": reply})
            return

        self._send_json(400, {"ok": False, "message": "Unknown action"})
