import io
import os
import re
import secrets
import string
from collections import Counter
from functools import wraps
from urllib.parse import urljoin

import qrcode
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for

from store import DEFAULT_QUESTIONS, get_store, utc_now_iso

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
store = get_store()

SESSION_ID_CHARS = string.ascii_uppercase + string.digits
STOPWORDS = {
    "업무", "자료", "확인", "작성", "하는", "하고", "있습니다", "대한", "때문", "관련", "매월", "매일",
    "처리", "필요", "기관", "내용", "결과", "정리", "사람", "마다", "에서", "으로", "하는데", "너무",
}


def admin_configured():
    if os.getenv("ADMIN_PASSWORD"):
        return True
    return os.getenv("DATA_BACKEND", "firestore").lower() == "local"


def admin_password():
    return os.getenv("ADMIN_PASSWORD") or ("admin" if os.getenv("DATA_BACKEND", "firestore").lower() == "local" else "")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def make_session_id(length=6):
    for _ in range(20):
        sid = "".join(secrets.choice(SESSION_ID_CHARS) for _ in range(length))
        if not store.get_session(sid):
            return sid
    raise RuntimeError("Could not generate unique session id")


def absolute_url(path):
    return urljoin(request.url_root, path.lstrip("/"))


def normalize_question_form(form, existing):
    out = []
    for q in existing:
        q2 = dict(q)
        label = (form.get(f"label_{q['id']}") or q["label"]).strip()
        q2["label"] = label[:200]
        if q["type"] in {"single", "multi"}:
            raw = form.get(f"options_{q['id']}", "")
            opts = [x.strip() for x in raw.split("\n") if x.strip()]
            if opts:
                q2["options"] = opts[:12]
        if q["type"] in {"text", "textarea"}:
            q2["placeholder"] = (form.get(f"placeholder_{q['id']}") or q.get("placeholder", ""))[:220]
        out.append(q2)
    return out


def validate_answers(session_obj, form):
    answers = {}
    errors = []
    for q in session_obj.get("questions", []):
        qid = q["id"]
        qtype = q["type"]
        if qtype == "multi":
            value = [x.strip() for x in form.getlist(qid) if x.strip()]
        else:
            value = (form.get(qid) or "").strip()

        if q.get("required") and (not value):
            errors.append(f"'{q['label']}' 항목에 응답해주세요.")
            continue

        if qtype in {"single", "multi"} and value:
            allowed = set(q.get("options", []))
            vals = value if isinstance(value, list) else [value]
            if any(v not in allowed for v in vals):
                errors.append("선택 항목이 올바르지 않습니다.")
                continue
        if qtype == "scale" and value:
            try:
                iv = int(value)
                if not q.get("min", 1) <= iv <= q.get("max", 5):
                    raise ValueError
                value = iv
            except ValueError:
                errors.append("척도 응답이 올바르지 않습니다.")
                continue
        if isinstance(value, str):
            value = value[:2000]
        answers[qid] = value
    return answers, errors


def distribution(responses, qid):
    c = Counter()
    for r in responses:
        v = (r.get("answers") or {}).get(qid)
        if isinstance(v, list):
            c.update([str(x) for x in v if x])
        elif v not in (None, ""):
            c[str(v)] += 1
    return dict(c.most_common())


def keyword_cloud(responses):
    c = Counter()
    for r in responses:
        a = r.get("answers") or {}
        text = f"{a.get('q2','')} {a.get('q7','')}"
        for tok in re.findall(r"[가-힣A-Za-z0-9]{2,}", text):
            if tok not in STOPWORDS and not tok.isdigit():
                c[tok] += 1
    return [{"word": w, "count": n} for w, n in c.most_common(20)]


def live_payload(session_obj):
    responses = store.list_responses(session_obj["id"], limit=500)
    scale_values = []
    cards = []
    for r in responses:
        a = r.get("answers") or {}
        try:
            if a.get("q6") not in (None, ""):
                scale_values.append(int(a.get("q6")))
        except Exception:
            pass
        if a.get("q2") or a.get("q7"):
            cards.append({
                "title": a.get("q2") or "자유응답",
                "detail": a.get("q7") or "",
                "category": a.get("q1") or "",
                "frequency": a.get("q3") or "",
                "rule": a.get("q5") or "",
                "submitted_at": r.get("submitted_at"),
            })
    return {
        "session": {"id": session_obj["id"], "title": session_obj.get("title"), "subtitle": session_obj.get("subtitle", "")},
        "response_count": len(responses),
        "distributions": {
            "q1": distribution(responses, "q1"),
            "q3": distribution(responses, "q3"),
            "q4": distribution(responses, "q4"),
            "q5": distribution(responses, "q5"),
        },
        "ai_average": round(sum(scale_values) / len(scale_values), 1) if scale_values else None,
        "cards": cards[:80],
        "keywords": keyword_cloud(responses),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True, "backend": os.getenv("DATA_BACKEND", "firestore")}


@app.get("/")
def home():
    active_id = store.get_active_session_id()
    active = store.get_session(active_id) if active_id else None
    return render_template("home.html", active=active)


@app.get("/today")
def today():
    sid = store.get_active_session_id()
    if not sid:
        return render_template("no_active.html"), 200
    if not store.get_session(sid):
        return render_template("no_active.html"), 200
    return redirect(url_for("join_session", session_id=sid))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if not admin_configured():
            error = "관리자 비밀번호가 설정되지 않았습니다. Cloud Run 환경변수 ADMIN_PASSWORD를 설정해주세요."
        elif secrets.compare_digest(request.form.get("password", ""), admin_password()):
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_home"))
        else:
            error = "비밀번호가 맞지 않습니다."
    return render_template("admin_login.html", error=error, configured=admin_configured())


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/admin")
@admin_required
def admin_home():
    sessions = store.list_sessions()
    active_id = store.get_active_session_id()
    return render_template("admin.html", sessions=sessions, active_id=active_id, default_questions=DEFAULT_QUESTIONS)


@app.post("/admin/sessions")
@admin_required
def admin_create_session():
    title = (request.form.get("title") or "새 강의").strip()[:100]
    subtitle = (request.form.get("subtitle") or "").strip()[:180]
    sid = make_session_id()
    obj = {
        "id": sid,
        "title": title,
        "subtitle": subtitle,
        "created_at": utc_now_iso(),
        "questions": DEFAULT_QUESTIONS,
    }
    store.create_session(obj)
    if request.form.get("activate") == "1" or not store.get_active_session_id():
        store.set_active_session(sid)
    return redirect(url_for("admin_session", session_id=sid))


@app.get("/admin/sessions/<session_id>")
@admin_required
def admin_session(session_id):
    obj = store.get_session(session_id)
    if not obj:
        abort(404)
    return render_template(
        "admin_session.html",
        s=obj,
        active_id=store.get_active_session_id(),
        join_url=absolute_url(url_for("join_session", session_id=session_id)),
        live_url=absolute_url(url_for("live_session", session_id=session_id)),
        today_url=absolute_url(url_for("today")),
    )


@app.post("/admin/sessions/<session_id>/update")
@admin_required
def admin_update_session(session_id):
    obj = store.get_session(session_id)
    if not obj:
        abort(404)
    questions = normalize_question_form(request.form, obj.get("questions", DEFAULT_QUESTIONS))
    store.update_session(session_id, {
        "title": (request.form.get("title") or obj.get("title", "")).strip()[:100],
        "subtitle": (request.form.get("subtitle") or "").strip()[:180],
        "questions": questions,
    })
    return redirect(url_for("admin_session", session_id=session_id, saved=1))


@app.post("/admin/sessions/<session_id>/activate")
@admin_required
def admin_activate_session(session_id):
    if not store.get_session(session_id):
        abort(404)
    store.set_active_session(session_id)
    return redirect(request.referrer or url_for("admin_home"))


@app.route("/join/<session_id>", methods=["GET", "POST"])
def join_session(session_id):
    obj = store.get_session(session_id)
    if not obj:
        abort(404)
    errors = []
    if request.method == "POST":
        answers, errors = validate_answers(obj, request.form)
        client_id = (request.form.get("client_id") or secrets.token_hex(12))[:80]
        if not errors:
            if not store.save_response(session_id, client_id, answers):
                abort(404)
            return render_template("thanks.html", s=obj)
    return render_template("join.html", s=obj, errors=errors)


@app.get("/live/<session_id>")
def live_session(session_id):
    obj = store.get_session(session_id)
    if not obj:
        abort(404)
    return render_template("live.html", s=obj)


@app.get("/api/sessions/<session_id>/live")
def api_live(session_id):
    obj = store.get_session(session_id)
    if not obj:
        return jsonify({"error": "not_found"}), 404
    return jsonify(live_payload(obj))


@app.get("/qr/today.png")
def qr_today():
    return qr_png(absolute_url(url_for("today")), "today-qr.png")


@app.get("/qr/session/<session_id>.png")
def qr_session(session_id):
    if not store.get_session(session_id):
        abort(404)
    return qr_png(absolute_url(url_for("join_session", session_id=session_id)), f"{session_id}-qr.png")


def qr_png(target, filename):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(target)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    as_attachment = request.args.get("download") == "1"
    return send_file(bio, mimetype="image/png", as_attachment=as_attachment, download_name=filename)


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
