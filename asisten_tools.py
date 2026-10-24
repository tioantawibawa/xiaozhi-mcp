"""
Tool MCP gabungan untuk Xiaozhi — Web Search + Google Calendar + Gmail
(versi optimal: caching koneksi, config via environment variable)

Jalankan lewat mcp_pipe.py:
    python mcp_pipe.py asisten_tools.py

File pendukung yang harus ada di folder yang sama:
    - credentials.json, token.json  (hasil generate_token.py)

Konfigurasi lewat environment variable (opsional):
    TAVILY_API_KEY   -> kalau diisi, search pakai Tavily (lebih stabil)
                         kalau kosong, otomatis fallback ke DuckDuckGo (gratis)
"""

import datetime
import logging
import os
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("asisten_tools")

mcp = FastMCP("AsistenXiaozhi")

TIMEZONE = ZoneInfo("Asia/Jakarta")

# ---- Isi API key Tavily kamu di sini ----
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# ---------------------------------------------------------
# Cache koneksi Google (dibuat sekali, dipakai ulang)
# ---------------------------------------------------------
_creds = None
_calendar_service = None
_gmail_service = None


def _ensure_credentials():
    """Ambil credentials dari cache; refresh hanya kalau sudah expired."""
    global _creds
    if _creds is None:
        _creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if _creds.expired and _creds.refresh_token:
        logger.info("Token Google expired, melakukan refresh...")
        _creds.refresh(Request())
        with open("token.json", "w") as f:
            f.write(_creds.to_json())

    return _creds


def _calendar():
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = build("calendar", "v3", credentials=_ensure_credentials())
    return _calendar_service


def _gmail():
    global _gmail_service
    if _gmail_service is None:
        _gmail_service = build("gmail", "v1", credentials=_ensure_credentials())
    return _gmail_service


# =========================================================
# WEB SEARCH
# =========================================================
@mcp.tool()
def search_internet(query: str, max_results: int = 5) -> dict:
    """Cari informasi terkini di internet. Gunakan setiap kali pengguna
    bertanya soal berita, harga, cuaca, atau hal lain yang butuh data
    terbaru dari internet.
    """
    logger.info(f"Mencari: {query}")
    if TAVILY_API_KEY and "isi_api_key" not in TAVILY_API_KEY:
        return _search_tavily(query, max_results)
    return _search_duckduckgo(query, max_results)


def _search_duckduckgo(query: str, max_results: int) -> dict:
    try:
        from ddgs import DDGS

        with DDGS(timeout=8) as ddgs:
            results = list(ddgs.text(query, max_results=max_results, backend="html"))
        if not results:
            return {"success": False, "message": "Tidak ada hasil ditemukan."}
        return {
            "success": True,
            "hasil": [
                {"judul": r.get("title", ""), "ringkasan": r.get("body", ""), "sumber": r.get("href", "")}
                for r in results
            ],
        }
    except Exception as e:
        logger.exception("Gagal mencari via DuckDuckGo")
        return {"success": False, "message": f"Error: {e}"}


def _search_tavily(query: str, max_results: int) -> dict:
    try:
        import requests

        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results, "search_depth": "basic"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "success": True,
            "hasil": [
                {"judul": r.get("title", ""), "ringkasan": r.get("content", ""), "sumber": r.get("url", "")}
                for r in data.get("results", [])
            ],
        }
    except Exception as e:
        logger.exception("Gagal mencari via Tavily, fallback ke DuckDuckGo")
        return _search_duckduckgo(query, max_results)


# =========================================================
# GOOGLE CALENDAR
# =========================================================
@mcp.tool()
def lihat_jadwal(hari_kedepan: int = 7, max_hasil: int = 10) -> dict:
    """Lihat jadwal/agenda dari Google Calendar untuk beberapa hari ke depan.

    Args:
        hari_kedepan: berapa hari ke depan yang mau dilihat (default 7)
        max_hasil: jumlah maksimal event yang ditampilkan
    """
    try:
        now = datetime.datetime.now(TIMEZONE)
        end = now + datetime.timedelta(days=hari_kedepan)

        events_result = (
            _calendar()
            .events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                maxResults=max_hasil,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            return {"success": True, "jadwal": [], "message": "Tidak ada agenda di rentang waktu ini."}

        hasil = [
            {
                "judul": e.get("summary", "(tanpa judul)"),
                "waktu_mulai": e["start"].get("dateTime", e["start"].get("date")),
                "lokasi": e.get("location", ""),
            }
            for e in events
        ]
        return {"success": True, "jadwal": hasil}

    except Exception as e:
        logger.exception("Gagal ambil jadwal")
        return {"success": False, "message": f"Error: {e}"}


@mcp.tool()
def buat_jadwal(
    judul: str,
    tanggal_waktu_mulai: str,
    tanggal_waktu_selesai: str,
    deskripsi: str = "",
    lokasi: str = "",
) -> dict:
    """Buat event/jadwal baru di Google Calendar.

    Args:
        judul: judul acara
        tanggal_waktu_mulai: format ISO, contoh '2026-08-01T10:00:00'
        tanggal_waktu_selesai: format ISO, contoh '2026-08-01T11:00:00'
        deskripsi: catatan tambahan (opsional)
        lokasi: lokasi acara (opsional)
    """
    try:
        event = {
            "summary": judul,
            "location": lokasi,
            "description": deskripsi,
            "start": {"dateTime": tanggal_waktu_mulai, "timeZone": "Asia/Jakarta"},
            "end": {"dateTime": tanggal_waktu_selesai, "timeZone": "Asia/Jakarta"},
        }
        created = _calendar().events().insert(calendarId="primary", body=event).execute()
        return {"success": True, "message": f"Jadwal '{judul}' berhasil dibuat.", "link": created.get("htmlLink")}

    except Exception as e:
        logger.exception("Gagal membuat jadwal")
        return {"success": False, "message": f"Error: {e}"}


# =========================================================
# GMAIL
# =========================================================
@mcp.tool()
def cek_email(query: str = "is:unread", max_hasil: int = 5) -> dict:
    """Cek email masuk. Default menampilkan email yang belum dibaca.

    Args:
        query: filter pencarian gaya Gmail, contoh 'is:unread', 'from:bos@company.com'
        max_hasil: jumlah maksimal email yang ditampilkan
    """
    try:
        results = _gmail().users().messages().list(userId="me", q=query, maxResults=max_hasil).execute()
        messages = results.get("messages", [])
        if not messages:
            return {"success": True, "email": [], "message": "Tidak ada email yang cocok."}

        hasil = []
        for m in messages:
            msg = (
                _gmail()
                .users()
                .messages()
                .get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            hasil.append(
                {
                    "dari": headers.get("From", ""),
                    "subjek": headers.get("Subject", "(tanpa subjek)"),
                    "ringkasan": msg.get("snippet", ""),
                }
            )
        return {"success": True, "email": hasil}

    except Exception as e:
        logger.exception("Gagal cek email")
        return {"success": False, "message": f"Error: {e}"}


@mcp.tool()
def kirim_email(ke: str, subjek: str, isi: str) -> dict:
    """Kirim email lewat Gmail.

    Args:
        ke: alamat email tujuan
        subjek: subjek email
        isi: isi/badan email
    """
    try:
        import base64
        from email.mime.text import MIMEText

        message = MIMEText(isi)
        message["to"] = ke
        message["subject"] = subjek
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        _gmail().users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"success": True, "message": f"Email ke {ke} berhasil dikirim."}

    except Exception as e:
        logger.exception("Gagal kirim email")
        return {"success": False, "message": f"Error: {e}"}


# =========================================================
# STARTUP CHECK
# =========================================================
def _startup_check():
    if not os.path.exists("token.json"):
        logger.warning("token.json TIDAK DITEMUKAN, jalankan generate_token.py dulu sebelum pakai fitur kalender/email.")
    if not TAVILY_API_KEY or "isi_api_key" in TAVILY_API_KEY:
        logger.info("TAVILY_API_KEY belum diisi, search_internet akan pakai DuckDuckGo (gratis, sedikit kurang stabil).")
    else:
        logger.info("TAVILY_API_KEY terdeteksi, search_internet akan pakai Tavily.")


if __name__ == "__main__":
    _startup_check()
    mcp.run(transport="stdio")
