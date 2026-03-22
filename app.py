# app.py
import os
from datetime import datetime

import streamlit as st
from core.engine import DaptRuleEngine
from core.oac_engine import OacRuleEngine


# ----------------------------
# TABLE 5 (ESC) -> Surgery list & risk mapping
# ----------------------------
SURGERY_TABLE5 = {
    "Düşük": [
        "Meme cerrahisi (Breast)",
        "Dental girişimler (Dental)",
        "Endokrin: Tiroid (Endocrine: thyroid)",
        "Göz cerrahisi (Eye)",
        "Jinekolojik: Minör (Gynaecological: minor)",
        "Ortopedik minör: Menisektomi (Orthopaedic minor - meniscectomy)",
        "Rekonstrüktif cerrahi (Reconstructive)",
        "Yüzeyel cerrahi (Superficial surgery)",
        "Ürolojik minör: TUR-P (Transurethral resection of prostate)",
        "VATS minör akciğer rezeksiyonu (VATS minor lung resection)",
    ],
    "Orta": [
        "Karotis asemptomatik: CEA veya CAS (Carotid asymptomatic - CEA/CAS)",
        "Karotis semptomatik: CEA (Carotid symptomatic - CEA)",
        "Endovasküler AAA onarımı: EVAR (Endovascular aortic aneurysm repair)",
        "Baş-boyun cerrahisi (Head or neck surgery)",
        "İntraperitoneal: Splenektomi / Hiatal herni / Kolesistektomi (Intraperitoneal)",
        "İntratorasik: Majör olmayan (Intrathoracic - non-major)",
        "Nörolojik veya ortopedik majör: Kalça / Omurga (Major hip and spine surgery)",
        "Periferik arter anjiyoplasti (Peripheral arterial angioplasty)",
        "Renal transplant (Renal transplants)",
        "Ürolojik veya jinekolojik majör (Urological or gynaecological - major)",
    ],
    "Yüksek": [
        "Adrenal rezeksiyon (Adrenal resection)",
        "Aort ve majör vasküler cerrahi (Aortic and major vascular surgery)",
        "Karotis semptomatik: CAS (Carotid symptomatic - CAS)",
        "Duodeno-pankreatik cerrahi (Duodenal-pancreatic surgery)",
        "Karaciğer rezeksiyonu / Safra yolu cerrahisi (Liver resection / bile duct surgery)",
        "Özofajektomi (Oesophagectomy)",
        "Açık alt ekstremite revaskülarizasyonu (akut iskemi) veya amputasyon",
        "Pnömonektomi (VATS veya açık) (Pneumonectomy)",
        "Pulmoner veya karaciğer transplantı (Pulmonary or liver transplant)",
        "Perfore barsak onarımı (Repair of perforated bowel)",
        "Total sistektomi (Total cystectomy)",
    ],
}

SURGERY_TO_RISK = {}
SURGERY_OPTIONS = []
for risk, items in SURGERY_TABLE5.items():
    for it in items:
        SURGERY_OPTIONS.append(it)
        SURGERY_TO_RISK[it] = risk


# ----------------------------
# Drugs list (optional SGK CSV)
# ----------------------------
DEFAULT_DRUGS = sorted(
    list(
        {
            "Aspirin",
            "Klopidogrel",
            "Prasugrel",
            "Tikagrelor",
            "Warfarin",
            "Apiksaban",
            "Rivaroksaban",
            "Edoksaban",
            "Dabigatran",
            "Enoksaparin",
            "Dalteparin",
            "Fondaparinuks",
            "Metoprolol",
            "Bisoprolol",
            "Nebivolol",
            "Carvedilol",
            "Propranolol",
            "Diltiazem",
            "Verapamil",
            "Amiodaron",
            "Digoksin",
            "Amlodipin",
            "Ramipril",
            "Perindopril",
            "Enalapril",
            "Valsartan",
            "Losartan",
            "Sacubitril/Valsartan",
            "Furosemid",
            "Torasemid",
            "Spironolakton",
            "Eplerenon",
            "Empagliflozin",
            "Dapagliflozin",
            "Atorvastatin",
            "Rosuvastatin",
            "Pantoprazol",
            "Omeprazol",
        }
    )
)


def load_drug_list():
    csv_path = os.path.join("data", "sgk_ilaclar.csv")
    if os.path.exists(csv_path):
        try:
            import pandas as pd

            df = pd.read_csv(csv_path)
            if "drug_name" in df.columns:
                drugs = df["drug_name"].dropna().astype(str).unique().tolist()
            else:
                drugs = df.iloc[:, 0].dropna().astype(str).unique().tolist()
            drugs = sorted(set([d.strip() for d in drugs if d.strip()]))
            if drugs:
                return drugs, f"İlaç listesi: data/sgk_ilaclar.csv ({len(drugs)} kayıt)"
        except Exception as e:
            return DEFAULT_DRUGS, f"İlaç listesi: varsayılan (CSV okunamadı: {e})"
    return DEFAULT_DRUGS, "İlaç listesi: varsayılan (CSV yok)"


DRUGS, DRUGS_CAPTION = load_drug_list()


# ----------------------------
# Clinical helpers
# ----------------------------
BETA_BLOCKERS = {"metoprolol", "bisoprolol", "nebivolol", "carvedilol", "propranolol"}
NON_DHP_CCB = {"diltiazem", "verapamil"}

DOAC_INTERACT_EDOXABAN = {
    "siklosporin",
    "cyclosporine",
    "dronedarone",
    "eritromisin",
    "erythromycin",
    "ketokonazol",
    "ketoconazole",
}


def meds_contains_any(meds, needles_lower_set):
    meds_l = [m.lower() for m in (meds or [])]
    for n in needles_lower_set:
        if any(n in m for m in meds_l):
            return True
    return False


# ----------------------------
# RCRI helpers
# ----------------------------
RCRI_ITEMS_TR = {
    "high_risk_surgery": "Yüksek riskli cerrahi (intraperitoneal / intratorasik / suprainguinal vasküler)",
    "ihd": "İskemik kalp hastalığı (MI/anjina/pozitif stres testi/nitrat/Q dalgası)",
    "chf": "Kalp yetersizliği öyküsü (pulmoner ödem/PND/S3/raller vb.)",
    "cva": "Serebrovasküler hastalık (inme/TIA)",
    "dm_insulin": "İnsülin kullanan DM",
    "cr_gt2": "Kreatinin >2.0 mg/dL (≈177 µmol/L)",
}


def calc_rcri(flags: dict) -> tuple[int, list[str]]:
    positives = []
    score = 0
    for k, label in RCRI_ITEMS_TR.items():
        if bool(flags.get(k, False)):
            score += 1
            positives.append(label)
    return score, positives


def esc_rcri_pathway_summary(
    surgery_risk: str,
    rcri_score: int,
    functional_capacity: str,
    symptoms: list[str],
    urgency: str,
    has_hf: str,
    lvef: str,
) -> tuple[str, list[str]]:
    symp = symptoms or []
    active_symptoms = [s for s in symp if s != "Yok"]
    has_active_cardiac_symptoms = any(
        s in active_symptoms for s in ["Angina", "Senkop", "Kalp yetersizliği semptomu", "Dispne"]
    )

    high_risk_surg = surgery_risk == "Yüksek"
    intermediate_surg = surgery_risk == "Orta"
    low_surg = surgery_risk == "Düşük"

    poor_fc = functional_capacity == "<4 MET"
    unknown_fc = functional_capacity == "Bilinmiyor"

    unstable_flag = bool(has_active_cardiac_symptoms)

    workup: list[str] = []
    pathway_lines: list[str] = []

    # --- ACİL ---
    if urgency == "Acil":
        pathway_lines.append("Acil cerrahi → Yalnızca tedaviyi değiştirecek testler yapılır.")
        workup.append("ECG + klinik değerlendirme.")
    else:
        pathway_lines.append(
            "Elektif cerrahi → Cerrahi risk, RCRI, efor kapasitesi ve semptomlara göre değerlendirme."
        )

    # --- AKTİF SEMPTOM ---
    if unstable_flag:
        pathway_lines.append(
            "Aktif kardiyak semptom mevcut → Önce kardiyak stabilizasyon sağlanmalı."
        )
        workup.append("Kardiyoloji konsültasyonu.")
        workup.append("Ekokardiyografi (KY/dispne/üfürüm varsa veya EF bilinmiyorsa).")
        if high_risk_surg or intermediate_surg:
            workup.append("Troponin (bazal) + postop 48–72 saat izlem.")
            workup.append("BNP/NT-proBNP.")
        return "\n".join([f"- {x}" for x in pathway_lines]), workup

    # --- DÜŞÜK RİSK PROFİLİ ---
    if low_surg and rcri_score == 0 and functional_capacity == "≥4 MET":
        pathway_lines.append("Düşük riskli profil (düşük cerrahi risk + RCRI 0 + iyi efor kapasitesi) → Ek kardiyak test gerekmez.")
        workup.append("Rutin perioperatif izlem, gerekirse bazal ECG.")
        return "\n".join([f"- {x}" for x in pathway_lines]), workup

    # --- ARTIRILMIŞ RİSK ---
    if high_risk_surg or intermediate_surg or rcri_score >= 1 or poor_fc or unknown_fc:
        risk_factors = []
        if high_risk_surg or intermediate_surg:
            risk_factors.append(f"cerrahi risk: {surgery_risk}")
        if rcri_score >= 1:
            risk_factors.append(f"RCRI: {rcri_score}")
        if poor_fc or unknown_fc:
            risk_factors.append(f"efor kapasitesi: {functional_capacity}")
        pathway_lines.append(f"Risk artırıcı faktörler: {', '.join(risk_factors)}.")

        workup.append("Bazal ECG.")

        if high_risk_surg or intermediate_surg:
            workup.append("Troponin (bazal) + postop 48–72 saat izlem.")

        if intermediate_surg or high_risk_surg or poor_fc or unknown_fc:
            workup.append("Ekokardiyografi (KY/kapak hastalığı/dispne varsa öncelikli).")

        if high_risk_surg or rcri_score >= 2 or poor_fc or unknown_fc:
            workup.append("BNP/NT-proBNP (≥65 yaş veya orta/yüksek riskli cerrahide).")

        if (high_risk_surg or rcri_score >= 2) and (poor_fc or unknown_fc) and urgency != "Acil":
            workup.append(
                "Efor kapasitesi düşük/bilinmiyor → Tedaviyi değiştirecekse iskemi testi düşünülebilir."
            )

        pathway_lines.append("Not: Testler yalnızca tedavi kararını değiştirecekse istenmelidir.")
        return "\n".join([f"- {x}" for x in pathway_lines]), workup

    # --- DÜŞÜK-ORTA RİSK ---
    pathway_lines.append("Düşük-orta riskli profil → Bazal ECG + klinik değerlendirme yeterli.")
    workup.append("Bazal ECG.")
    return "\n".join([f"- {x}" for x in pathway_lines]), workup


def get_mech_valve_warfarin_note() -> str:
    return "\n".join(
        [
            "MEKANİK KAPAK – WARFARİN YÖNETİMİ ve ENFEKTİF ENDOKARDİT PROFİLAKSİSİ ",
            "- Warfarin operasyon tarihinden **5 gün önce kesilmelidir**.",
            "- Operasyon sabahı hedef **INR < 1.5** olacak şekilde planlama yapılmalıdır.",
            "- INR operasyon öncesi gün kontrol edilmelidir.",
            "",
            "Enfektif Endokardit Profilaksisi:",
            "- Standart: **Amoksisilin 2 g PO** (işlemden 30–60 dk önce).",
            "- Penisilin alerjisi varsa: **Klindamisin 600 mg PO** veya **Azitromisin 500 mg PO**.",
            "",
            "Postop Warfarin:",
            "- Hemostaz sağlandıktan sonra genellikle **operasyondan 12–24 saat sonra** başlanabilir.",
            "- Büyük kanama riski varsa **48–72 saate** ertelenebilir.",
            "- Başlangıç dozu: hastanın **önceki stabil dozuna göre** başlanır.",
            "",
            "INR Hedefleri:",
            "- Mekanik mitral kapak: **2.5–3.5**",
            "- Mekanik aort kapak: **2.0–3.0**",
            "- Atriyal fibrilasyon: **2.0–3.0**",
            "",
            "Bridging:",
            "- **INR >2 olana kadar LMWH ile bridging uygulanır; INR >2 olduktan sonra LMWH kesilmesi uygundur.**",
        ]
    )


def get_device_management_note(has_device: str, device_type: str, pace_dependent: str) -> str:
    if has_device != "Evet":
        return ""

    dt = (device_type or "").strip()
    pd = (pace_dependent or "").strip()

    if dt not in {"Permanent pacemaker", "ICD", "CRT"}:
        return "- Cihaz: Belirtilmedi.\n"

    if pd not in {"Evet", "Hayır"}:
        return f"- Cihaz: {dt}. Pace bağımlılığı belirtilmedi.\n"

    if dt == "Permanent pacemaker":
        if pd == "Evet":
            return "- Cihaz: Permanent pacemaker. **Pace bağımlı** → **VOO 80 bpm** moduna alınmalı (perioperatif plan).\n"
        return "- Cihaz: Permanent pacemaker. Pace bağımlı değil → **VVI 40 bpm** alınmalı (perioperatif plan).\n"

    if pd == "Evet":
        return f"- Cihaz: {dt}. **Pace bağımlı** → **Taşi-terapiler kapatılmalı** + **VOO 80 bpm** moduna alınmalı.\n"
    return f"- Cihaz: {dt}. Pace bağımlı değil → **Taşi-terapiler kapatılmalı** + **VVI 40 bpm** alınmalı.\n"


def get_bradycardia_meds_note(hr: int, has_hf: str, current_meds: list[str]) -> str:
    if hr >= 60:
        return ""

    on_bb = meds_contains_any(current_meds, BETA_BLOCKERS)
    on_non_dhp = meds_contains_any(current_meds, NON_DHP_CCB)

    if not (on_bb or on_non_dhp):
        return ""

    if has_hf != "Evet":
        return (
            "- Bradikardi (HR<60/dk) ve hız düşürücü ilaç kullanımı mevcut: "
            "perioperatif dönemde hemodinami uygunsa beta-bloker ve/veya non-DHP KKB doz azaltımı "
            "veya geçici kesilmesi (hold) uygundur.\n"
        )

    if on_bb:
        return (
            "- Bradikardi (HR<60/dk) mevcut: kalp yetersizliği varlığında perioperatif dönemde "
            "beta-bloker doz azaltımı veya geçici kesilmesi (hold) hemodinamiye göre uygundur.\n"
        )

    return (
        "- Bradikardi (HR<60/dk) mevcut: hemodinamiye göre hız düşürücü ajanların doz azaltımı "
        "veya geçici kesilmesi (hold) düşünülebilir.\n"
    )


def get_doac_dose_warnings(
    agent: str,
    age: int,
    egfr: float,
    current_meds: list[str],
    bleed_risk: str,
    very_high_bleed: bool,
) -> list[str]:
    warnings: list[str] = []
    a = (agent or "").strip().lower()
    meds_l = [m.lower() for m in (current_meds or [])]
    has_verapamil = any("verapamil" in m for m in meds_l)
    has_edox_interaction = any(any(x in m for m in meds_l) for x in DOAC_INTERACT_EDOXABAN)
    high_bleed = (bleed_risk == "Yüksek") or bool(very_high_bleed)

    if egfr is None:
        egfr = 0.0

    if a in {"apiksaban", "apixaban"}:
        if egfr < 15:
            warnings.append("⚠️ Apiksaban: eGFR <15 → **kesme/kaçınma uyarısı**.")
        elif (age >= 80 and egfr < 30):
            warnings.append("⚠️ Apiksaban: yaş ≥80 + eGFR <30 → **doz azaltımı uyarısı**.")
        elif egfr < 30:
            warnings.append("⚠️ Apiksaban: eGFR <30 → **doz azaltımı uyarısı**.")

    elif a in {"dabigatran", "dabigatran eteksilat"}:
        if egfr < 30:
            warnings.append("⚠️ Dabigatran: eGFR <30 → **kesme/kaçınma uyarısı**.")
        if age >= 80 or has_verapamil:
            warnings.append("⚠️ Dabigatran: (yaş ≥80) veya (eş zamanlı verapamil) → **doz azaltımı uyarısı**.")
        if (75 <= age < 80) or (30 <= egfr <= 50) or high_bleed:
            warnings.append("ℹ️ Dabigatran: 75–80 yaş / eGFR 30–50 / yüksek kanama riski → **doz azaltımı bireysel değerlendirilir**.")

    elif a in {"edoksaban", "edoxaban"}:
        if egfr < 15:
            warnings.append("⚠️ Edoksaban: eGFR <15 → **kesme/kaçınma uyarısı**.")
        elif 15 <= egfr <= 50:
            warnings.append("⚠️ Edoksaban: eGFR 15–50 → **doz azaltımı uyarısı**.")
        if has_edox_interaction:
            warnings.append("⚠️ Edoksaban: etkileşimli ilaç (siklosporin/dronedarone/eritromisin/ketokonazol) → **doz azaltımı uyarısı**.")

    elif a in {"rivaroksaban", "rivaroxaban"}:
        if egfr < 15:
            warnings.append("⚠️ Rivaroksaban: eGFR <15 → **kesme/kaçınma uyarısı**.")
        elif 15 <= egfr <= 49:
            warnings.append("⚠️ Rivaroksaban: eGFR 15–49 → **doz azaltımı uyarısı**.")

    return warnings


def get_af_rate_control_text(has_af: str, hr: int, has_hf: str, lvef: str, current_meds: list[str]) -> str:
    brady_note = get_bradycardia_meds_note(hr=hr, has_hf=has_hf, current_meds=current_meds)

    if has_af != "Evet":
        base = "- AF’ye yönelik hız kontrol önerisi: Endike değil.\n"
        if brady_note:
            base += brady_note
        return base

    if hr >= 110:
        status = "kontrolsüz (yüksek ventrikül yanıtı)"
    elif hr >= 90:
        status = "kısmi kontrol"
    else:
        status = "kontrollü"

    on_bb = meds_contains_any(current_meds, BETA_BLOCKERS)
    on_non_dhp = meds_contains_any(current_meds, NON_DHP_CCB)
    hfrEF = (has_hf == "Evet" and lvef == "<40%")

    lines = [f"- AF perioperatif hız kontrolü: Ventrikül yanıtı {status} (≈{hr}/dk)."]

    if on_bb:
        lines.append("- Mevcut tedavide beta-bloker mevcut: perioperatif dönemde hemodinami izin verdiği ölçüde sürdürülmesi uygundur.")
    if on_non_dhp:
        if hfrEF:
            lines.append("- Non-DHP KKB (verapamil/diltiazem) mevcut: LVEF <40% olguda negatif inotropi nedeniyle dikkat/kaçınılması gerektiği hatırlatılır.")
        else:
            lines.append("- Non-DHP KKB (verapamil/diltiazem) mevcut: uygun hastada hız kontrolünde kullanılabilir; hipotansiyon/bradikardi açısından izlem önerilir.")

    if hfrEF:
        lines.append("- HFrEF varlığında non-DHP KKB’den kaçınma; hız kontrolünde beta-bloker ± digoksin; instabilitede amiodaron multidisipliner kararla düşünülebilir.")
    else:
        lines.append("- Hemodinami stabil hastada hız kontrolünde beta-bloker veya non-DHP KKB; instabilitede öncelik hemodinamik stabilizasyondur.")

    if brady_note:
        lines.append(brady_note.strip())

    return "\n".join(lines) + "\n"


def get_postop_af_risk_text(age: int, has_hf: str, has_ckd: str, surgery_risk: str, hr: int) -> str:
    flags = 0
    if age >= 70:
        flags += 1
    if has_hf == "Evet":
        flags += 1
    if has_ckd == "Evet":
        flags += 1
    if surgery_risk == "Yüksek":
        flags += 1
    if hr >= 100:
        flags += 1

    if flags >= 3:
        risk_level = "artmış"
    elif flags == 2:
        risk_level = "orta"
    else:
        risk_level = "düşük/orta"

    return f"- Postop AF/aritmi riski: {risk_level}. İlk 48–72 saatte ritim/HR ve elektrolitlerin yakın izlenmesi önerilir."


# ----------------------------
# Antiplatelet monotherapy preop plan
# ----------------------------
def get_antiplatelet_monotherapy_preop_plan(agent: str, surgery_risk: str) -> str:
    a = (agent or "").strip()
    if surgery_risk in {"Düşük", "Orta"}:
        return f"- {a}: Kanama riski düşük/orta → **Devam et (kesilmez).**"
    if surgery_risk == "Yüksek":
        if a == "Aspirin":
            return "- Aspirin: Kanama riski yüksek → **7 gün önce kes.**"
        if a == "Klopidogrel":
            return "- Klopidogrel: Kanama riski yüksek → **5 gün önce kes.**"
        return "- Ajan belirtilmedi (yüksek kanama riski)."
    return "- Kanama riski belirlenemedi."


def get_oac_monotherapy_hint(oac_agent: str) -> str:
    a = (oac_agent or "").strip()
    if not a or a == "Bilinmiyor":
        return "- OAC seçilmedi → Warfarin / Apiksaban / Rivaroksaban / Dabigatran / Edoksaban'dan biri seçilmeli."
    return f"- {a}: Kesme ve yeniden başlama planı Antikoagülan Değerlendirme bölümünde."


# ----------------------------
# DAPT agent-specific preop cutting info
# ----------------------------
def get_dapt_cutting_info(aspirin_dose: str, p2y12_agent: str, surgery_risk: str) -> list[str]:
    """Return concise cutting instructions for the specific DAPT agents selected."""
    lines = []
    asp = (aspirin_dose or "").strip()
    p2y12 = (p2y12_agent or "").strip()

    # Aspirin cutting info
    if asp and asp != "Bilinmiyor" and asp != "—":
        if surgery_risk == "Yüksek":
            lines.append(f"- Aspirin ({asp}): Yüksek kanama riski → **7 gün önce kes**, hemostaz sağlanınca tekrar başla.")
        else:
            lines.append(f"- Aspirin ({asp}): **Devam et** (düşük/orta kanama riski).")

    # P2Y12 cutting info — only for the selected agent
    if p2y12 and p2y12 != "Bilinmiyor" and p2y12 != "—":
        if p2y12 == "Klopidogrel":
            lines.append("- Klopidogrel: **5 gün önce kes**, postop 24–72 saat içinde yeniden başla.")
        elif p2y12 == "Prasugrel":
            lines.append("- Prasugrel: **7 gün önce kes**, postop 24–72 saat içinde yeniden başla.")
        elif p2y12 == "Tikagrelor":
            lines.append("- Tikagrelor: **3–5 gün önce kes**, postop 24–72 saat içinde yeniden başla.")

    if not lines:
        lines.append("- DAPT ajanları belirtilmedi.")

    return lines


def filter_dapt_recommendation(recommendation_tr: str, p2y12_agent: str) -> str:
    """Filter the YAML engine recommendation to only mention the selected P2Y12 agent."""
    if not recommendation_tr:
        return ""

    rec = recommendation_tr.strip()
    p2y12 = (p2y12_agent or "").strip()

    # If the recommendation contains all three agents, rebuild with only the selected one
    all_three = ("Tikagrelor" in rec and "Klopidogrel" in rec and "Prasugrel" in rec)
    if not all_three:
        return rec

    # Determine cutting time for the selected agent
    cutting_map = {
        "Klopidogrel": "Klopidogrel → 5 gün önce kesilir",
        "Prasugrel": "Prasugrel → 7 gün önce kesilir",
        "Tikagrelor": "Tikagrelor → 3–5 gün önce kesilir",
    }
    agent_cut = cutting_map.get(p2y12, "")

    # Build a clean, agent-specific recommendation
    parts = []
    if "ASA sürdürülerek" in rec or "aspirin" in rec.lower():
        parts.append("Aspirin sürdürülür")
    if agent_cut:
        parts.append(agent_cut)
    if "bridging" in rec.lower():
        parts.append("Gerekirse IV antiplatelet bridging düşünülebilir")
    parts.append("Postop yeniden başlama multidisipliner değerlendirme ile planlanır")

    return ". ".join(parts) + "."


# ----------------------------
# Consultation note generator
# ----------------------------
def generate_consultation_note(
    context: dict,
    dapt_result: dict,
    oac_text_block: str,
    device_note: str,
    rcri_block: str,
    esc_pathway_block: str,
    esc_workup_block: str,
    include_rcri: bool = True,
) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    hr_val = int(context.get("hr", 0) or 0)

    rhythm_line = (
        f"Atriyal fibrilasyon, ventrikül yanıtı yaklaşık {hr_val}/dk."
        if context.get("has_af") == "Evet"
        else f"Sinüs ritmi, kalp hızı yaklaşık {hr_val}/dk."
    )

    symptoms_list = context.get("symptoms", [])
    symptom_text = ", ".join(symptoms_list) if symptoms_list and "Yok" not in symptoms_list else "Aktif kardiyak semptom tariflemiyor."

    hf_line = ""
    if context.get("has_hf") == "Evet":
        hf_line = f"- Kalp yetersizliği: NYHA {context.get('nyha')}, LVEF {context.get('lvef')}. Perioperatif volüm dengesine dikkat."
    
    ckd_line = ""
    if context.get("has_ckd") == "Evet":
        egfr = float(context.get("egfr", 0) or 0)
        egfr_text = f"{egfr:.0f} ml/dk/1.73m²" if egfr > 0 else "bilinmiyor"
        ckd_line = f"- KBH: eGFR {egfr_text}. Nefrotoksik ajanlardan kaçınılmalı."

    comorb = []
    if context.get("has_dm") == "Evet":
        comorb.append("DM")
    if context.get("has_ht") == "Evet":
        comorb.append("HT")
    if context.get("has_cad") == "Evet":
        comorb.append("KAH/PCI")
    if context.get("has_af") == "Evet":
        comorb.append("AF")
    if context.get("has_mech_valve") == "Evet":
        comorb.append("Mekanik kapak")
    if context.get("has_hf") == "Evet":
        comorb.append("KY")
    if context.get("has_ckd") == "Evet":
        comorb.append("KBH")
    if context.get("has_device") == "Evet":
        comorb.append(f"Cihaz ({context.get('device_type')})")
    comorb_text = ", ".join(comorb) if comorb else "Belirtilmedi"

    meds = context.get("current_meds", [])
    meds_text = ", ".join(meds) if meds else "Belirtilmedi"

    ant_strategy = context.get("antithrombotic_strategy", "—")
    pci_time = context.get("pci_time", "—")

    if ant_strategy == "Monoterapi-OAC":
        oac_mono_agent = context.get("mono_oac_agent", "Bilinmiyor")
        antithrombotic_block = "\n".join(
            [
                f"- OAC Monoterapi: {oac_mono_agent} (PCI: {pci_time})",
                get_oac_monotherapy_hint(oac_mono_agent),
            ]
        )
    elif ant_strategy == "Monoterapi-AP":
        ap_agent = context.get("mono_ap_agent", "Bilinmiyor")
        ap_plan = get_antiplatelet_monotherapy_preop_plan(ap_agent, context.get("surgery_risk"))
        antithrombotic_block = "\n".join(
            [
                f"- Antiplatelet Monoterapi: {ap_agent} (PCI: {pci_time})",
                ap_plan,
            ]
        )
    elif ant_strategy == "DAPT":
        cutting_lines = get_dapt_cutting_info(
            aspirin_dose=context.get("aspirin_dose", ""),
            p2y12_agent=context.get("p2y12_agent_ui", ""),
            surgery_risk=context.get("surgery_risk", ""),
        )
        antithrombotic_block = "\n".join(
            [
                f"- DAPT (PCI: {pci_time})",
                *cutting_lines,
            ]
        )
    else:
        antithrombotic_block = "- Antitrombotik strateji belirtilmedi."

    plan_raw = dapt_result.get("recommendation_tr", "")
    rec_class = dapt_result.get("class", "")
    # Filter the YAML recommendation to only mention the selected P2Y12 agent
    p2y12_selected = context.get("p2y12_agent_ui", "")
    plan = filter_dapt_recommendation(plan_raw, p2y12_selected)

    af_rate_control = get_af_rate_control_text(
        has_af=context.get("has_af"),
        hr=int(context.get("hr", 0) or 0),
        has_hf=context.get("has_hf"),
        lvef=context.get("lvef"),
        current_meds=meds,
    )

    # Build RCRI section conditionally
    rcri_section = ""
    if include_rcri:
        rcri_section = f"""
D) Risk Katmanlama (RCRI + ESC)
{rcri_block}
{esc_pathway_block}
Önerilen tetkik:
{esc_workup_block}
"""

    # Build clinical notes section
    clinical_lines = []
    if hf_line:
        clinical_lines.append(hf_line)
    if ckd_line:
        clinical_lines.append(ckd_line)
    if device_note and device_note.strip():
        clinical_lines.append(device_note.strip())
    clinical_section = "\n".join(clinical_lines) if clinical_lines else "- Ek klinik not yok."

    # Build DAPT recommendation line (only if engine produced meaningful output)
    dapt_plan_line = ""
    if plan and plan.strip() and "uygulanmadı" not in plan.lower():
        dapt_plan_line = f"\n- Kılavuz önerisi: {plan}"
        if rec_class:
            dapt_plan_line += f" ({rec_class})"

    note = f"""PREOPERATİF KARDİYOLOJİ KONSÜLTASYON NOTU
Tarih: {today}

A) Hasta Bilgileri
- Yaş/Cinsiyet: {context.get("patient_age")} / {context.get("patient_sex")}
- Komorbiditeler: {comorb_text}
- İlaçlar: {meds_text}

B) Klinik Değerlendirme
- Ritim: {rhythm_line}
- TA: {context.get("sbp")}/{context.get("dbp")} mmHg
- Semptomlar: {symptom_text}
- Fonksiyonel kapasite: {context.get("functional_capacity")}

C) Cerrahi Bilgisi
- İşlem: {context.get("selected_surgery")}
- Kardiyak risk: {context.get("surgery_risk")} | Aciliyet: {context.get("urgency")}
{rcri_section}
E) Perioperatif Klinik Notlar
{clinical_section}

F) Antitrombotik Yönetim
{antithrombotic_block}{dapt_plan_line}

{oac_text_block}

G) Ritim / Hız Kontrolü
{af_rate_control}

H) Sonuç
- Bu çıktı karar destek amaçlıdır; nihai klinik karar ilgili hekim ve multidisipliner ekip tarafından verilir.
""".strip()

    return note


# ----------------------------
# Streamlit UI — SINGLE PAGE (Branding + Logo)
# Optimized for 1600x350 transparent PNG logo
# ----------------------------

import streamlit as st
import os

LOGO_PATH = "assets/logo.png"

st.set_page_config(
    page_title="SynerCardioConsult",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "🫀",
    layout="centered"
)

# Sidebar logo
if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, width=220)

# Main header logo (application width)
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, use_container_width=True)

# Centered title
st.markdown(
"""
<h1 style='text-align:center; margin-top:10px;'>
SynerCardioConsult
</h1>
""",
unsafe_allow_html=True
)

# Centered subtitle
st.markdown(
"""
<p style='text-align:center; font-size:18px; color:gray;'>
Preoperative Cardiology Consultation Tool
</p>
""",
unsafe_allow_html=True
)

# rules/dapt.yaml var mı?
if not os.path.exists("rules/dapt.yaml"):
    st.error("rules/dapt.yaml bulunamadı. Repo içinde rules/dapt.yaml yolunu kontrol et.")
    st.stop()

engine = DaptRuleEngine("rules/dapt.yaml")
oac_engine = OacRuleEngine()

if "answers" not in st.session_state:
    st.session_state["answers"] = {}
if "dapt_result" not in st.session_state:
    st.session_state["dapt_result"] = None


# ----------------------------
# 1) Shared patient inputs
# ----------------------------
with st.expander("1) Hasta Yaş, Cerrahi ve Klinik Bilgiler", expanded=True):
    colA, colB = st.columns(2)
    with colA:
        patient_age = st.number_input("Yaş", min_value=0, max_value=120, value=55, step=1)
    with colB:
        patient_sex = st.selectbox("Cinsiyet", ["Erkek", "Kadın"])

    st.markdown("---")

    selected_surgery = st.selectbox("Planlanan işlemi seçin (Table 5)", SURGERY_OPTIONS, index=0)
    auto_risk = SURGERY_TO_RISK.get(selected_surgery, "Orta")
    surgery_risk = st.selectbox(
        "Cerrahi kardiyak risk (otomatik)",
        ["Düşük", "Orta", "Yüksek"],
        index=["Düşük", "Orta", "Yüksek"].index(auto_risk),
        disabled=True,
    )
    urgency = st.selectbox("Cerrahi aciliyeti", ["Elektif", "Time-sensitive", "Acil"])

    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    with c1:
        hr = st.number_input("EKG hızı / Nabız (dk)", min_value=0, max_value=250, value=80, step=1)
    with c2:
        sbp = st.number_input("Sistolik TA (mmHg)", min_value=0, max_value=300, value=130, step=1)
    with c3:
        dbp = st.number_input("Diyastolik TA (mmHg)", min_value=0, max_value=200, value=80, step=1)

    st.markdown("---")

    symptoms = st.multiselect(
        "Mevcut semptomlar",
        ["Angina", "Dispne", "Senkop", "Kalp yetersizliği semptomu", "Yok"],
        default=["Yok"],
    )
    functional_capacity = st.selectbox("Fonksiyonel kapasite (MET)", ["≥4 MET", "<4 MET", "Bilinmiyor"])

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        has_hf = st.selectbox("Kalp yetersizliği var mı?", ["Hayır", "Evet"])
        nyha = st.selectbox("NYHA sınıfı", ["Bilinmiyor", "I", "II", "III", "IV"], disabled=(has_hf == "Hayır"))
        lvef = st.selectbox("LVEF", ["Bilinmiyor", "≥50%", "40–49%", "<40%"], disabled=(has_hf == "Hayır"))
    with col2:
        has_af = st.selectbox("Atriyal fibrilasyon (AF)", ["Hayır", "Evet"])
        has_ckd = st.selectbox("Kronik böbrek hastalığı (CKD)", ["Hayır", "Evet"])
        egfr = st.number_input("eGFR (ml/dk/1.73m²) - varsa", min_value=0.0, max_value=200.0, value=0.0, step=1.0)

    has_dm = st.selectbox("Diabetes mellitus", ["Hayır", "Evet"])
    has_ht = st.selectbox("Hipertansiyon", ["Hayır", "Evet"])

    # CAD/PCI + ≥1 year branching
    has_cad = st.selectbox("Koroner arter hastalığı / PCI öyküsü", ["Hayır", "Evet"])

    pci_time = "—"
    antithrombotic_strategy = "—"
    mono_ap_agent = "—"
    mono_oac_agent = "Bilinmiyor"

    if has_cad == "Evet":
        pci_time = st.selectbox("PCI/AKS üzerinden 1 yıl geçti mi?", ["<1 yıl", "≥1 yıl"], index=0, key="pci_time")
        if pci_time == "<1 yıl":
            antithrombotic_strategy = "DAPT"
        else:
            if has_af == "Evet":
                antithrombotic_strategy = "Monoterapi-OAC"
                st.markdown("### Monoterapi (AF + PCI ≥1 yıl) → OAC seçimi")
                mono_oac_agent = st.selectbox(
                    "OAC ajanı (monoterapi)",
                    ["Bilinmiyor", "Warfarin", "Apiksaban", "Rivaroksaban", "Dabigatran", "Edoksaban"],
                    index=0,
                    key="mono_oac_agent",
                    help="AF (+) ve PCI ≥1 yıl: antiplatelet monoterapi yerine OAC monoterapi tercih edilir.",
                )
                st.info(get_oac_monotherapy_hint(mono_oac_agent))
            else:
                antithrombotic_strategy = "Monoterapi-AP"
                st.markdown("### Monoterapi (AF yok + PCI ≥1 yıl) → Aspirin/Klopidogrel")
                mono_ap_agent = st.selectbox("Antiplatelet monoterapi ajanı", ["Aspirin", "Klopidogrel"], index=0, key="mono_ap_agent")
                st.info(get_antiplatelet_monotherapy_preop_plan(mono_ap_agent, surgery_risk))

    has_mech_valve_ui = st.selectbox("Mekanik kapak var mı?", ["Hayır", "Evet"])

    # RCRI module
    st.markdown("---")
    include_rcri = st.checkbox("RCRI (Revised Cardiac Risk Index) – ESC risk katmanlama ekle", value=False, key="include_rcri")

    rcri_flags = {}
    rcri_score = 0
    rcri_positives = []
    pathway_text = ""
    workup_list = []

    if include_rcri:
        default_high_risk_surgery = (surgery_risk == "Yüksek")

        colr1, colr2 = st.columns(2)
        with colr1:
            rcri_high_risk_surgery = st.checkbox(RCRI_ITEMS_TR["high_risk_surgery"], value=default_high_risk_surgery, key="rcri_high_risk_surgery")
            rcri_ihd = st.checkbox(RCRI_ITEMS_TR["ihd"], value=(has_cad == "Evet"), key="rcri_ihd")
            rcri_chf = st.checkbox(RCRI_ITEMS_TR["chf"], value=(has_hf == "Evet"), key="rcri_chf")
        with colr2:
            rcri_cva = st.checkbox(RCRI_ITEMS_TR["cva"], value=False, key="rcri_cva")
            rcri_dm_insulin = st.checkbox(RCRI_ITEMS_TR["dm_insulin"], value=False, key="rcri_dm_insulin")
            creatinine = st.number_input("Kreatinin (mg/dL) - varsa", min_value=0.0, max_value=25.0, value=0.0, step=0.1, key="creatinine")
            rcri_cr_gt2 = bool(creatinine > 2.0)

        rcri_flags = {
            "high_risk_surgery": rcri_high_risk_surgery,
            "ihd": rcri_ihd,
            "chf": rcri_chf,
            "cva": rcri_cva,
            "dm_insulin": rcri_dm_insulin,
            "cr_gt2": rcri_cr_gt2,
        }
        rcri_score, rcri_positives = calc_rcri(rcri_flags)

        st.markdown(f"**RCRI skoru:** `{rcri_score}` / 6")
        if rcri_positives:
            st.caption("Pozitif kriter(ler): " + " • ".join(rcri_positives))
        else:
            st.caption("Pozitif kriter yok (RCRI 0).")

        pathway_text, workup_list = esc_rcri_pathway_summary(
            surgery_risk=surgery_risk,
            rcri_score=rcri_score,
            functional_capacity=functional_capacity,
            symptoms=symptoms,
            urgency=urgency,
            has_hf=has_hf,
            lvef=lvef,
        )

        st.markdown("#### ESC şeması önizleme (RCRI + MET + semptom + cerrahi risk)")
        tabA, tabB = st.tabs(["Akış (özet)", "Önerilen test/izlem (özet)"])
        with tabA:
            st.markdown(pathway_text)
        with tabB:
            if workup_list:
                for w in workup_list:
                    st.write(f"- {w}")
            else:
                st.write("- Ek test önerisi yok.")

    # Device logic
    st.markdown("---")
    has_device = st.selectbox("Hastada pacemaker/ICD/CRT var mı?", ["Hayır", "Evet"])
    device_type = "—"
    pace_dependent = "—"
    if has_device == "Evet":
        device_type = st.selectbox("Cihaz tipi", ["Permanent pacemaker", "ICD", "CRT"])
        pace_dependent = st.selectbox("Hasta pace bağımlı mı?", ["Hayır", "Evet"])
        device_note_preview = get_device_management_note(has_device, device_type, pace_dependent)
        if device_note_preview.strip():
            st.markdown("**Cihaz Yönetimi Uyarısı (Önizleme)**")
            st.warning(device_note_preview)

    st.markdown("---")
    st.caption(DRUGS_CAPTION)
    current_meds = st.multiselect("Kullandığı ilaçlar (type-ahead)", options=DRUGS, default=[])


# ----------------------------
# 2) Antiplatelet (DAPT) -> only if PCI <1 year
# ----------------------------
show_tool1 = (has_cad == "Evet") and (pci_time == "<1 yıl")

with st.expander("2) Antiplatelet Değerlendirme – DAPT (PCI <1 yıl)", expanded=show_tool1):
    if not show_tool1:
        if has_cad != "Evet":
            st.info("Koroner arter hastalığı / PCI öyküsü **Hayır** seçildiği için Antiplatelet Değerlendirme (DAPT) algoritması gizlendi.")
        else:
            st.success("PCI/AKS üzerinden **≥1 yıl** geçtiği için monoterapi dalı aktif. DAPT değerlendirmesi uygulanmadı.")
        aspirin_dose = "—"
        p2y12_agent_ui = "—"
    else:
        st.caption(f"Kural seti: {engine.title_tr}")

        st.markdown("---")
        st.subheader("Antiplatelet Tedavi (Klinik Kayıt)")

        aspirin_dose = st.selectbox(
            "Aspirin günlük dozu",
            ["Bilinmiyor", "75 mg/gün", "81 mg/gün", "100 mg/gün", "150 mg/gün", "300 mg/gün"],
            index=0,
            key="aspirin_dose",
        )
        p2y12_agent_ui = st.selectbox(
            "P2Y12 inhibitörü (klinik kayıt)",
            ["Bilinmiyor", "Klopidogrel", "Prasugrel", "Tikagrelor"],
            index=0,
            key="p2y12_agent_ui",
        )

        st.markdown("---")
        answers = st.session_state["answers"]

        # YAML çoğunlukla answers["p2y12_agent"] bekler → map'liyoruz
        if p2y12_agent_ui and p2y12_agent_ui != "Bilinmiyor":
            answers["p2y12_agent"] = p2y12_agent_ui
        if aspirin_dose and aspirin_dose != "Bilinmiyor":
            answers["aspirin_dose"] = aspirin_dose

        visible_questions = engine.get_visible_questions(answers)

        for q in visible_questions:
            key = f"q_{q.id}"
            default = answers.get(q.id, q.options[0] if q.options else "")
            idx = q.options.index(default) if (q.options and default in q.options) else 0
            val = st.radio(q.text_tr, q.options, index=idx, key=key)
            answers[q.id] = val

        st.markdown("---")
        if st.button("DAPT Sonucu Göster", key="btn_tool1"):
            try:
                dapt_result = engine.evaluate(answers)
            except Exception as e:
                st.error("DAPT değerlendirme hatası (rules/dapt.yaml / eksik cevap / kural uyuşmazlığı).")
                st.exception(e)
                st.stop()

            st.session_state["dapt_result"] = dapt_result
            filtered_rec = filter_dapt_recommendation(dapt_result.get("recommendation_tr", ""), p2y12_agent_ui)
            st.success(filtered_rec)
            if dapt_result.get("class"):
                st.info(f"Öneri sınıfı: {dapt_result['class']}")

            show_raw = st.checkbox("Ham yanıtları göster (DAPT)", value=False, key="show_raw_tool1")
            if show_raw:
                st.json(answers)


# ----------------------------
# 3) Antikoagülan (OAK/NOAC)
# ----------------------------
show_tool2 = (has_af == "Evet") or (has_mech_valve_ui == "Evet")

oac_agent = "Bilinmiyor"
bleed_risk_oac = "Düşük-Orta"
very_high_bleed = False
high_te_risk = False

with st.expander("3) Antikoagülan Değerlendirme – OAK/NOAC (AF / Mekanik Kapak)", expanded=show_tool2):
    if not show_tool2:
        st.info("AF **Hayır** ve Mekanik kapak **Hayır** seçildiği için Antikoagülan Değerlendirme (OAK/NOAC) algoritması gizlendi.")
    else:
        OAC_OPTIONS = ["Bilinmiyor", "Warfarin", "Apiksaban", "Rivaroksaban", "Edoksaban", "Dabigatran"]

        preferred_oac = mono_oac_agent if antithrombotic_strategy == "Monoterapi-OAC" else "Bilinmiyor"

        if has_mech_valve_ui == "Evet":
            oac_agent = st.selectbox(
                "Oral antikoagülan",
                OAC_OPTIONS,
                index=OAC_OPTIONS.index("Warfarin"),
                disabled=True,
                help="Mekanik kapakta DOAC kullanılmaz; otomatik Warfarin seçildi.",
                key="oac_agent",
            )
        else:
            default_idx = OAC_OPTIONS.index(preferred_oac) if preferred_oac in OAC_OPTIONS else 0
            oac_agent = st.selectbox("Oral antikoagülan", OAC_OPTIONS, index=default_idx, key="oac_agent")

        bleed_risk_oac = st.selectbox(
            "Prosedür kanama riski (OAK/NOAC için)",
            ["Minör", "Düşük-Orta", "Yüksek"],
            index=1,
            key="bleed_risk_oac",
        )

        very_high_bleed = st.checkbox(
            "Çok yüksek kanama riski (örn. spinal/epidural, intrakraniyal, vitreoretinal vb.)",
            value=False,
            key="very_high_bleed",
        )

        has_mech_valve = (has_mech_valve_ui == "Evet")
        if has_mech_valve:
            high_te_risk = (
                st.selectbox(
                    "Yüksek tromboemboli riski var mı? (mekanik kapak + RF vb.)",
                    ["Hayır", "Evet"],
                    index=0,
                    key="high_te_risk_ui",
                )
                == "Evet"
            )
        else:
            st.caption("Not: Mekanik kapak yoksa bridging/TE risk değerlendirmesi genellikle daha sınırlıdır.")
            high_te_risk = False

        st.markdown("---")
        if st.button("Antikoagülan Sonucu Göster", key="btn_tool2"):
            mapped_bleed = "Düşük-Orta" if bleed_risk_oac in ["Minör", "Düşük-Orta"] else "Yüksek"
            res = oac_engine.evaluate(
                agent=oac_agent,
                urgency=urgency,
                bleed_risk=mapped_bleed,
                very_high_bleed=very_high_bleed,
                egfr=egfr,
                has_mech_valve=has_mech_valve,
                high_te_risk=high_te_risk,
            )

            dose_warnings = get_doac_dose_warnings(
                agent=oac_agent,
                age=int(patient_age or 0),
                egfr=float(egfr or 0),
                current_meds=current_meds,
                bleed_risk=mapped_bleed,
                very_high_bleed=very_high_bleed,
            )

            st.write("### Antikoagülan Değerlendirme Çıktısı")
            st.write(res.summary_tr)
            st.write(res.stop_plan_tr)
            st.write(res.bridging_tr)
            st.write(res.restart_plan_tr)
            st.caption(res.cautions_tr)

            if has_mech_valve:
                st.markdown("### Mekanik Kapak – Warfarin / EE Profilaksisi / Bridging Notu")
                st.info(get_mech_valve_warfarin_note())

            if dose_warnings:
                st.markdown("### DOAC Doz / Kesme Uyarıları")
                for w in dose_warnings:
                    if "kesme" in w.lower() or "kaçınma" in w.lower():
                        st.warning(w)
                    else:
                        st.info(w)


# ----------------------------
# 4) Konsültasyon Notu (AUTO-CALC)
# ----------------------------
with st.expander("4) Konsültasyon Notu", expanded=True):
    if st.button("Öneri + Konsültasyon Notu Oluştur", key="btn_generate_all"):
        # DAPT auto
        if show_tool1:
            answers = st.session_state.get("answers", {})
            # mapping (konsültasyon butonunda da garanti)
            if st.session_state.get("p2y12_agent_ui", "Bilinmiyor") != "Bilinmiyor":
                answers["p2y12_agent"] = st.session_state.get("p2y12_agent_ui")
            if st.session_state.get("aspirin_dose", "Bilinmiyor") != "Bilinmiyor":
                answers["aspirin_dose"] = st.session_state.get("aspirin_dose")

            try:
                dapt_result = engine.evaluate(answers)
            except Exception as e:
                st.error("DAPT otomatik değerlendirme hatası.")
                st.exception(e)
                st.stop()

            aspirin_val = st.session_state.get("aspirin_dose", "Bilinmiyor")
            p2y12_val = st.session_state.get("p2y12_agent_ui", "Bilinmiyor")
        else:
            dapt_result = {
                "output_id": "tool1_inactive",
                "recommendation_tr": "DAPT değerlendirmesi uygulanmadı (PCI ≥1 yıl veya KAH/PCI yok).",
                "class": "",
            }
            aspirin_val = "—"
            p2y12_val = "—"

        device_note = get_device_management_note(has_device, device_type, pace_dependent)

        # OAC auto
        if show_tool2:
            mapped_bleed = "Düşük-Orta" if bleed_risk_oac in ["Minör", "Düşük-Orta"] else "Yüksek"
            has_mech_valve = (has_mech_valve_ui == "Evet")
            agent_for_eval = "Warfarin" if has_mech_valve else oac_agent

            oac_res = oac_engine.evaluate(
                agent=agent_for_eval,
                urgency=urgency,
                bleed_risk=mapped_bleed,
                very_high_bleed=very_high_bleed,
                egfr=egfr,
                has_mech_valve=has_mech_valve,
                high_te_risk=high_te_risk,
            )

            dose_warnings = get_doac_dose_warnings(
                agent=agent_for_eval,
                age=int(patient_age or 0),
                egfr=float(egfr or 0),
                current_meds=current_meds,
                bleed_risk=mapped_bleed,
                very_high_bleed=very_high_bleed,
            )

            if has_mech_valve:
                base_lines = [
                    "Oral Antikoagülan Yönetimi",
                    oac_res.summary_tr,
                    "",
                    get_mech_valve_warfarin_note(),
                ]
            else:
                base_lines = [
                    "Oral Antikoagülan Yönetimi",
                    oac_res.summary_tr,
                    oac_res.stop_plan_tr,
                    oac_res.bridging_tr,
                    oac_res.restart_plan_tr,
                ]

            if dose_warnings:
                base_lines += ["", "DOAC Doz / Kesme Uyarıları:", *[f"- {w}" for w in dose_warnings]]

            oac_block = "\n".join([l for l in base_lines if l is not None and str(l).strip() != ""])
        else:
            oac_block = "Oral Antikoagülan Yönetimi\n- Değerlendirilmedi (AF veya mekanik kapak yok)."

        # RCRI text blocks (only if enabled)
        rcri_block = ""
        esc_pathway_block = ""
        esc_workup_block = ""

        if include_rcri:
            rcri_score_local, rcri_pos_local = calc_rcri(rcri_flags)
            rcri_block = "\n".join(
                [
                    f"- RCRI skoru: {rcri_score_local}/6",
                    ("- Pozitif kriter(ler): " + "; ".join(rcri_pos_local)) if rcri_pos_local else "- Pozitif kriter yok (RCRI 0).",
                ]
            )

            pathway_text_local, workup_list_local = esc_rcri_pathway_summary(
                surgery_risk=surgery_risk,
                rcri_score=rcri_score_local,
                functional_capacity=functional_capacity,
                symptoms=symptoms,
                urgency=urgency,
                has_hf=has_hf,
                lvef=lvef,
            )
            esc_pathway_block = pathway_text_local
            esc_workup_block = "\n".join([f"- {w}" for w in workup_list_local]) if workup_list_local else "- Ek test önerisi yok."

        ctx = {
            "patient_age": patient_age,
            "patient_sex": patient_sex,
            "selected_surgery": selected_surgery,
            "surgery_risk": surgery_risk,
            "urgency": urgency,
            "hr": hr,
            "sbp": sbp,
            "dbp": dbp,
            "symptoms": symptoms,
            "functional_capacity": functional_capacity,
            "has_hf": has_hf,
            "nyha": nyha,
            "lvef": lvef,
            "has_af": has_af,
            "has_ckd": has_ckd,
            "egfr": egfr,
            "has_dm": has_dm,
            "has_ht": has_ht,
            "has_cad": has_cad,
            "pci_time": pci_time,
            "antithrombotic_strategy": antithrombotic_strategy,
            "mono_ap_agent": mono_ap_agent,
            "mono_oac_agent": mono_oac_agent,
            "has_mech_valve": has_mech_valve_ui,
            "has_device": has_device,
            "device_type": device_type,
            "pace_dependent": pace_dependent,
            "aspirin_dose": aspirin_val,
            "p2y12_agent_ui": p2y12_val,
            "current_meds": current_meds,
        }

        note = generate_consultation_note(
            ctx,
            dapt_result,
            oac_block,
            device_note,
            rcri_block=rcri_block,
            esc_pathway_block=esc_pathway_block,
            esc_workup_block=esc_workup_block,
            include_rcri=include_rcri,
        )
        st.text_area("Kopyalanabilir çıktı", note, height=760)

    # ----------------------------
# Footer (Always visible)
# ----------------------------

st.markdown(
"""
<style>
.footer {
position: fixed;
left: 0;
bottom: 0;
width: 100%;
background-color: #f8f9fa;
color: #6c757d;
text-align: center;
padding: 10px;
font-size: 13px;
border-top: 1px solid #e6e6e6;
}
</style>

<div class="footer">
SynerCardioConsult v1.0 | © 2026  Halil Siner,MD – All rights reserved
</div>
""",
unsafe_allow_html=True
)
