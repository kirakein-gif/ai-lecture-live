import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_QUESTIONS = [
    {
        "id": "q1",
        "type": "single",
        "label": "현재 가장 많은 시간을 쓰는 업무 분야는 무엇인가요?",
        "options": ["자료취합·실적관리", "문서·보고서 작성", "엑셀·통계", "민원·상담", "계약·회계", "인사·복무", "기타"],
        "required": True,
    },
    {
        "id": "q2",
        "type": "text",
        "label": "가장 줄이고 싶은 반복업무를 한 문장으로 적어주세요.",
        "placeholder": "예: 매월 기관별 엑셀 실적을 받아 하나로 합치고 누락을 확인하는 일",
        "required": True,
    },
    {
        "id": "q3",
        "type": "single",
        "label": "이 업무는 얼마나 자주 반복되나요?",
        "options": ["매일", "매주", "매월", "분기·반기", "비정기"],
        "required": True,
    },
    {
        "id": "q4",
        "type": "multi",
        "label": "이 업무가 번거로운 이유는 무엇인가요?",
        "options": ["같은 내용을 반복 입력", "자료 형식이 제각각", "규정·기준 확인이 복잡", "자료가 여러 곳에 흩어짐", "누락·오류 확인이 번거로움", "관행적으로 계속 해옴", "시스템에서 지원하지 않음", "기타"],
        "required": True,
    },
    {
        "id": "q5",
        "type": "single",
        "label": "이 업무에는 정해진 규칙이나 절차가 있나요?",
        "options": ["대부분 정해져 있음", "일부만 정해져 있음", "상황마다 판단이 다름"],
        "required": True,
    },
    {
        "id": "q6",
        "type": "scale",
        "label": "AI나 자동화가 이 업무에 도움이 될 것 같나요?",
        "min": 1,
        "max": 5,
        "min_label": "전혀 아니다",
        "max_label": "매우 그렇다",
        "required": True,
    },
    {
        "id": "q7",
        "type": "textarea",
        "label": "현재 이 업무를 어떻게 처리하는지, 어려운 점을 조금 더 적어주세요.",
        "placeholder": "개인정보·민감정보는 적지 마세요. 실제 처리 흐름만 간단히 적어주시면 됩니다.",
        "required": False,
    },
]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class LocalStore:
    """Local JSON store for preview/development only. Not for production persistence."""

    def __init__(self, path=None):
        self.path = Path(path or os.getenv("LOCAL_STORE_PATH", "data/local_store.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        if not self.path.exists():
            self._write({"settings": {"active_session_id": None}, "sessions": {}, "responses": {}})

    def _read(self):
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data):
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def list_sessions(self):
        with self.lock:
            d = self._read()
            items = list(d["sessions"].values())
            items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            for item in items:
                item["response_count"] = len(d["responses"].get(item["id"], {}))
            return items

    def get_session(self, session_id):
        with self.lock:
            d = self._read()
            s = d["sessions"].get(session_id)
            if not s:
                return None
            out = deepcopy(s)
            out["response_count"] = len(d["responses"].get(session_id, {}))
            return out

    def create_session(self, session_obj):
        with self.lock:
            d = self._read()
            d["sessions"][session_obj["id"]] = deepcopy(session_obj)
            d["responses"].setdefault(session_obj["id"], {})
            self._write(d)
        return session_obj

    def update_session(self, session_id, patch):
        with self.lock:
            d = self._read()
            if session_id not in d["sessions"]:
                return None
            d["sessions"][session_id].update(deepcopy(patch))
            self._write(d)
            return deepcopy(d["sessions"][session_id])

    def set_active_session(self, session_id):
        with self.lock:
            d = self._read()
            if session_id is not None and session_id not in d["sessions"]:
                return False
            d["settings"]["active_session_id"] = session_id
            self._write(d)
            return True

    def get_active_session_id(self):
        with self.lock:
            return self._read()["settings"].get("active_session_id")

    def save_response(self, session_id, client_id, answers):
        with self.lock:
            d = self._read()
            if session_id not in d["sessions"]:
                return False
            d["responses"].setdefault(session_id, {})[client_id] = {
                "client_id": client_id,
                "answers": answers,
                "submitted_at": utc_now_iso(),
            }
            self._write(d)
            return True

    def list_responses(self, session_id, limit=500):
        with self.lock:
            d = self._read()
            rows = list(d["responses"].get(session_id, {}).values())
            rows.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
            return rows[:limit]


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore
        self.firestore = firestore
        self.db = firestore.Client()

    def list_sessions(self):
        docs = self.db.collection("sessions").stream()
        out = []
        for doc in docs:
            item = doc.to_dict() or {}
            item["id"] = doc.id
            item["response_count"] = self._response_count(doc.id)
            out.append(item)
        out.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return out

    def _response_count(self, session_id):
        try:
            agg = self.db.collection("sessions").document(session_id).collection("responses").count().get()
            return int(agg[0][0].value)
        except Exception:
            return sum(1 for _ in self.db.collection("sessions").document(session_id).collection("responses").stream())

    def get_session(self, session_id):
        doc = self.db.collection("sessions").document(session_id).get()
        if not doc.exists:
            return None
        item = doc.to_dict() or {}
        item["id"] = doc.id
        item["response_count"] = self._response_count(session_id)
        return item

    def create_session(self, session_obj):
        payload = deepcopy(session_obj)
        payload.pop("id", None)
        self.db.collection("sessions").document(session_obj["id"]).set(payload)
        return session_obj

    def update_session(self, session_id, patch):
        ref = self.db.collection("sessions").document(session_id)
        if not ref.get().exists:
            return None
        ref.update(deepcopy(patch))
        return self.get_session(session_id)

    def set_active_session(self, session_id):
        self.db.collection("settings").document("global").set({"active_session_id": session_id}, merge=True)
        return True

    def get_active_session_id(self):
        doc = self.db.collection("settings").document("global").get()
        if not doc.exists:
            return None
        return (doc.to_dict() or {}).get("active_session_id")

    def save_response(self, session_id, client_id, answers):
        if not self.db.collection("sessions").document(session_id).get().exists:
            return False
        self.db.collection("sessions").document(session_id).collection("responses").document(client_id).set({
            "client_id": client_id,
            "answers": answers,
            "submitted_at": self.firestore.SERVER_TIMESTAMP,
        })
        return True

    def list_responses(self, session_id, limit=500):
        q = (self.db.collection("sessions").document(session_id).collection("responses")
             .order_by("submitted_at", direction=self.firestore.Query.DESCENDING).limit(limit))
        rows = []
        for doc in q.stream():
            x = doc.to_dict() or {}
            x["client_id"] = doc.id
            dt = x.get("submitted_at")
            if hasattr(dt, "isoformat"):
                x["submitted_at"] = dt.isoformat()
            rows.append(x)
        return rows


def get_store():
    backend = os.getenv("DATA_BACKEND", "firestore").strip().lower()
    if backend == "local":
        return LocalStore()
    return FirestoreStore()
