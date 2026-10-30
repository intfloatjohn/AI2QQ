"""Minimal QQ Zone (QQ空间) client: read posts (说说), publish a text post, comment, like.

Qzone has no official API. This uses the same web endpoints as the Qzone website, logged in
with the bot account's cookies, which NapCat hands out through the OneBot `get_cookies` action.
Everything here is best effort: Tencent can change these endpoints at any time, so callers must
treat every failure as normal and simply try again later.
"""
import json
import re
import time
import urllib.parse
import urllib.request

try:
    import requests
    _REQUESTS = True
except ImportError:  # pragma: no cover
    _REQUESTS = False

BASE_URL = "https://user.qzone.qq.com"
LIST_PATH = "/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
PUBLISH_PATH = "/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"
COMMENT_PATH = "/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
LIKE_PATH = "/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

LOGIN_ERROR_CODES = {-3000, -4001, -100, -10000}
NO_PERMISSION_CODES = {-10031, -4009, -10, -2}
_EMOJI_RE = re.compile(r'\[em\][^\[]*\[/em\]')


class QzoneError(Exception):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code

    @property
    def login_expired(self) -> bool:
        return self.code in LOGIN_ERROR_CODES

    @property
    def no_permission(self) -> bool:
        return self.code in NO_PERMISSION_CODES


def g_tk(key: str) -> int:
    """Qzone's CSRF token, derived from the p_skey (or skey) cookie."""
    h = 5381
    for ch in key or "":
        h += (h << 5) + ord(ch)
    return h & 0x7fffffff


def parse_cookie_string(cookie_str: str) -> dict:
    out = {}
    for part in (cookie_str or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def clean_text(text: str) -> str:
    return _EMOJI_RE.sub("", str(text or "")).strip()


def _extract_json(body: str) -> dict:
    """Responses come as JSON, JSONP (_preloadCallback({...})) or an HTML page that calls
    frameElement.callback({...}); this returns the JSON object in all three cases."""
    body = (body or "").strip()
    if body.startswith("{"):
        try:
            return json.loads(body)
        except ValueError:
            pass
    m = re.search(r'\(\s*(\{.*\})\s*\)\s*;?', body, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError:
            pass
    raise QzoneError(f"Unexpected Qzone response: {body[:120]}")


class QzoneClient:
    def __init__(self, cookie_provider, self_uin: int, base_url: str = BASE_URL, timeout: float = 10.0):
        """cookie_provider() returns the cookie string for the logged-in account (or "")."""
        self.cookie_provider = cookie_provider
        self.self_uin = int(self_uin)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cookies = {}
        self._cookies_at = 0.0

    # ---------------------------------------------------------------- cookies
    def refresh_cookies(self):
        cookies = parse_cookie_string(self.cookie_provider() or "")
        if not (cookies.get("p_skey") or cookies.get("skey")):
            raise QzoneError("No Qzone login cookies (p_skey/skey) from NapCat", -3000)
        self._cookies = cookies
        self._cookies_at = time.time()

    def _ensure_cookies(self):
        if not self._cookies or time.time() - self._cookies_at > 6 * 3600:
            self.refresh_cookies()

    @property
    def gtk(self) -> int:
        return g_tk(self._cookies.get("p_skey") or self._cookies.get("skey") or "")

    # ---------------------------------------------------------------- http
    def _request(self, method: str, path: str, params: dict = None, data: dict = None, retry: bool = True) -> dict:
        self._ensure_cookies()
        params = dict(params or {})
        params["g_tk"] = self.gtk
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": f"https://user.qzone.qq.com/{self.self_uin}",
            "Origin": "https://user.qzone.qq.com",
            "Cookie": "; ".join(f"{k}={v}" for k, v in self._cookies.items()),
        }
        try:
            if _REQUESTS:
                resp = requests.request(method, url, data=data, headers=headers, timeout=self.timeout)
                status, body = resp.status_code, resp.text
            else:  # pragma: no cover
                payload = urllib.parse.urlencode(data).encode() if data else None
                if payload:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                req = urllib.request.Request(url, data=payload, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    status, body = r.status, r.read().decode("utf-8", errors="ignore")
        except Exception as e:
            raise QzoneError(f"Qzone request failed: {e}")
        if status in (401, 403) and retry:
            self.refresh_cookies()
            return self._request(method, path, params, data, retry=False)
        if status != 200:
            raise QzoneError(f"Qzone HTTP {status}")
        result = _extract_json(body)
        code = int(result.get("code", result.get("ret", 0)) or 0)
        if code != 0:
            if code in LOGIN_ERROR_CODES and retry:
                self.refresh_cookies()
                return self._request(method, path, params, data, retry=False)
            raise QzoneError(str(result.get("message") or result.get("msg") or f"Qzone error {code}"), code)
        return result

    # ---------------------------------------------------------------- actions
    def list_posts(self, uin: int, num: int = 5) -> list:
        """Latest posts of one user (newest first). Raises QzoneError (no_permission) when their
        space is not visible to the bot."""
        result = self._request("GET", LIST_PATH, params={
            "uin": int(uin), "ftype": 0, "sort": 0, "pos": 0, "num": int(num), "replynum": 20,
            "callback": "_preloadCallback", "code_version": 1, "format": "jsonp", "need_private_comment": 1,
        })
        posts = []
        for m in result.get("msglist") or []:
            if not isinstance(m, dict) or not m.get("tid"):
                continue
            content = clean_text(m.get("content"))
            rt = m.get("rt_con") or {}
            if isinstance(rt, dict) and rt.get("content"):
                content = (content + " // " if content else "") + clean_text(rt.get("content"))
            comments = []
            for c in m.get("commentlist") or []:
                if isinstance(c, dict):
                    comments.append({"uin": int(c.get("uin") or 0), "name": str(c.get("name") or ""),
                                     "content": clean_text(c.get("content")),
                                     "time": int(c.get("create_time") or c.get("createTime2") or 0)})
            posts.append({
                "tid": str(m["tid"]),
                "uin": int(m.get("uin") or uin),
                "name": str(m.get("name") or ""),
                "content": content,
                "created": int(m.get("created_time") or 0),
                "pictures": len(m.get("pic") or []),
                "comment_count": int(m.get("cmtnum") or len(comments)),
                "comments": comments,
            })
        return posts

    def publish(self, text: str) -> str:
        result = self._request("POST", PUBLISH_PATH, data={
            "syn_tweet_verson": 1, "paramstr": 1, "who": 1, "con": text, "feedversion": 1, "ver": 1,
            "ugc_right": 1, "to_sign": 0, "hostuin": self.self_uin, "code_version": 1, "format": "json",
            "qzreferrer": f"https://user.qzone.qq.com/{self.self_uin}",
        })
        return str(result.get("tid") or "")

    def comment(self, owner_uin: int, tid: str, text: str):
        self._request("POST", COMMENT_PATH, data={
            "topicId": f"{int(owner_uin)}_{tid}__1", "feedsType": 100, "inCharset": "utf-8",
            "outCharset": "utf-8", "plat": "qzone", "source": "ic", "hostUin": int(owner_uin),
            "isSignIn": "", "platformid": 52, "uin": self.self_uin, "format": "fs", "ref": "feeds",
            "content": text, "richval": "", "richtype": "", "private": 0, "paramstr": 1,
            "qzreferrer": f"https://user.qzone.qq.com/{self.self_uin}",
        })

    def like(self, owner_uin: int, tid: str, created: int = 0):
        key = f"http://user.qzone.qq.com/{int(owner_uin)}/mood/{tid}"
        self._request("POST", LIKE_PATH, data={
            "qzreferrer": f"https://user.qzone.qq.com/{self.self_uin}", "opuin": self.self_uin,
            "unikey": key, "curkey": key, "from": 1, "appid": 311, "typeid": 0,
            "abstime": int(created or time.time()), "fid": tid, "active": 0, "fupdate": 1,
        })
