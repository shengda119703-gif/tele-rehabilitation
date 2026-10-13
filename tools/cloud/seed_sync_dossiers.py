"""Append marked, read-only sync acceptance dossiers to five requested accounts.

Dry-run is the default. No account, grant, real result, prescription or local
clinical store is replaced. Credentials stay in a private input file.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request
from uuid import NAMESPACE_URL, uuid5

SCHEMA = "ankang-sync-acceptance-1"
BATCH = "sync-acceptance:2026-10-13:v1"
NAMES = ("gh409", "ty211", "ljy666", "wz999", "lc783256")
CASES = (
    ("肩部活动", "男", 66, 168, 68, "肩部抬举不便", "高血压病史条目", "苯磺酸氨氯地平片", "shoulder_abduction", "肩外展", 95, 112,
     ("坐位肩外展", "肩胛控制", "肘屈伸")),
    ("膝部活动", "女", 69, 158, 62, "膝部上下楼不便", "膝关节退变条目", "对乙酰氨基酚片", "knee_flexion", "膝屈曲", 88, 103,
     ("坐位伸膝", "椅子坐站", "扶椅提踵")),
    ("颈部活动", "男", 58, 172, 74, "低头后颈部僵硬", "颈肩不适条目", "维生素D制剂", "neck_flexion", "颈前屈", 27, 34,
     ("轻缓颈部活动", "肩胛后收", "肩部放松")),
    ("腰背活动", "女", 64, 160, 65, "久坐后腰背不适", "血脂异常病史条目", "阿托伐他汀钙片", "trunk_flexion", "躯干前屈", 38, 46,
     ("骨盆控制", "坐位躯干控制", "扶椅髋外展")),
    ("下肢功能", "男", 73, 170, 70, "步行耐力下降", "骨健康关注条目", "碳酸钙制剂", "sit_to_stand", "坐站观察", 6, 8,
     ("椅子坐站", "扶椅重心转移", "扶椅提踵")),
)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def dossier(username, patient_id):
    i = NAMES.index(username)
    theme, sex, age, height, weight, problem, history, drug, action, label, old, new, exercises = CASES[i]
    sections = []

    def section(key, title, summary, pairs):
        sections.append({"key": key, "title": title, "summary": summary,
                         "rows": [{"label": k, "value": str(v)} for k, v in pairs]})

    section("profile", "身体档案", theme, [
        ("账号", username), ("档案姓名", f"同步验收{chr(65+i)}"), ("性别", sex),
        ("年龄", f"{age}岁"), ("身高", f"{height} cm"), ("体重", f"{weight} kg"),
        ("BMI", f"{weight/(height/100)**2:.1f}"), ("生活场景", "居家、手机使用"),
        ("目标", "验证本人、电脑和医生看到相同资料")])
    section("health", "健康问题与病史", problem, [
        ("主要问题", problem), ("病史条目", history), ("症状持续时间", "4周（情境字段）"),
        ("疼痛变化", f"{4+i%2}/10 → {2+i%2}/10（情境字段）"),
        ("过敏信息", "未提供实际过敏史"), ("手术史", "未提供实际手术史"),
        ("风险关注", "活动不适、耐力、平衡"), ("临床诊断", "未提供真实诊断文件")])
    section("medications", "用药资料", "药物展示条目，未启用处方或服药提醒", [
        ("药物条目", drug), ("剂型", "口服制剂"), ("剂量与频次", "需核对本人真实处方；本次不设置"),
        ("处方医生", "未提供实际处方"), ("提醒", "未启用"),
        ("10月10日记录样式", "已完成（仅验收状态）"),
        ("10月11日记录样式", "跳过（仅验收状态）"),
        ("10月12日记录样式", "待记录（仅验收状态）"), ("库存样式", "剩余14份（情境字段）")])
    unit = "次/30秒" if action == "sit_to_stand" else "°（展示角度）"
    section("assessment", "康复评估", f"{label} · 对比记录", [
        ("动作", label), ("动作标识", action), ("测试侧", "双侧" if action in {"sit_to_stand", "trunk_flexion"} else "左侧"),
        ("机位", "正面机位" if action == "shoulder_abduction" else "侧面机位"),
        ("10月6日展示值", f"{old} {unit}"), ("10月12日展示值", f"{new} {unit}"),
        ("完成次数样式", "3次"), ("观察时长样式", "30秒"),
        ("结论样式", "活动表现较前次改善，仍有提升空间"),
        ("测量证据", "无原片、无设备测量；不作为正式训练资格")])
    section("rehab_plan", "康复方案", "2周安排样式，非已发布医嘱", [
        ("目标", "循序改善活动、控制和耐力"), ("周期", "第1周熟悉动作；第2周复核表现"),
        ("安排日", "周一、周三、周五（展示字段）"),
        ("第一项", exercises[0]+" · 2组 × 8次"), ("第二项", exercises[1]+" · 2组 × 8次"),
        ("第三项", exercises[2]+" · 1组 × 8次"), ("组间休息", "60秒（展示字段）"),
        ("时长样式", "12分钟/次"), ("进阶逻辑", "依据后续真实评估、感受及专业确认"),
        ("执行状态", "未激活；不下发自动训练或医嘱")])
    section("training", "训练与反馈", "三次使用记录样式", [
        ("10月7日", "12分钟 · 2组 · 16次 · 感受轻松"),
        ("10月9日", "13分钟 · 2组 · 16次 · 感受适中"),
        ("10月12日", "12分钟 · 2组 · 16次 · 感受适中"),
        ("周汇总", "3次 · 37分钟 · 48次（情境字段）"),
        ("动作完成样式", "完成计划、组间休息、训练结束"),
        ("客观完成确认", "无自动识别证据；正式完成量不增加")])
    # A self-consistent calculation example, not measured muscle/barbell force.
    mass, velocity, acceleration = 20, 0.6+i*0.04, 1.2+i*0.1
    force = mass*(9.81+acceleration)
    section("fitness", "健身记录", "深蹲 · 20 kg · 计算展示", [
        ("动作", "深蹲"), ("器械质量", "20 kg（情境字段）"), ("组次样式", "2组 × 8次"),
        ("同一时刻速度", f"{velocity:.2f} m/s（非测量）"),
        ("同一时刻加速度", f"{acceleration:.2f} m/s²（非测量）"),
        ("外力计算", f"F = m(g+a) = {force:.1f} N（理想化计算）"),
        ("功率计算", f"P = Fv = {force*velocity:.1f} W（理想化计算）"),
        ("肌肉发力", "未测量"), ("原片与标定", "未提供，不写入正式分析结果")])
    section("daily_health", "健康指标与生活记录", "趋势字段供同步核对", [
        ("血压样式", f"{126+i*3}/{76+i} mmHg"), ("静息心率样式", f"{64+i*2} 次/分钟"),
        ("体重样式", f"{weight} kg"), ("睡眠样式", "22:30—06:30 · 8小时"),
        ("步数样式", f"{3800+i*350}步"), ("夜间起身样式", f"{i%2+1}次"),
        ("数据来源", "验收输入；未连接手环或居家摄像头"), ("报警", "未触发真实报警")])
    section("followup", "随访与复评", "一条完成样式和一条待办样式", [
        ("10月12日", "已填写样式：症状、训练感受、执行情况"),
        ("10月19日", "复评待办样式：同一动作、同一侧别、同一机位"),
        ("需补材料", "真实病史、处方、原片和训练记录"),
        ("医生审阅", "尚未开展真实审阅"), ("通知与日程", "仅显示，不派发提醒")])
    section("family", "家庭与医生协作", "家庭联系场景，不创建或冒领家属账号", [
        ("家属显示名", f"验收联系人{i+1}"), ("关系样式", "子女"), ("真实联系方式", "未提供"),
        ("共用医生账号", "doctor"), ("授权状态", "以云端现有授权为准；本次不更改"),
        ("语音/视频通话", "未建立真实通话"), ("消息样式", "请查看本周训练记录（验收文字）")])
    section("assistant", "智能康复管家", "本周汇总场景，仅模板文字", [
        ("问题样式", "我这周完成了哪些训练？"),
        ("回答样式", f"此验收档案展示了3次{theme}相关训练、1组评估对比及复评待办。"),
        ("可核对信息", "健康问题、用药条目、方案、评估、训练与随访"),
        ("生成来源", "固定验收模板；未调用医师、语言模型或语音服务")])
    return {"schema": SCHEMA, "batch_id": BATCH, "patient_id": patient_id, "username": username,
            "title": "完整身体与使用档案 · 同步验收", "text": theme+"情境；资料为验收输入，不是实测结果或医嘱。",
            "source": "SYNC_ACCEPTANCE", "synthetic": True, "read_only": True,
            "clinical_use": False, "execution_enabled": False,
            "provenance": {"kind": "SYNC_ACCEPTANCE", "evidence": "NONE", "created_for": "CROSS_CLIENT_SYNC_CHECK"},
            "sections": sections}


def document(username, patient_id):
    return {"operation_id": str(uuid5(NAMESPACE_URL, "urn:ankang:"+BATCH+":"+patient_id)),
            "source_event_id": BATCH,
            "installation_id": "ankang-sync-acceptance-v1", "source_kind": "IMPORT",
            "payload": dossier(username, patient_id)}


class API:
    def __init__(self, base):
        if base != "https://139.224.216.18":
            raise ValueError("Only the verified production origin is allowed")
        self.base = base+"/api/cloud/v1"
        self.context = ssl.create_default_context()
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.context))

    def call(self, path, body=None, token=None):
        headers = {"Content-Type": "application/json", "X-Ankang-Client": "native"}
        if token:
            headers["Authorization"] = "Bearer "+token
        request = urllib.request.Request(self.base+path, headers=headers,
            data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
            method="GET" if body is None else "POST")
        try:
            with self.opener.open(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Cloud request failed ({exc.code}); no credentials printed") from None

    @contextmanager
    def session(self, item, kind="DESKTOP"):
        signed = self.call("/auth/password/login", {"username": item["username"], "password": item["password"], "client_kind": kind})
        token = signed["access_token"]
        try:
            if signed.get("role") != "PATIENT" or signed.get("username") != item["username"]:
                raise RuntimeError("Patient identity mismatch")
            yield signed, token
        finally:
            self.call("/auth/logout", {}, token)

    def records(self, ident, token):
        result, offset = [], 0
        while True:
            chunk = self.call(f"/patients/{ident}/records?offset={offset}&limit=100", token=token)["items"]
            result.extend(chunk)
            if len(chunk) < 100:
                return result
            offset += 100


def inputs(path):
    items = json.loads(path.read_text(encoding="utf-8-sig"))
    if (not isinstance(items, list) or len(items) != 5 or
        any(set(x) != {"username", "password"} for x in items) or
        sorted(x["username"] for x in items) != sorted(NAMES)):
        raise ValueError("Exactly the five requested accounts are required; no creation/reset permitted")
    return sorted(items, key=lambda x: NAMES.index(x["username"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("private_file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--base", default="https://139.224.216.18")
    args = parser.parse_args()
    api = API(args.base)
    for item in inputs(args.private_file):
        with api.session(item) as (signed, token):
            ident = signed["patient_id"]
            profile = api.call("/patients/"+ident, token=token)
            before = api.records(ident, token)
            original = {r["id"]: fingerprint(r) for r in before}
            packet = document(item["username"], ident)
            own = [r for r in before if r["payload"].get("schema") == SCHEMA and r["payload"].get("batch_id") == BATCH]
            if len(own) > 1 or own and own[0]["payload"] != packet["payload"]:
                raise RuntimeError("Existing acceptance data differs; nothing replaced")
            receipt = None
            if args.apply:
                receipt = api.call(f"/patients/{ident}/record-events", packet, token)
                if receipt.get("status") != "COMMITTED":
                    raise RuntimeError("Cloud did not confirm commit")
                after = api.records(ident, token)
                index = {r["id"]: r for r in after}
                if any(key not in index or fingerprint(index[key]) != value for key, value in original.items()):
                    raise RuntimeError("Preexisting records changed; stop and inspect")
                stored = index.get(receipt["resource_id"])
                if not stored or stored["source_kind"] != "IMPORT" or stored["payload"] != packet["payload"]:
                    raise RuntimeError("Read-back mismatch")
                after_profile = api.call("/patients/"+ident, token=token)
                if after_profile != profile:
                    raise RuntimeError("Patient identity or grant changed")
            print(json.dumps({"username": item["username"], "before_records": len(before),
                "existing_acceptance": len(own), "sections": len(packet["payload"]["sections"]),
                "fields": sum(len(s["rows"]) for s in packet["payload"]["sections"]),
                "bytes": len(json.dumps(packet, ensure_ascii=False).encode()),
                "doctor_access": profile["doctor_access"], "mode": "APPLY" if args.apply else "DRY_RUN",
                "committed": bool(receipt), "idempotent": receipt.get("idempotent") if receipt else None,
                "payload_sha256": fingerprint(packet["payload"]), "preexisting_unchanged": True if receipt else None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
